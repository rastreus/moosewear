"""Layers, events, and the night: the through-the-day machinery."""

import json

import pytest
from hypothesis import given, settings, strategies as st

from wardrobe import core, store
from wardrobe.cli import main

LAYERS = [
    {"name": "quilted jacket", "role": "outer"},
    {"name": "plaid scarf", "role": "extra"},
    {"name": "merino sweater and corduroy trousers", "role": "core"},
]
LAYERS_JSON = json.dumps(LAYERS)

RECORD = [
    "record", "--date", "2026-11-07", "--location", "Testville",
    "--condition", "partly cloudy", "--high", "68", "--low", "34",
    "--precip", "0",
    "--outfit", "quilted jacket over a merino sweater and corduroy "
               "trousers, plaid scarf",
    "--reason", "A 34-degree swing: layers for dawn, shed by noon.",
    "--layers", LAYERS_JSON,
]


def run(db, argv):
    return main(argv + ["--db", str(db)])


def shed(db, time="11:27", outfit="merino sweater and corduroy trousers, "
                                 "plaid scarf"):
    return run(db, [
        "adjust", "--date", "2026-11-07", "--time", time,
        "--action", "shed", "--off", "quilted jacket",
        "--outfit", outfit, "--reason", "Warmed to 63F; shell off."])


# ---------- core: layer specs and state ----------

def test_parse_layers_rejects_bad_specs():
    for bad in ([], "nope", [{"name": "x"}],
                [{"name": "x", "role": "hat"}],
                [{"name": "x", "role": "core"},
                 {"name": "x", "role": "core"}],
                [{"name": "a", "role": "outer"},
                 {"name": "b", "role": "outer"}]):
        with pytest.raises(ValueError):
            core.parse_layers(bad)
    assert core.parse_layers(LAYERS) == LAYERS


def test_layer_state_folds_events_in_order():
    events = [
        {"kind": "layers", "action": "shed",
         "detail": {"off": ["quilted jacket", "plaid scarf"]}},
        {"kind": "night", "action": "dress", "detail": {}},
        {"kind": "layers", "action": "restore",
         "detail": {"on": ["quilted jacket"]}},
        {"kind": "layers", "action": "swap",
         "detail": {"outer": "a heavy waxed-canvas parka"}},
    ]
    state = core.layer_state(LAYERS, events)
    assert state["on"] == {
        "quilted jacket": True,
        "plaid scarf": False,
        "merino sweater and corduroy trousers": True,
    }
    assert state["outer_text"] == "a heavy waxed-canvas parka"


def test_validate_transition_guards():
    state = core.layer_state(LAYERS, [])
    assert core.validate_transition(LAYERS, state, "shed",
                                    off=["quilted jacket"]) == []
    assert core.validate_transition(LAYERS, state, "shed",
                                    off=["merino sweater and corduroy "
                                         "trousers"])  # core: refused
    assert core.validate_transition(LAYERS, state, "restore",
                                    on=["plaid scarf"])  # already on
    assert core.validate_transition(LAYERS, state, "none",
                                    off=["plaid scarf"])  # none takes none
    shed_state = core.layer_state(
        LAYERS, [{"kind": "layers", "action": "shed",
                  "detail": {"off": ["quilted jacket"]}}])
    assert core.validate_transition(LAYERS, shed_state, "swap",
                                    outer="a parka")  # outer off: refused


# ---------- store: events and idempotent slots ----------

def test_event_slots_are_unique(tmp_path):
    db = tmp_path / "wardrobe.db"
    event = {"date": "2026-11-07", "kind": "layers", "time": "11:27",
             "action": "none", "outfit": "the morning outfit",
             "reason": "Still cold.", "detail": {}}
    with store.connect(db) as conn:
        store.add_event(conn, event)
        assert store.get_event(conn, "2026-11-07", "layers",
                               "11:27")["action"] == "none"
        with pytest.raises(store.DuplicateSlot):
            store.add_event(conn, event)


def test_set_layers_is_set_once(tmp_path):
    db = tmp_path / "wardrobe.db"
    entry = {"date": "2026-11-07", "location": "Testville",
             "condition": "sunny", "high_f": 70, "low_f": 40,
             "precip_pct": 0, "outfit": "a jacket and jeans",
             "reason": "Fine day.", "layers": None}
    with store.connect(db) as conn:
        store.add_outfit(conn, entry)
        assert store.set_layers(conn, "2026-11-07", LAYERS) == "set"
        assert store.set_layers(conn, "2026-11-07", LAYERS) == "same"
        other = [{"name": "different coat", "role": "outer"},
                 {"name": "jeans", "role": "core"}]
        assert store.set_layers(conn, "2026-11-07", other) == "different"
        assert store.get_outfit(conn, "2026-11-07")["layers"] == LAYERS


# ---------- CLI: a full day, end to end ----------

def test_a_whole_day(tmp_path, capsys):
    db = tmp_path / "wardrobe.db"
    assert run(db, RECORD) == 0
    capsys.readouterr()

    # 11:27 — it warmed; shed the jacket.
    assert shed(db) == 0
    capsys.readouterr()

    # Re-running the identical slot is a no-op, not an error.
    assert shed(db) == 0
    assert "ALREADY RECORDED" in capsys.readouterr().out

    # A different decision in the same slot is refused.
    assert run(db, [
        "adjust", "--date", "2026-11-07", "--time", "11:27",
        "--action", "none", "--reason", "Changed my mind."]) == 3
    assert "SLOT TAKEN" in capsys.readouterr().out

    # Shedding it again in a later slot is refused by the guard.
    assert shed(db, time="15:27") == 3
    capsys.readouterr()

    # 15:27 — a no-change decision records fine without an outfit.
    assert run(db, [
        "adjust", "--date", "2026-11-07", "--time", "15:27",
        "--action", "none", "--reason", "Still mild at 66F."]) == 0
    capsys.readouterr()

    # 19:27 — evening cooled; put the jacket back on.
    assert run(db, [
        "adjust", "--date", "2026-11-07", "--time", "19:27",
        "--action", "restore", "--on", "quilted jacket",
        "--outfit", "quilted jacket over a merino sweater and "
                    "corduroy trousers, plaid scarf",
        "--reason", "Down to 48F; shell back on."]) == 0
    capsys.readouterr()

    # State reflects the whole day.
    assert run(db, ["state", "--date", "2026-11-07"]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["state"]["on"]["quilted jacket"] is True
    assert state["state"]["on"]["plaid scarf"] is True
    assert "19:27" in [e["time"] for e in state["events"]]
    assert state["worn"].startswith("quilted jacket over")

    # 20:30 — pajamas, and the same set never repeats.
    night = ["night", "--date", "2026-11-07", "--temp", "41",
             "--outfit", "teal flannel pajamas with cream piping",
             "--reason", "Winding down."]
    assert run(db, night) == 0
    capsys.readouterr()
    assert run(db, ["check-night", "--temp", "40",
                    "--outfit", "teal flannel pajamas with cream "
                                "piping"]) == 3
    capsys.readouterr()

    # The mirror tells the day's story.
    text = (tmp_path / "outfits.md").read_text(encoding="utf-8")
    assert "11:27 - layers off" in text
    assert "15:27 - checked, no change" in text
    assert "20:30 - pajamas" in text


def test_state_without_morning_record_is_refused(tmp_path, capsys):
    db = tmp_path / "wardrobe.db"
    assert run(db, ["state", "--date", "2026-11-08"]) == 3
    assert "NO OUTFIT" in capsys.readouterr().out


def test_swap_needs_weather_and_a_fresh_outer(tmp_path, capsys):
    db = tmp_path / "wardrobe.db"
    assert run(db, RECORD) == 0
    capsys.readouterr()
    swap = ["adjust", "--date", "2026-11-07", "--time", "15:27",
            "--action", "swap", "--outer", "a heavy teal parka",
            "--outfit", "heavy teal parka over a merino sweater",
            "--reason", "A cold front dropped it to 26F."]
    assert run(db, swap) == 3  # no weather given for validation
    capsys.readouterr()
    assert run(db, swap + ["--condition", "snow", "--high", "30",
                           "--low", "20"]) == 0
    capsys.readouterr()
    assert run(db, ["state", "--date", "2026-11-07"]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["state"]["outer_text"] == "a heavy teal parka"


# ---------- property: state folds are deterministic ----------

_NAME = st.sampled_from([l["name"] for l in LAYERS])


@st.composite
def valid_event_sequences(draw):
    """Random sequences of transitions the guard would accept."""
    events = []
    on = {l["name"]: True for l in LAYERS}
    for _ in range(draw(st.integers(0, 8))):
        choices = []
        sheddable = [n for n, v in on.items()
                     if v and dict((l["name"], l["role"])
                                   for l in LAYERS)[n] != "core"]
        restorable = [n for n, v in on.items() if not v]
        if sheddable:
            choices.append("shed")
        if restorable:
            choices.append("restore")
        choices.append("none")
        action = draw(st.sampled_from(choices))
        if action == "shed":
            name = draw(st.sampled_from(sheddable))
            on[name] = False
            events.append({"kind": "layers", "action": "shed",
                           "detail": {"off": [name]}})
        elif action == "restore":
            name = draw(st.sampled_from(restorable))
            on[name] = True
            events.append({"kind": "layers", "action": "restore",
                           "detail": {"on": [name]}})
        else:
            events.append({"kind": "layers", "action": "none",
                           "detail": {}})
    return events, on


@given(valid_event_sequences())
@settings(max_examples=60)
def test_state_matches_naive_fold(pair):
    events, expected_on = pair
    state = core.layer_state(LAYERS, events)
    assert state["on"] == expected_on
    # Folding twice is folding once: the state is a pure function.
    assert core.layer_state(LAYERS, events) == state
