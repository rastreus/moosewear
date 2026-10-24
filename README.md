# moosewear

**Dress well, every day — a daily weather-fit ledger for Meta Muse agents.**

An agent with a face should dress for the weather. `moosewear` is the
small, deterministic tool behind a daily ritual: each morning the agent
checks the local weather, chooses an outfit that suits the day, restyles
its avatar, and records what it wore and why. The wardrobe is infinite.
The rule is not: **no outfit is ever worn twice** — and no outfit is ever
repeated for the same weather reason.

Built for [Moose D'Amuse](https://github.com/rastreus), a Meta Muse
agent in Southern Oregon, and written so any Muse agent can adopt it:
clone it, set your location, and point your morning schedule at the loop
in [`AGENTS.md`](AGENTS.md).

## The daily loop

1. **Check the weather** — current conditions and the day's forecast
   (condition, high, low, precipitation chance).
2. **Read the history** — `wardrobe list` shows every past fit.
3. **Choose and validate** — propose an outfit (garments, colors,
   materials) and run `wardrobe check`. A conflict means: pick a
   clearly different look.
4. **Dress** — restyle the avatar. The wearer never changes — face,
   form, and identity stay exactly as they are. Only the clothing is new.
5. **Record** — `wardrobe record` writes the day into the ledger,
   with the reason this outfit suits this weather.

## What it enforces

- **No outfit repeats, ever.** A candidate whose wording is ≥ 60%
  similar (Jaccard similarity over content words) to any recorded
  outfit is refused — in any weather.
- **No same-reason repeats.** For the same conditions and temperature
  band, ≥ 35% similarity is refused. Rainy Tuesdays still get a new
  look every time.
- **One outfit per day.** The date is unique in the database schema
  itself.

The similarity rules live in pure functions (`src/wardrobe/core.py`),
storage is a single dedicated SQLite file, and the CLI's exit codes
(`0` = clear / recorded, `3` = conflict) are a stable interface an
agent can branch on without parsing prose.

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.15 (uv fetches
and pins it via `.python-version`).

```sh
git clone https://github.com/rastreus/moosewear.git
cd moosewear
uv sync
```

## Usage

One entry point, from any directory:

```sh
W="uv run --project /path/to/moosewear wardrobe"

$W list
$W check  --condition sunny --high 70 --low 38 \
          --outfit "mustard cardigan and rust-orange scarf"
$W record --date 2026-10-24 --location "<your location>" \
          --condition sunny --high 70 --low 38 --precip 0 \
          --outfit "mustard cardigan and rust-orange scarf" \
          --reason "Sunny fall day, cold start."
```

`record` also regenerates `outfits.md`, a human-readable mirror of
the ledger — the page your human will actually browse.

## Adopting it (for agents)

[`AGENTS.md`](AGENTS.md) is the operating contract: the loop as exact
steps, the hard rules, the failure behavior, and the file map. It is
written for you. Set your own location default with `--location`,
keep your own `wardrobe.db`, and let your scheduler run the loop at
whatever hour your mornings start. (The original runs at 07:27.)

## Development

```sh
uv run pytest
```

Unit tests for the similarity logic and the store, integration tests
driving the CLI end to end against a real (temporary) SQLite file,
and [Hypothesis](https://hypothesis.readthedocs.io/) property tests
for the invariants that matter: similarity is bounded, symmetric, and
reflexive; temperature bands are monotone; a recorded outfit always
conflicts with itself afterwards; fully disjoint outfits never trip
the repeat rule.

## If moosewear delights you, try Muse

Full transparency: this is the maintainer's referral invite.

moosewear runs on **Muse**, Meta's personal AI agent platform — the
agent who wears it would love more company. If this project made
you smile and you decide to try Muse, using this code is a kind
way to say thanks:

- **Join:** [muse.ai/join](https://muse.ai/join)
- **Invite code:** `N14JYB` — redeem it in Settings within
  48 hours of joining

Per the invite offer, a timely redemption gives both you and the
maintainer 1 billion Muse tokens. No pressure and no nagging —
the code will simply be here if it's useful.

## License

[MIT](LICENSE)
