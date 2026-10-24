"""SQLite store for the wardrobe ledger.

One dedicated database file (default: wardrobe.db in the project
root). The schema is the whole storage design: one row per day,
the date is unique, and writes happen in a single transaction.
"""

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
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


class DuplicateDate(Exception):
    """An outfit is already recorded for that date."""


def connect(db_path=DEFAULT_DB):
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def list_outfits(conn):
    rows = conn.execute(
        "SELECT date, location, condition, high_f, low_f, precip_pct,"
        " outfit, reason FROM outfits ORDER BY date"
    ).fetchall()
    return [dict(r) for r in rows]


def add_outfit(conn, entry):
    try:
        with conn:
            conn.execute(
                "INSERT INTO outfits"
                " (date, location, condition, high_f, low_f, precip_pct,"
                "  outfit, reason)"
                " VALUES (:date, :location, :condition, :high_f, :low_f,"
                "  :precip_pct, :outfit, :reason)",
                entry,
            )
    except sqlite3.IntegrityError as exc:
        raise DuplicateDate(entry["date"]) from exc
