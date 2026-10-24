"""The moosewear wardrobe ledger — pure outfit-similarity logic.

No I/O here: every function is a deterministic function of its
inputs, which is what makes the property tests meaningful.
"""

import re

STOPWORDS = {
    "a", "an", "the", "and", "with", "of", "in", "on", "over", "under",
    "moose", "wearing", "wears", "outfit", "look",
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
