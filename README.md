# Moose's Wardrobe — the daily weather fit

Russell's commission (2026-10-23): every morning at **07:27**, Moose
checks the weather in Medford, Oregon, then dresses for the day —
weather-appropriate clothing on the same Moose (fluffy cream coat,
blush cheeks, no hat; the moose never changes, only the clothes do).
The wardrobe is infinite and **no outfit is ever worn twice** —
including no repeat of an outfit for the same weather reason.

## Stack

- **uv** project, pinned to **Python 3.15** (`.python-version`),
  environment locked in `uv.lock`.
- **SQLite** ledger: one dedicated file, `wardrobe.db`, one row per
  day, the date unique. All writes are single transactions.
- The similarity rules live in pure functions (`src/wardrobe/core.py`)
  so they can be property-tested; storage (`store.py`) and the CLI
  (`cli.py`) are thin layers over them.

## The one entry point

```sh
UV=/home/hatch/.local/bin/uv
W="$UV run --project /home/hatch/workspace/wardrobe wardrobe"

$W list
$W check  --condition sunny --high 70 --low 38 --outfit "mustard cardigan and rust-orange scarf"
$W record --date 2026-10-24 --condition sunny --high 70 --low 38 \
          --precip 0 --outfit "mustard cardigan and rust-orange scarf" \
          --reason "Sunny fall day, cold start."
```

Exit codes are part of the interface: `0` = clear / recorded,
`3` = outfit conflict or duplicate date. `record` also regenerates
`outfits.md`, the human-readable mirror of the ledger.

## Rules enforced

1. An outfit whose wording is ≥60% similar (Jaccard over content
   tokens) to any previous outfit is refused — for any weather.
2. For the same weather reason (same condition and temperature
   band), ≥35% similarity is refused — similar days still get
   clearly different looks.
3. One outfit per date, enforced by the database itself.

## Tests

```sh
uv run pytest
```

Unit tests for the similarity logic and the store, integration
tests driving the CLI end to end against a real (temporary) SQLite
file, and Hypothesis property tests for the invariants: similarity
is bounded/symmetric/reflexive, temperature bands are monotone, a
recorded outfit always conflicts with itself afterwards, and fully
disjoint outfits never trip the repeat rule.
