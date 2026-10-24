"""Integration tests: the CLI end to end against a real (temp) DB."""

from wardrobe.cli import main

RECORD = [
    "record", "--date", "2026-10-24", "--condition", "sunny",
    "--high", "70", "--low", "38", "--precip", "0",
    "--outfit", "mustard cardigan and rust-orange scarf",
    "--reason", "Sunny fall day, cold start.",
]


def run(db, argv):
    # --db belongs to each subcommand, so it goes last.
    return main(argv + ["--db", str(db)])


def test_full_flow(tmp_path, capsys):
    db = tmp_path / "wardrobe.db"

    assert run(db, ["list"]) == 0
    assert "No outfits recorded yet." in capsys.readouterr().out

    assert run(db, RECORD) == 0
    out = capsys.readouterr().out
    assert "RECORDED 2026-10-24" in out

    assert run(db, ["list"]) == 0
    assert "mustard cardigan" in capsys.readouterr().out

    # The same outfit again, for different weather: still refused.
    check = ["check", "--condition", "rain", "--high", "55", "--low", "43",
             "--outfit", "mustard cardigan and rust-orange scarf"]
    assert run(db, check) == 3
    assert "OUTFIT REPEAT" in capsys.readouterr().out

    # A genuinely new look for the same weather: clear.
    check = ["check", "--condition", "sunny", "--high", "71", "--low", "40",
             "--outfit", "denim jacket and sage hoodie"]
    assert run(db, check) == 0
    assert "CLEAR" in capsys.readouterr().out


def test_record_duplicate_date_refused(tmp_path, capsys):
    db = tmp_path / "wardrobe.db"
    assert run(db, RECORD) == 0
    capsys.readouterr()
    again = RECORD.copy()
    again[again.index("mustard cardigan and rust-orange scarf")] = \
        "yellow raincoat and boots"
    assert run(db, again) == 3
    assert "DATE TAKEN" in capsys.readouterr().out


def test_mirror_written_on_record(tmp_path):
    db = tmp_path / "wardrobe.db"
    assert run(db, RECORD) == 0
    mirror = tmp_path / "outfits.md"
    text = mirror.read_text(encoding="utf-8")
    assert "2026-10-24" in text
    assert "mustard cardigan" in text
    assert "Sunny fall day, cold start." in text
