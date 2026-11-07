"""SQLite store for the wardrobe ledger.

One dedicated database file (default: wardrobe.db in the project
root). The schema is the whole storage design: one outfit row per
day (the date is unique), plus an events table holding the day's
timeline — layer changes and the night's pajamas — where the
(date, kind, time) triple is unique, which is what makes every
scheduled step idempotent. Writes happen in single transactions.
"""

import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "wardrobe.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS outfits (
    id         INTEGER PRIMARY KEY,
    date       TEXT NOT NULL UNIQUE,
    location   TEXT NOT NULL,
    condition  TEXT NOT NULL,
    high_f     INTEGER NOT NULL,
    low_f      INTEGER NOT NULL,
    precip_pct INTEGER NOT NULL DEFAULT 0,
    outfit     TEXT NOT NULL,
    reason     TEXT NOT NULL,
    layers     TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,
    date       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    time       TEXT NOT NULL,
    action     TEXT NOT NULL,
    outfit     TEXT NOT NULL,
    reason     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(date, kind, time)
);
"""


class DuplicateDate(Exception):
    """An outfit is already recorded for that date."""


class DuplicateSlot(Exception):
    """An event already occupies that (date, kind, time) slot."""


def connect(db_path=DEFAULT_DB):
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # Ledgers written before layers existed have an outfits table
    # without the column (the CREATE above is a no-op for them);
    # add it in place so old data keeps working untouched.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(outfits)")}
    if "layers" not in cols:
        conn.execute("ALTER TABLE outfits ADD COLUMN layers TEXT")
        conn.commit()
    return conn


def _outfit(row):
    entry = dict(row)
    raw = entry.get("layers")
    entry["layers"] = json.loads(raw) if raw else None
    return entry


def list_outfits(conn):
    rows = conn.execute(
        "SELECT date, location, condition, high_f, low_f, precip_pct,"
        " outfit, reason, layers FROM outfits ORDER BY date"
    ).fetchall()
    return [_outfit(r) for r in rows]


def get_outfit(conn, date):
    row = conn.execute(
        "SELECT date, location, condition, high_f, low_f, precip_pct,"
        " outfit, reason, layers FROM outfits WHERE date = ?",
        (date,),
    ).fetchone()
    return _outfit(row) if row else None


def add_outfit(conn, entry):
    entry = dict(entry)
    layers = entry.get("layers")
    entry["layers"] = json.dumps(layers) if layers is not None else None
    try:
        with conn:
            conn.execute(
                "INSERT INTO outfits"
                " (date, location, condition, high_f, low_f, precip_pct,"
                "  outfit, reason, layers)"
                " VALUES (:date, :location, :condition, :high_f, :low_f,"
                "  :precip_pct, :outfit, :reason, :layers)",
                entry,
            )
    except sqlite3.IntegrityError as exc:
        raise DuplicateDate(entry["date"]) from exc


def set_layers(conn, date, layers):
    """Set a day's layers once. Returns "set", "same", or "different".

    The set-once rule is what lets a day recorded before layers
    existed be backfilled through the tool without ever letting a
    later step quietly rewrite the decomposition.
    """
    row = conn.execute(
        "SELECT layers FROM outfits WHERE date = ?", (date,)
    ).fetchone()
    if row is None:
        raise DuplicateDate(date)  # no such day; caller reports it
    existing = row[0]
    if existing is not None:
        return "same" if json.loads(existing) == layers else "different"
    with conn:
        conn.execute(
            "UPDATE outfits SET layers = ? WHERE date = ?",
            (json.dumps(layers), date),
        )
    return "set"


def _event(row):
    event = dict(row)
    event["detail"] = json.loads(event.get("detail") or "{}")
    return event


def list_events(conn, date=None):
    if date is None:
        rows = conn.execute(
            "SELECT date, kind, time, action, outfit, reason, detail"
            " FROM events ORDER BY date, time"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT date, kind, time, action, outfit, reason, detail"
            " FROM events WHERE date = ? ORDER BY time",
            (date,),
        ).fetchall()
    return [_event(r) for r in rows]


def get_event(conn, date, kind, time):
    row = conn.execute(
        "SELECT date, kind, time, action, outfit, reason, detail"
        " FROM events WHERE date = ? AND kind = ? AND time = ?",
        (date, kind, time),
    ).fetchone()
    return _event(row) if row else None


def add_event(conn, event):
    event = dict(event)
    event["detail"] = json.dumps(event.get("detail") or {})
    try:
        with conn:
            conn.execute(
                "INSERT INTO events"
                " (date, kind, time, action, outfit, reason, detail)"
                " VALUES (:date, :kind, :time, :action, :outfit,"
                "  :reason, :detail)",
                event,
            )
    except sqlite3.IntegrityError as exc:
        raise DuplicateSlot(
            f"{event['date']} {event['kind']} {event['time']}") from exc
