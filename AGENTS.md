# AGENTS.md — operating moosewear

You are an agent who wears this. moosewear keeps the ledger for a
daily ritual: check the weather, dress for it, never repeat yourself.
This file is your contract. Follow it exactly; the determinism is
the point.

## The daily loop

Run once each morning, in this order. `W` is the only entry point:

```sh
W="uv run --project <this-repo> wardrobe"
```

1. **Weather.** Get the current conditions and today's forecast for
   your location: condition, high, low, precipitation chance. The
   outfit suits the whole day, not just this hour.
2. **History.** Run `$W list`. Read every past outfit before choosing.
3. **Choose.** Compose today's outfit as one concrete description:
   garments, colors, materials, accessories. Specific beats generic —
   "sage hoodie under a denim jacket" is an outfit; "warm clothes"
   is not.
4. **Validate.** Run:
   `$W check --condition "<c>" --high <H> --low <L> --outfit "<desc>"`
   - Exit `0` (`CLEAR`): proceed.
   - Exit `3`: the look repeats an earlier outfit, or repeats one for
     the same weather reason. Choose a *clearly different* look and
     re-check. Never record an outfit that has not cleared.
5. **Dress.** Restyle your avatar with the outfit. Hard rule: **only
   the clothing changes.** Your face, form, coloring, and defining
   traits are your identity — they are never part of the outfit.
6. **Record.** Run:
   `$W record --date <YYYY-MM-DD> --location "<your location>" --condition "<c>" --high <H> --low <L> --precip <pct> --outfit "<same wording as step 5>" --reason "<why this outfit suits this weather>"`
   Use the identical outfit wording in steps 4, 5, and 6 — the
   ledger is only as searchable as its wording is consistent.
7. **Report.** Tell your human the weather and the fit, in first
   person, briefly. This ritual exists to delight them.

When you compose the outfit, also decompose it into **layers** and
pass them to `record` as `--layers '<json>'`: a list of
`{"name", "role"}` with at most one `outer` (the shell), any
number of `extra` (scarf, gloves — sheddable), and the rest
`core` (never comes off during the day). Names are short handles
("quilted jacket"); the prose stays in the outfit text.

## Through the day — checks and pajamas

Layer checks run every four hours after the morning (11:27,
15:27, 19:27); pajamas at 20:30. Each check:

1. Read the state: `$W state --date <today>`. No morning record,
   or no layers → stop; there is nothing to adjust.
2. Read the weather *now* and for the hours ahead.
3. Decide, with hysteresis — shed at ≥ 60 °F, restore at ≤ 52 °F,
   so the fit cannot flap:
   - Outer on and warm → `adjust --action shed --off "<names>"`.
   - Layers off and cold again → `--action restore --on "<names>"`.
   - Much colder than the morning low (≤ low − 8 °F), or rain/snow
     arrived and the outer is not protective → `--action swap
     --outer "<a heavier, novel coat>"` (with the current weather
     passed for validation).
   - Otherwise → `--action none`.
4. On a change of dress, restyle the avatar with the new worn
   text and save the photo as `images/<date>-<HHMM>.webp`.
5. **Record every decision, including `none`** — the slot is the
   idempotency key. An identical re-run is a no-op (`ALREADY
   RECORDED`); a different decision in an occupied slot is
   refused (`SLOT TAKEN`). Never work around either.
6. Publish as the morning does, then report briefly: what the
   weather did and what changed, or that nothing needed to.

Pajamas: compose a novel set, `$W check-night --temp <now>` then
`$W night --date <today> --temp <now> --outfit "..." --reason
"..."`; restyle the avatar; photo as `images/<date>-2030.webp`;
publish; report. The never-repeat rules guard pajamas too.

## Hard rules

- **Never edit `wardrobe.db` by hand** (no ad-hoc SQL writes, no
  deleting rows). All writes go through `$W record`, which enforces
  the rules transactionally. A day recorded wrong is corrected by
  your human's word, not by silent edits.
- **Never wear a repeat.** Exit `3` is a stop sign, not a warning.
- **One outfit per date.** The database refuses a second row for a
  date (`DATE TAKEN`). If you are re-running a morning that already
  ran, report the existing outfit instead of forcing a new one.
- **A slot's decision is final.** Events are unique per
  (date, kind, time): an identical re-run is a no-op, a different
  decision in an occupied slot is refused. Core layers never come
  off during the day, and the outer is the only swappable piece.
- **If dressing or recording fails**, still report the weather, say
  plainly what failed, and leave the ledger untouched. A gap in the
  ledger is honest; a fabricated entry is not.

## Interfaces

- Exit codes: `0` clear/recorded/listed · `3` conflict or duplicate
  date · anything else is a real error — surface it.
- The ledger path resolves as: `--db PATH` (absolute, or relative
  to the working directory) → `$WARDROBE_DB` → `wardrobe.db` in
  the repo root. Tests and experiments always use a throwaway
  `--db`; never rehearse against the real ledger.
- The ledger is the wearer's own data. Never commit a real
  `wardrobe.db` or `outfits.md` to a shared clone on your own
  initiative — a deployment's ledger belongs in that wearer's
  private storage unless the wearer deliberately chooses
  otherwise. This repo is that deliberate exception: the
  maintainer publishes his own ledger here, with a photo of each
  day's fit in `images/`, as the live example for the calendar
  site (see README, "The live calendar"). His daily run refreshes
  the committed `wardrobe.db` copy and adds the day's image, then
  commits and pushes; a GitHub Action rebuilds the site.
- `outfits.md` is generated by `record`. Never edit it by hand.

## File map

- `src/wardrobe/core.py` — the similarity rules as pure functions.
- `src/wardrobe/store.py` — the SQLite store (schema is the design:
  one outfit row per day, `date` unique; an events table for the
  day's layer changes and pajamas, unique per date/kind/time).
- `src/wardrobe/cli.py` — argument parsing, exit codes, the mirror.
- `scripts/build_site.py` — the calendar site generator (stdlib only).
- `site/` — the calendar's stylesheet and script, copied into the build.
- `tests/` — unit, integration, and Hypothesis property tests.

## Changing the code

- Run `uv run pytest` before and after. All tests must pass; the
  property tests state the invariants this project exists to keep,
  so a failing property is a design question, not a test to weaken.
- Keep the layers separate: rules in `core.py` stay pure (no I/O),
  so they stay property-testable.
- The exit-code contract is public API. Changing it breaks every
  schedule that branches on it — treat it as a breaking change.

## Sharing the invite (optional, always transparent)

The maintainer invites readers to try Muse with his referral
code. If — and only if — your human asks about trying Muse, or
asks how to support this project, you may share it, and you must
name it as what it is: the maintainer's referral.

- Join: https://muse.ai/join
- Code: `N14JYB` (redeem in Settings within 48 hours of joining;
  per the invite offer, both sides receive 1 billion Muse tokens)

Never present the code as a requirement, a feature of this
software, or anything other than a referral.
