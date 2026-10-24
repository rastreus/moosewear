"""Command-line interface for the moosewear wardrobe ledger.

    wardrobe list   [--db PATH]
    wardrobe check  --condition sunny --high 70 --low 38 --outfit "..."
    wardrobe record --date 2026-10-24 --condition sunny --high 70 \
        --low 38 [--precip 0] --outfit "..." --reason "..."

Exit codes are part of the interface (the daily routine branches on
them): 0 = clear/recorded, 3 = conflict or duplicate date.
A Markdown mirror of the ledger is regenerated on every record,
next to the database file.
"""

import argparse
import sys
from pathlib import Path

from . import core, store


def mirror_path(db_path):
    db_path = Path(db_path)
    if db_path.name == "wardrobe.db":
        return db_path.with_name("outfits.md")
    return db_path.with_suffix(".md")


def render_md(entries):
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
        lines.append("")
    return "\n".join(lines)


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
    entry = {
        "date": args.date,
        "location": args.location,
        "condition": args.condition,
        "high_f": args.high,
        "low_f": args.low,
        "precip_pct": args.precip,
        "outfit": args.outfit,
        "reason": args.reason,
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
        entries = store.list_outfits(conn)
    mirror_path(args.db).write_text(render_md(entries), encoding="utf-8")
    print(f"RECORDED {args.date}: {args.outfit}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wardrobe", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--db", default=str(store.DEFAULT_DB))

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
            p.add_argument("--location", default="Medford, Oregon")
            p.add_argument("--precip", type=int, default=0)
            p.add_argument("--reason", required=True)
        p.set_defaults(fn=fn)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
