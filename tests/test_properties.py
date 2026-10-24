"""Hypothesis property tests for the wardrobe rules.

These state the invariants the ledger exists to keep, for any
inputs at all:
  - similarity is a well-behaved measure (bounded, symmetric,
    reflexive);
  - temperature bands never go backwards as it gets warmer;
  - a recorded outfit can never be checked in again as 'new';
  - fully disjoint outfits never trip the outfit-repeat rule.
"""

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from wardrobe import store
from wardrobe.core import BAND_RANK, conflicts, jaccard, temp_band, tokens

word = st.text(alphabet=string.ascii_lowercase, min_size=3, max_size=10)
word_set = st.sets(word, min_size=1, max_size=8)
temps = st.tuples(st.integers(-30, 120), st.integers(-30, 120)).filter(
    lambda t: t[0] >= t[1]
)  # (high, low)


@given(word_set, word_set)
def test_jaccard_bounded_and_symmetric(a, b):
    v = jaccard(a, b)
    assert 0.0 <= v <= 1.0
    assert v == jaccard(b, a)


@given(word_set)
def test_jaccard_reflexive(a):
    assert jaccard(a, a) == 1.0


@given(st.lists(temps, min_size=2, max_size=2))
def test_temp_band_never_goes_backwards(pair):
    (h1, l1), (h2, l2) = pair
    mid1, mid2 = (h1 + l1) / 2, (h2 + l2) / 2
    if mid1 <= mid2:
        assert BAND_RANK[temp_band(h1, l1)] <= BAND_RANK[temp_band(h2, l2)]


def outfit_text(words):
    return " ".join(sorted(words))


@given(word_set, word_set, temps)
@settings(max_examples=60)
def test_disjoint_outfits_never_repeat(words_a, words_b, hl):
    a, b = tokens(outfit_text(words_a)), tokens(outfit_text(words_b))
    if a & b:
        return  # not disjoint; the rule does not apply
    high, low = hl
    entry = {"date": "2026-01-01", "condition": "sunny",
             "high_f": high, "low_f": low, "outfit": outfit_text(words_a)}
    found = conflicts([entry], "sunny", high, low, outfit_text(words_b))
    assert not any(line.startswith("OUTFIT REPEAT") for line in found)


@given(word_set, temps, st.sampled_from(["sunny", "rain", "snow", "cloudy"]))
@settings(max_examples=40)
def test_a_recorded_outfit_always_conflicts_with_itself(words, hl, condition):
    # A fresh database per example, created inside the test body:
    # pytest fixtures are set up once per test item, not per
    # Hypothesis example, so the database must not come from one.
    import tempfile
    from pathlib import Path

    tmp = tempfile.TemporaryDirectory()
    db = Path(tmp.name) / "wardrobe.db"
    high, low = hl
    text = outfit_text(words)
    entry = {"date": "2026-01-01", "location": "Testville",
             "condition": condition, "high_f": high, "low_f": low,
             "precip_pct": 0, "outfit": text, "reason": "property test"}
    with store.connect(db) as conn:
        store.add_outfit(conn, entry)
        entries = store.list_outfits(conn)
    found = conflicts(entries, condition, high, low, text)
    assert any(line.startswith("OUTFIT REPEAT") for line in found)
