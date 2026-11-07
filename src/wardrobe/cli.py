"""Command-line interface for the moosewear wardrobe ledger.

    wardrobe list   [--db PATH]
    wardrobe check  --condition sunny --high 70 --low 38 --outfit "..."
    wardrobe record --date 2026-01-01 --location "Example City" \
        --condition sunny --high 70 --low 38 [--precip 0] \
        --outfit "..." --reason "..." [--layers '<json>']
    wardrobe layers --date 2026-01-01 --layers '<json>'
    wardrobe state  --date 2026-01-01
    wardrobe adjust --date 2026-01-01 --time 11:27 \
        --action shed|restore|swap|none [--off a,b] [--on a,b] \
        [--outer "..."] [--outfit "..."] --reason "..."
    wardrobe check-night --temp 41 --outfit "..."
    wardrobe night  --date 2026-01-01 [--time 20:30] --temp 41 \
        --outfit "..." --reason "..."

The day's outfit is decomposed into layers ([{"name", "role"}],
role outer/extra/core) so scheduled checks can shed, restore, or
swap pieces as the weather moves. Every check records an event —
including a no-change decision — in a slot unique per
(date, kind, time): re-recording the identical event is a no-op,
a different one is refused. That is what makes the routine
idempotent end to end.

Exit codes are part of the interface (the daily routine branches on
them): 0 = clear/recorded, 3 = conflict, duplicate, or refused
transition. A Markdown mirror of the ledger is regenerated on every
write, next to the database file.

Database path resolution, first match wins:
  1. the --db flag (absolute, or relative to the working directory)
  2. the WARDROBE_DB environment variable
  3. wardrobe.db in the project root (a fresh clone's starting point)

The tool is the code; the ledger is the wearer's own data and lives
wherever they point it — never inside a shared clone by default.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from . import core, store

ACTION_LABELS = {
    "shed": "layers off",
    "restore": "layers back on",
    "swap": "outer swapped",
    "none": "checked, no change",
    "dress": "pajamas",
}


def mirror_path(db_path):
    db_path = Path(db_path)
    if db_path.name == "wardrobe.db":
        return db_path.with_name("outfits.md")
    return db_path.with_suffix(".md")


def render_md(entries, events=()):
    by_date = {}
    for ev in events:
        by_date.setdefault(ev["date"], []).append(ev)
    lines = [
        "# Wardrobe - what the wearer wore, when, and why",
        "",
        "One entry per day, newest last. Kept in the SQLite ledger",
        "(`wardrobe.db`) and guarded by the wardrobe tool: no outfit",
        "repeats, and no outfit repeated for the same weather reason.",
        "The wearer never changes - only the clothing does.",
        "",
    ]
    if not entries:
        lines.append("_No outfits yet._")
        lines.append("")
    for e in entries:
        lines.append(f"## {e['date']} - {e['location']}")
        lines.append("")
        lines.append(
            f"- **Weather:** {e['condition']}, high {e['high_f']}F, "
            f"low {e['low_f']}F, precipitation {e['precip_pct']}%"
        )
        lines.append(f"- **Outfit:** {e['outfit']}")
        lines.append(f"- **Why:** {e['reason']}")
        for ev in by_date.get(e["date"], []):
            label = ACTION_LABELS.get(ev["action"], ev["action"])
            if ev["action"] == "none":
                lines.append(
                    f"- **{ev['time']} - {label}:** {ev['reason']}")
            else:
                lines.append(
                    f"- **{ev['time']} - {label}:** {ev['outfit']} "
                    f"({ev['reason']})")
        lines.append("")
    return "\n".join(lines)


def _refresh_mirror(conn, db):
    entries = store.list_outfits(conn)
    events = store.list_events(conn)
    mirror_path(db).write_text(render_md(entries, events), encoding="utf-8")


def _parse_layers(raw):
    """(layers, error) from a --layers JSON string."""
    if raw is None:
        return None, None
    try:
        return core.parse_layers(json.loads(raw)), None
    except (ValueError, json.JSONDecodeError) as exc:
        return None, f"BAD LAYERS: {exc}"


def _csv(text):
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def cmd_list(args):
    with store.connect(args.db) as conn:
        entries = store.list_outfits(conn)
    if not entries:
        print("No outfits recorded yet.")
        return 0
    for e in entries:
        print(
            f"{e['date']}  {e['condition']:<14} "
            f"{e['low_f']:>3}-{e['high_f']:<3}F  {e['outfit']}"
        )
    return 0


def cmd_check(args):
    with store.connect(args.db) as conn:
        entries = store.list_outfits(conn)
    found = core.conflicts(entries, args.condition, args.high, args.low,
                           args.outfit)
    if found:
        for line in found:
            print(line)
        return 3
    print("CLEAR: no outfit or same-weather-reason conflict.")
    return 0


def cmd_record(args):
    layers, error = _parse_layers(args.layers)
    if error:
        print(error)
        return 3
    entry = {
        "date": args.date,
        "location": args.location,
        "condition": args.condition,
        "high_f": args.high,
        "low_f": args.low,
        "precip_pct": args.precip,
        "outfit": args.outfit,
        "reason": args.reason,
        "layers": layers,
    }
    with store.connect(args.db) as conn:
        entries = store.list_outfits(conn)
        found = core.conflicts(entries, args.condition, args.high,
                               args.low, args.outfit)
        if found:
            for line in found:
                print(line)
            return 3
        try:
            store.add_outfit(conn, entry)
        except store.DuplicateDate:
            print(f"DATE TAKEN: {args.date} already has an outfit recorded.")
            return 3
        _refresh_mirror(conn, args.db)
    print(f"RECORDED {args.date}: {args.outfit}")
    return 0


def cmd_layers(args):
    layers, error = _parse_layers(args.layers)
    if error:
        print(error)
        return 3
    with store.connect(args.db) as conn:
        if store.get_outfit(conn, args.date) is None:
            print(f"NO OUTFIT recorded for {args.date}.")
            return 3
        try:
            result = store.set_layers(conn, args.date, layers)
        except store.DuplicateDate:
            print(f"NO OUTFIT recorded for {args.date}.")
            return 3
        if result == "different":
            print(f"LAYERS ALREADY SET for {args.date} and differ; "
                  "the decomposition is set once and never rewritten.")
            return 3
        _refresh_mirror(conn, args.db)
    print(f"LAYERS {'SET' if result == 'set' else 'UNCHANGED'} "
          f"{args.date}: {len(layers)} layers")
    return 0


def cmd_state(args):
    with store.connect(args.db) as conn:
        day = store.get_outfit(conn, args.date)
        if day is None:
            print(f"NO OUTFIT recorded for {args.date}.")
            return 3
        events = store.list_events(conn, args.date)
    layers = day["layers"]
    state = core.layer_state(layers, events) if layers else None
    night = next((e for e in events if e["kind"] == "night"), None)
    print(json.dumps({
        "date": day["date"],
        "condition": day["condition"],
        "high_f": day["high_f"],
        "low_f": day["low_f"],
        "layers": layers,
        "state": state,
        "events": events,
        "night": night,
        "worn": core.current_worn(day, events),
    }, indent=2))
    return 0


def _slot_check(conn, candidate):
    """None if the slot is free, else (exit_code, message)."""
    existing = store.get_event(conn, candidate["date"], candidate["kind"],
                               candidate["time"])
    if existing is None:
        return None
    same = all(existing[k] == candidate[k]
               for k in ("action", "outfit", "reason", "detail"))
    if same:
        return 0, (f"ALREADY RECORDED {candidate['date']} "
                   f"{candidate['time']}: {candidate['action']} — "
                   "identical event; nothing to do.")
    return 3, (f"SLOT TAKEN: {candidate['date']} {candidate['time']} "
               f"already holds a {existing['action']} event; a slot's "
               "decision is never rewritten.")


def cmd_adjust(args):
    off, on = _csv(args.off), _csv(args.on)
    detail = {}
    if off:
        detail["off"] = off
    if on:
        detail["on"] = on
    if args.outer:
        detail["outer"] = args.outer
    with store.connect(args.db) as conn:
        day = store.get_outfit(conn, args.date)
        if day is None:
            print(f"NO OUTFIT recorded for {args.date}.")
            return 3
        if not day["layers"]:
            print(f"NO LAYERS recorded for {args.date}; the morning "
                  "record carries none, so there is nothing to adjust.")
            return 3
        events = store.list_events(conn, args.date)
        outfit = args.outfit
        if outfit is None:
            if args.action != "none":
                print("--outfit is required for a change of dress.")
                return 3
            outfit = core.current_worn(day, events)
        candidate = {
            "date": args.date, "kind": "layers", "time": args.time,
            "action": args.action, "outfit": outfit,
            "reason": args.reason, "detail": detail,
        }
        slot = _slot_check(conn, candidate)
        if slot is not None:
            code, message = slot
            print(message)
            return code
        state = core.layer_state(day["layers"], events)
        problems = core.validate_transition(
            day["layers"], state, args.action, off, on, args.outer)
        if args.action == "swap":
            if args.condition is None or args.high is None or args.low is None:
                problems.append(
                    "swap validation needs the current weather "
                    "(--condition/--high/--low)")
            else:
                entries = store.list_outfits(conn)
                problems += core.conflicts(
                    entries, args.condition, args.high, args.low, args.outer)
        if problems:
            for line in problems:
                print(line)
            return 3
        store.add_event(conn, candidate)
        _refresh_mirror(conn, args.db)
    print(f"ADJUSTED {args.date} {args.time}: {args.action} — {outfit}")
    return 0


def _night_entries(conn, fallback_temp):
    entries = []
    for ev in store.list_events(conn):
        if ev["kind"] != "night":
            continue
        temp = ev["detail"].get("temp_f", fallback_temp)
        entries.append({
            "date": ev["date"], "condition": "night",
            "high_f": temp, "low_f": temp, "outfit": ev["outfit"],
        })
    return entries


def cmd_check_night(args):
    with store.connect(args.db) as conn:
        entries = _night_entries(conn, args.temp)
    found = core.conflicts(entries, "night", args.temp, args.temp,
                           args.outfit)
    if found:
        for line in found:
            print(line)
        return 3
    print("CLEAR: no pajama repeat.")
    return 0


def cmd_night(args):
    candidate = {
        "date": args.date, "kind": "night", "time": args.time,
        "action": "dress", "outfit": args.outfit,
        "reason": args.reason, "detail": {"temp_f": args.temp},
    }
    with store.connect(args.db) as conn:
        slot = _slot_check(conn, candidate)
        if slot is not None:
            code, message = slot
            print(message)
            return code
        entries = _night_entries(conn, args.temp)
        found = core.conflicts(entries, "night", args.temp, args.temp,
                               args.outfit)
        if found:
            for line in found:
                print(line)
            return 3
        store.add_event(conn, candidate)
        _refresh_mirror(conn, args.db)
    print(f"NIGHT RECORDED {args.date} {args.time}: {args.outfit}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wardrobe", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--db", default=None,
                       help="ledger path (default: $WARDROBE_DB, else "
                            "wardrobe.db in the project root)")

    p_list = sub.add_parser("list")
    common(p_list)
    p_list.set_defaults(fn=cmd_list)

    for name, fn in (("check", cmd_check), ("record", cmd_record)):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--condition", required=True)
        p.add_argument("--high", required=True, type=int)
        p.add_argument("--low", required=True, type=int)
        p.add_argument("--outfit", required=True)
        if name == "record":
            p.add_argument("--date", required=True)
            p.add_argument("--location", required=True)
            p.add_argument("--precip", type=int, default=0)
            p.add_argument("--reason", required=True)
            p.add_argument("--layers", default=None,
                           help='JSON list of {"name", "role"} layers')
        p.set_defaults(fn=fn)

    p_layers = sub.add_parser("layers")
    common(p_layers)
    p_layers.add_argument("--date", required=True)
    p_layers.add_argument("--layers", required=True,
                          help='JSON list of {"name", "role"} layers')
    p_layers.set_defaults(fn=cmd_layers)

    p_state = sub.add_parser("state")
    common(p_state)
    p_state.add_argument("--date", required=True)
    p_state.set_defaults(fn=cmd_state)

    p_adj = sub.add_parser("adjust")
    common(p_adj)
    p_adj.add_argument("--date", required=True)
    p_adj.add_argument("--time", required=True)
    p_adj.add_argument("--action", required=True,
                       choices=("shed", "restore", "swap", "none"))
    p_adj.add_argument("--off", default=None,
                       help="comma-separated layer names to take off")
    p_adj.add_argument("--on", default=None,
                       help="comma-separated layer names to put back")
    p_adj.add_argument("--outer", default=None,
                       help="replacement outer garment (swap)")
    p_adj.add_argument("--outfit", default=None,
                       help="full worn description after the change")
    p_adj.add_argument("--reason", required=True)
    p_adj.add_argument("--condition", default=None)
    p_adj.add_argument("--high", type=int, default=None)
    p_adj.add_argument("--low", type=int, default=None)
    p_adj.set_defaults(fn=cmd_adjust)

    p_cn = sub.add_parser("check-night")
    common(p_cn)
    p_cn.add_argument("--temp", required=True, type=int)
    p_cn.add_argument("--outfit", required=True)
    p_cn.set_defaults(fn=cmd_check_night)

    p_night = sub.add_parser("night")
    common(p_night)
    p_night.add_argument("--date", required=True)
    p_night.add_argument("--time", default="20:30")
    p_night.add_argument("--temp", required=True, type=int)
    p_night.add_argument("--outfit", required=True)
    p_night.add_argument("--reason", required=True)
    p_night.set_defaults(fn=cmd_night)

    args = parser.parse_args(argv)
    args.db = args.db or os.environ.get("WARDROBE_DB") or str(store.DEFAULT_DB)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
