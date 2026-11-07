"""Tests for the calendar site generator (scripts/build_site.py)."""

import importlib.util
import json
from pathlib import Path

import pytest

from wardrobe import store

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_site.py"
spec = importlib.util.spec_from_file_location("build_site", SCRIPT)
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


def entry(day, condition="sunny", outfit="mustard cardigan and rust-orange scarf"):
    return {"date": day, "location": "Testville", "condition": condition,
            "high_f": 70, "low_f": 38, "precip_pct": 40, "outfit": outfit,
            "reason": "Because the weather said so."}


@pytest.fixture()
def built(tmp_path):
    db = tmp_path / "wardrobe.db"
    images = tmp_path / "images"
    images.mkdir()
    with store.connect(db) as conn:
        store.add_outfit(conn, entry("2026-09-30", "Snow showers"))
        store.add_outfit(conn, entry("2026-10-01", "Dense fog",
                                     outfit='<b>teal</b> "vest" & cream socks'))
        store.add_outfit(conn, entry("2026-10-02", "Partly sunny"))
    (images / "2026-09-30.webp").write_bytes(b"RIFF")
    (images / "2026-10-02.webp").write_bytes(b"RIFF")
    out = tmp_path / "_site"
    site.build(db, out, images=images)
    return out


@pytest.mark.parametrize("condition, kind", [
    ("Sunny", "sunny"),
    ("Clear then mostly cloudy", "partly"),
    ("AM rain showers then mostly cloudy", "rain"),
    ("Scattered thunderstorms", "storm"),
    ("Light snow", "snow"),
    ("Morning fog", "fog"),
    ("Overcast", "cloudy"),
    ("Something unheard of", "cloudy"),
])
def test_sky_of(condition, kind):
    assert site.sky_of(condition) == kind


@pytest.fixture()
def built_with_events(tmp_path):
    db = tmp_path / "wardrobe.db"
    images = tmp_path / "images"
    images.mkdir()
    with store.connect(db) as conn:
        store.add_outfit(conn, entry("2026-10-03", "Partly cloudy"))
        store.add_event(conn, {
            "date": "2026-10-03", "kind": "layers", "time": "11:27",
            "action": "shed", "outfit": "mustard cardigan, scarf off",
            "reason": "Warmed up.", "detail": {"off": ["jacket"]}})
        store.add_event(conn, {
            "date": "2026-10-03", "kind": "layers", "time": "15:27",
            "action": "none", "outfit": "mustard cardigan, scarf off",
            "reason": "Still mild.", "detail": {}})
        store.add_event(conn, {
            "date": "2026-10-03", "kind": "night", "time": "20:30",
            "action": "dress",
            "outfit": "teal flannel pajamas with cream piping",
            "reason": "Winding down.", "detail": {"temp_f": 44}})
    (images / "2026-10-03.webp").write_bytes(b"RIFF")
    (images / "2026-10-03-2030.webp").write_bytes(b"RIFF")
    out = tmp_path / "_site"
    site.build(db, out, images=images)
    return out


def test_day_page_shows_the_days_timeline(built_with_events):
    page = (built_with_events / "day" / "2026-10-03.html").read_text(
        encoding="utf-8")
    assert "Through the day" in page
    assert "11:27" in page and "Layers off" in page
    assert "Checked — no change" in page and "Still mild." in page
    assert "Pajamas" in page
    assert "teal flannel pajamas" in page
    assert "2026-10-03-2030.webp" in page  # the night photo is used


def test_fits_json_carries_events(built_with_events):
    data = json.loads((built_with_events / "fits.json").read_text(
        encoding="utf-8"))
    (fit,) = [f for f in data if f["date"] == "2026-10-03"]
    assert [e["action"] for e in fit["events"]] == ["shed", "none", "dress"]
    assert "has_image" not in fit["events"][0]


def test_palette_finds_colors_in_order_and_dedupes():
    names = [n for n, _ in site.palette(
        "deep-teal jacket, sage-and-cream plaid, cherry-red boots, teal hat, "
        "cable-knit cream scarf")]
    assert names == ["deep teal", "sage", "cream", "cherry red", "teal"]


def test_palette_is_empty_without_colors():
    assert site.palette("a sturdy waxed-canvas jacket") == []


def test_streak_counts_back_from_latest():
    fits = [entry(d) for d in ("2026-10-01", "2026-10-03", "2026-10-04")]
    assert site.streak(fits) == 2


def test_build_writes_every_page(built):
    for rel in ("index.html", "2026-09.html", "2026-10.html", "fits.json",
                "assets/style.css", "assets/site.js",
                "day/2026-09-30.html", "day/2026-10-01.html", "day/2026-10-02.html"):
        assert (built / rel).is_file(), rel


def test_months_link_to_each_other(built):
    sep = (built / "2026-09.html").read_text()
    octo = (built / "2026-10.html").read_text()
    assert 'href="2026-10.html" rel="next"' in sep
    assert 'href="2026-09.html" rel="prev"' in octo
    assert (built / "index.html").read_text() == octo


def test_outfit_text_is_escaped(built):
    page = (built / "day" / "2026-10-01.html").read_text()
    assert "<b>teal</b>" not in page
    assert "&lt;b&gt;teal&lt;/b&gt; &quot;vest&quot; &amp; cream socks" in page


def test_missing_photo_gets_a_placeholder(built):
    page = (built / "day" / "2026-10-01.html").read_text()
    assert "no-photo" in page
    assert "images/2026-10-01.webp" not in page


def test_fits_json_is_the_ledger(built):
    fits = json.loads((built / "fits.json").read_text())
    assert [f["date"] for f in fits] == ["2026-09-30", "2026-10-01", "2026-10-02"]
    assert "has_image" not in fits[0]
