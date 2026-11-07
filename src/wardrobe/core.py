"""The moosewear wardrobe ledger — pure outfit-similarity logic.

No I/O here: every function is a deterministic function of its
inputs, which is what makes the property tests meaningful.
"""

import re

STOPWORDS = {
    "a", "an", "the", "and", "with", "of", "in", "on", "over", "under",
    "wearer", "wearing", "wears", "outfit", "look",
}

BAND_RANK = {
    "freezing": 0,
    "cold": 1,
    "cool": 2,
    "mild": 3,
    "warm": 4,
    "hot": 5,
}


def tokens(text):
    """Content words of an outfit description, lowercased."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def jaccard(a, b):
    """Jaccard similarity of two token sets, in [0, 1]."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def temp_band(high, low):
    """Coarse band so 'similar weather' is comparable across days."""
    mid = (high + low) / 2.0
    if mid < 35:
        return "freezing"
    if mid < 50:
        return "cold"
    if mid < 62:
        return "cool"
    if mid < 74:
        return "mild"
    if mid < 86:
        return "warm"
    return "hot"


def conflicts(entries, condition, high, low, outfit):
    """Conflicts between a candidate outfit and recorded history.

    `entries` are dicts with condition/high_f/low_f/outfit keys.
    Returns human-readable conflict strings; empty means clear.
    Two rules (the wearer's): the same outfit never repeats at all, and
    an outfit never repeats for the same weather reason — same
    condition and temperature band — even at lower similarity.
    """
    found = []
    new_tokens = tokens(outfit)
    new_band = temp_band(high, low)
    for entry in entries:
        old_tokens = tokens(entry["outfit"])
        overlap = jaccard(new_tokens, old_tokens)
        if overlap >= 0.6:
            found.append(
                f"OUTFIT REPEAT: {overlap:.0%} similar to {entry['date']} "
                f"({entry['outfit']!r})"
            )
        same_reason = (
            entry["condition"].strip().lower() == condition.strip().lower()
            and temp_band(entry["high_f"], entry["low_f"]) == new_band
        )
        if same_reason and overlap >= 0.35:
            found.append(
                f"SAME-REASON REPEAT: {condition}/{new_band} already worn "
                f"on {entry['date']} with a {overlap:.0%}-similar outfit "
                f"({entry['outfit']!r}) - pick a clearly different look "
                f"for this weather"
            )
    return found


# ---------- layers and the day's events ----------

LAYER_ROLES = ("outer", "extra", "core")
EVENT_ACTIONS = ("shed", "restore", "swap", "none", "dress")


def parse_layers(raw):
    """Validate a layers spec (already JSON-decoded).

    A layers spec is a non-empty list of {"name", "role"} dicts with
    unique names, roles from LAYER_ROLES, and at most one `outer`
    (the shell that can be shed or swapped). Returns the normalized
    list; raises ValueError on anything else.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("layers must be a non-empty list")
    seen = set()
    outers = 0
    layers = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"layer is not an object: {item!r}")
        name, role = item.get("name"), item.get("role")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"layer name must be non-empty text: {item!r}")
        if role not in LAYER_ROLES:
            raise ValueError(f"layer role must be one of {LAYER_ROLES}: {item!r}")
        if name in seen:
            raise ValueError(f"duplicate layer name: {name!r}")
        seen.add(name)
        if role == "outer":
            outers += 1
        layers.append({"name": name, "role": role})
    if outers > 1:
        raise ValueError("at most one layer may have the outer role")
    return layers


def layer_state(layers, events):
    """Fold a day's layers events into the current layer state.

    `layers` is a validated spec; `events` are event dicts in time
    order (kind "layers" only — night events do not touch layers).
    Returns {"on": {name: bool}, "outer_text": str | None}: the
    outer_text is the current outer garment's description once a
    swap has replaced it, else None (the morning original).
    """
    on = {layer["name"]: True for layer in layers}
    outer_text = None
    for event in events:
        if event.get("kind") != "layers":
            continue
        detail = event.get("detail") or {}
        action = event.get("action")
        if action == "shed":
            for name in detail.get("off", []):
                if name in on:
                    on[name] = False
        elif action == "restore":
            for name in detail.get("on", []):
                if name in on:
                    on[name] = True
        elif action == "swap":
            if detail.get("outer"):
                outer_text = detail["outer"]
    return {"on": on, "outer_text": outer_text}


def validate_transition(layers, state, action, off=(), on=(), outer=None):
    """Problems with a proposed layers event; empty means it may run.

    The point of the guard: a check can never shed a layer that is
    already off or restore one that is on, so a duplicated or stale
    check fails loudly instead of corrupting the day's state.
    """
    problems = []
    if action not in EVENT_ACTIONS:
        return [f"unknown action: {action!r}"]
    by_name = {layer["name"]: layer for layer in layers}
    if action == "shed":
        if not off:
            problems.append("shed needs at least one layer to take off")
        for name in off:
            layer = by_name.get(name)
            if layer is None:
                problems.append(f"no such layer: {name!r}")
            elif layer["role"] == "core":
                problems.append(f"core layer never comes off: {name!r}")
            elif not state["on"][name]:
                problems.append(f"layer already off: {name!r}")
        if on or outer:
            problems.append("shed takes no --on or --outer")
    elif action == "restore":
        if not on:
            problems.append("restore needs at least one layer to put back")
        for name in on:
            if name not in by_name:
                problems.append(f"no such layer: {name!r}")
            elif state["on"][name]:
                problems.append(f"layer already on: {name!r}")
        if off or outer:
            problems.append("restore takes no --off or --outer")
    elif action == "swap":
        outer_layers = [l for l in layers if l["role"] == "outer"]
        if not outer_layers:
            problems.append("this outfit has no outer layer to swap")
        elif not state["on"][outer_layers[0]["name"]]:
            problems.append("the outer layer is off; restore it instead")
        if not outer or not outer.strip():
            problems.append("swap needs the replacement outer (--outer)")
        if off or on:
            problems.append("swap takes no --off or --on")
    elif action == "none":
        if off or on or outer:
            problems.append("a no-change decision takes no layer changes")
    return problems


def current_worn(day, events):
    """The outfit text currently in effect for a day.

    The morning outfit, replaced by each later event's outfit text
    in time order; the night event (pajamas) wins last, as it
    should — after 20:30 the wearer is in pajamas.
    """
    worn = day["outfit"]
    for event in events:
        if event.get("outfit"):
            worn = event["outfit"]
    return worn
