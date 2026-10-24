"""Tests for the SQLite store: roundtrip, uniqueness, ordering."""

import pytest

from wardrobe import store

ENTRY = {
    "date": "2026-10-24",
    "location": "Testville",
    "condition": "sunny",
    "high_f": 70,
    "low_f": 38,
    "precip_pct": 0,
    "outfit": "mustard cardigan and rust-orange scarf",
    "reason": "Sunny fall day, cold start.",
}


@pytest.fixture()
def conn(tmp_path):
    with store.connect(tmp_path / "test.db") as c:
        yield c


def test_add_and_list_roundtrip(conn):
    store.add_outfit(conn, ENTRY)
    rows = store.list_outfits(conn)
    assert len(rows) == 1
    assert rows[0]["outfit"] == ENTRY["outfit"]
    assert rows[0]["precip_pct"] == 0


def test_duplicate_date_rejected(conn):
    store.add_outfit(conn, ENTRY)
    with pytest.raises(store.DuplicateDate):
        store.add_outfit(conn, {**ENTRY, "outfit": "something else entirely"})


def test_list_orders_by_date(conn):
    store.add_outfit(conn, {**ENTRY, "date": "2026-10-26"})
    store.add_outfit(conn, ENTRY)
    dates = [r["date"] for r in store.list_outfits(conn)]
    assert dates == ["2026-10-24", "2026-10-26"]


def test_data_survives_reconnect(tmp_path):
    db = tmp_path / "test.db"
    with store.connect(db) as c:
        store.add_outfit(c, ENTRY)
    with store.connect(db) as c:
        assert store.list_outfits(c)[0]["date"] == "2026-10-24"
