"""Unit tests for the pure similarity logic."""

from wardrobe.core import conflicts, jaccard, temp_band, tokens


def test_tokens_lowercases_and_drops_stopwords():
    assert tokens("The wearer wearing a RED Scarf") == {"red", "scarf"}


def test_tokens_keeps_short_content_words_out():
    # Words of length <= 2 are dropped as noise.
    assert tokens("ox go in red") == {"red"}


def test_jaccard_identical_and_disjoint():
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a"}, {"b"}) == 0.0


def test_jaccard_partial_and_empty():
    assert jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    assert jaccard(set(), {"a"}) == 0.0
    assert jaccard(set(), set()) == 0.0


def test_temp_band_boundaries():
    assert temp_band(30, 20) == "freezing"   # mid 25
    assert temp_band(40, 30) == "cold"       # mid 35
    assert temp_band(60, 40) == "cool"       # mid 50
    assert temp_band(70, 54) == "mild"       # mid 62
    assert temp_band(80, 68) == "warm"       # mid 74
    assert temp_band(95, 77) == "hot"        # mid 86


ENTRY = {
    "date": "2026-10-24",
    "condition": "sunny",
    "high_f": 70,
    "low_f": 38,
    "outfit": "mustard cardigan and rust-orange scarf",
}


def test_exact_repeat_flags_outfit_and_reason():
    found = conflicts([ENTRY], "sunny", 70, 38, ENTRY["outfit"])
    kinds = [line.split(":")[0] for line in found]
    assert kinds == ["OUTFIT REPEAT", "SAME-REASON REPEAT"]


def test_same_outfit_other_weather_still_an_outfit_repeat():
    found = conflicts([ENTRY], "rain", 55, 43, ENTRY["outfit"])
    assert len(found) == 1
    assert found[0].startswith("OUTFIT REPEAT")


def test_different_look_same_weather_is_clear():
    found = conflicts([ENTRY], "sunny", 71, 40, "denim jacket and sage hoodie")
    assert found == []


def test_similar_look_same_reason_flags_reason_only():
    # ~50% token overlap, same condition and band: reason rule fires,
    # outfit rule (60%) does not.
    found = conflicts([ENTRY], "sunny", 72, 41,
                      "mustard cardigan and cream scarf")
    assert len(found) == 1
    assert found[0].startswith("SAME-REASON REPEAT")


def test_empty_history_is_always_clear():
    assert conflicts([], "snow", 30, 20, "parka and mittens") == []
