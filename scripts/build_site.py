#!/usr/bin/env python3
"""Build the moosewear daily-fit calendar site from the ledger.

Reads the wearer's SQLite ledger (default: wardrobe.db in the repo
root) and the per-day images in images/ (named YYYY-MM-DD.webp), and
writes a static site to _site/:

  index.html        the latest fit, the latest month, the closet rail
  <YYYY-MM>.html    one calendar page per month with fits
  day/<date>.html   one page per fit: big image, weather, outfit, why
  fits.json         the raw data, for anything that wants it
  assets/           site/style.css and site/site.js, copied through
  images/           copied through

Standard library only. Run by .github/workflows/pages.yml on every
push to main, and by hand with:

  python3 scripts/build_site.py [LEDGER] [OUT]
"""

import calendar
import hashlib
import html
import json
import re
import shutil
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "images"
ASSETS = ROOT / "site"
REPO_URL = "https://github.com/rastreus/moosewear"
FONTS = ("https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT,WONK"
         "@9..144,400..900,0..100,0..1&family=Nunito:wght@400..800&display=swap")
RAIL_SIZE = 14


def esc(s):
    return html.escape(str(s), quote=True)


# ---------- weather ----------

# First match wins, so the most dramatic weather in a mixed forecast
# ("AM rain showers then mostly cloudy") sets the day's sky.
SKIES = [
    ("storm", r"thunder|storm|lightning"),
    ("snow", r"snow|sleet|flurr|blizzard|ice"),
    ("rain", r"rain|shower|drizzle|sprinkle"),
    ("fog", r"fog|mist|haze|smoke"),
    ("partly", r"(?=.*(sun|clear|fair))(?=.*(cloud|overcast))|partly"),
    ("cloudy", r"cloud|overcast|gr[ae]y"),
    ("sunny", r"sun|clear|fair|bright"),
]


def sky_of(condition):
    text = condition.lower()
    for kind, pattern in SKIES:
        if re.search(pattern, text):
            return kind
    return "cloudy"


_SUN = ('<circle cx="{x}" cy="{y}" r="{r}" fill="#ffc93c" stroke="#e39b0b" '
        'stroke-width="1.5"/>')
_RAYS = ('<g stroke="#e39b0b" stroke-width="2" stroke-linecap="round">'
         '<path d="M16 3v3M16 26v3M3 16h3M26 16h3M6.8 6.8l2.1 2.1M23.1 23.1'
         'l2.1 2.1M6.8 25.2l2.1-2.1M23.1 8.9l2.1-2.1"/></g>')
_CLOUD = ('<path d="M9.5 {b}h13a5 5 0 0 0 .9-9.92 7 7 0 0 0-13.5 1.3A4.3 4.3 0 0 0 '
          '9.5 {b}z" fill="#fff" stroke="#9089a8" stroke-width="1.6" '
          'stroke-linejoin="round" transform="translate({dx} 0)"/>')

ICONS = {
    "sunny": _RAYS + _SUN.format(x=16, y=16, r=6),
    "partly": ('<g transform="translate(-4 -4) scale(.8)">' + _RAYS
               + _SUN.format(x=16, y=16, r=6) + "</g>"
               + _CLOUD.format(b=27, dx=2)),
    "cloudy": (_CLOUD.format(b=20, dx=-3).replace('fill="#fff"', 'fill="#e6e3ef"')
               + _CLOUD.format(b=26, dx=2)),
    "rain": (_CLOUD.format(b=19, dx=0)
             + '<g stroke="#4f97d1" stroke-width="2" stroke-linecap="round">'
             '<path d="M11 23l-1.5 4M16.5 23 15 27M22 23l-1.5 4"/></g>'),
    "storm": (_CLOUD.format(b=18, dx=0)
              + '<path d="M17.5 19 13 25h4l-2 5 6-7.5h-4l2-3.5z" fill="#ffc93c" '
              'stroke="#e39b0b" stroke-width="1.2" stroke-linejoin="round"/>'),
    "snow": (_CLOUD.format(b=19, dx=0)
             + '<g fill="#8ec1e6"><circle cx="10.5" cy="24.5" r="1.6"/>'
             '<circle cx="16" cy="27.5" r="1.6"/><circle cx="21.5" cy="24.5" r="1.6"/></g>'),
    "fog": ('<g stroke="#a09bb3" stroke-width="2.4" stroke-linecap="round">'
            '<path d="M5 11h17M9 16h18M5 21h15M11 26h14"/></g>'),
}


def icon(kind, cls="wx-icon"):
    return (f'<svg class="{cls}" viewBox="0 0 32 32" aria-hidden="true" '
            f'focusable="false">{ICONS[kind]}</svg>')


HANGER = ('<svg class="{cls}" viewBox="0 0 64 64" fill="none" stroke="currentColor" '
          'stroke-width="4" stroke-linecap="round" stroke-linejoin="round" '
          'aria-hidden="true"><path d="M26 13a6 6 0 1 1 6 6v4"/><path d="M32 23 '
          '7 42.5c-2 1.6-.9 4.5 1.6 4.5h46.8c2.5 0 3.6-2.9 1.6-4.5L32 23z"/></svg>')

FAVICON = ("data:image/svg+xml," + HANGER.format(cls="f")
           .replace('stroke="currentColor"', 'stroke="%23c8601d"')
           .replace('class="f"', 'xmlns="http://www.w3.org/2000/svg"')
           .replace('"', "'").replace("<", "%3C").replace(">", "%3E"))


def decor(kind):
    """Weather drawn behind the big photo: sun, clouds, rain, snow."""
    def puff(top, left, width, delay=0):
        return (f'<svg class="puff" viewBox="0 0 32 32" style="top:{top}%;'
                f'left:{left}%;width:{width}%;animation-delay:-{delay}s">'
                + _CLOUD.format(b=24, dx=0) + "</svg>")

    def falls(n, seed):
        out = []
        for i in range(n):
            x = (i * 37 + seed) % 96 + 2
            out.append(f'<span class="fall" style="--x:{x}%;'
                       f'--d:-{(i * 0.53) % 3:.2f}s;--t:{1.3 + (i % 4) * 0.25:.2f}s;'
                       f'--y:{(i * 23) % 80 + 5}%"></span>')
        return "".join(out)

    sun = '<svg class="orb" viewBox="0 0 32 32">' + ICONS["sunny"] + "</svg>"
    parts = {
        "sunny": sun,
        # Kept to the corners, clear of the wearer's head.
        "partly": sun + puff(15, 70, 24),
        "cloudy": puff(4, 3, 22) + puff(10, 74, 23, 6) + puff(48, 82, 15, 3),
        "rain": puff(3, 3, 22) + puff(7, 74, 23, 5) + falls(12, 5),
        "storm": puff(3, 3, 23) + puff(6, 73, 24, 5) + falls(14, 11),
        "snow": puff(4, 74, 22) + falls(14, 3),
        "fog": "".join(f'<span class="mist" style="top:{t}%;left:{l}%;'
                       f'animation-delay:-{d}s"></span>'
                       for t, l, d in ((20, -20, 0), (46, 30, 4), (70, -10, 8))),
    }
    return f'<span class="decor" aria-hidden="true">{parts[kind]}</span>'


def thermometer(lo, hi):
    """Today's low-to-high stretch of a 10-100°F gradient."""
    def pos(t):
        return max(0, min(100, round((t - 10) / 90 * 100)))
    a, b = pos(lo), pos(hi)
    if b - a < 6:  # always leave a visible sliver
        b = min(100, a + 6)
        a = b - 6
    return (f'<span class="thermo" aria-hidden="true"><span style="--lo:{a}%;'
            f'--hi:{b}%"></span></span>')


def raindrop(pct, day):
    """A droplet filled to the chance of precipitation; `day` keys its clipPath."""
    pct = max(0, min(100, int(pct)))
    top = 2 + 26 * (1 - pct / 100)
    path = "M13 2C9 8 4 13.5 4 19a9 9 0 0 0 18 0C22 13.5 17 8 13 2z"
    clip = f"drop-{day}"
    return (f'<svg class="drop" viewBox="0 0 26 30" aria-hidden="true">'
            f'<clipPath id="{clip}"><path d="{path}"/></clipPath>'
            f'<rect x="0" y="{top:.1f}" width="26" height="30" fill="#6aa9dc" '
            f'clip-path="url(#{clip})"/>'
            f'<path d="{path}" fill="none" stroke="#4f97d1" stroke-width="1.8"/></svg>')


# ---------- the outfit's palette ----------

COLORS = {
    "white": "#f7f5ef", "ivory": "#f6f0dc", "cream": "#f2e6c9", "bone": "#e9e0cc",
    "ecru": "#e3d6b8", "oat": "#dccdb0", "oatmeal": "#d8c8a8", "beige": "#d8c3a0",
    "sand": "#d6bf94", "khaki": "#bfae7d", "tan": "#c39a6b", "camel": "#c08a4b",
    "fawn": "#c8a27a", "taupe": "#8f7d6e", "caramel": "#b8732f", "cognac": "#9a4e1e",
    "chestnut": "#8a4a26", "chocolate": "#5c3520", "cocoa": "#6b4532",
    "mocha": "#7a5541", "espresso": "#3f2a20", "brown": "#7a4d2b",
    "black": "#26221f", "charcoal": "#45434a", "slate": "#5f6b78", "ash": "#a4a09a",
    "grey": "#9a9895", "gray": "#9a9895", "heather-grey": "#a9a6a3",
    "dove-grey": "#bdbab6", "silver": "#c5c8cc", "pewter": "#8f9396",
    "red": "#c8352e", "cherry": "#b8202b", "cherry-red": "#c0232c",
    "scarlet": "#d12b23", "crimson": "#a8172e", "tomato": "#e0533b",
    "brick": "#a5432f", "rust": "#b4532a", "rust-red": "#a9432a",
    "rust-orange": "#c0602a", "terracotta": "#c4643f", "burgundy": "#7b1e34",
    "maroon": "#6d1f2a", "wine": "#6e2338", "oxblood": "#5e1a1d",
    "ruby": "#a51d3f", "raspberry": "#c22e5d", "berry": "#8e2c56",
    "pink": "#eea3b6", "blush": "#f0bfb8", "rose": "#d9798a", "dusty-rose": "#c98f93",
    "coral": "#ee7b62", "salmon": "#f09a82", "peach": "#f6b98f", "apricot": "#f3a86b",
    "fuchsia": "#c2358f", "magenta": "#b5307f",
    "orange": "#ea7a26", "burnt-orange": "#c35a1c", "pumpkin": "#df6f1f",
    "amber": "#e39a2c", "marigold": "#efa52c", "saffron": "#f0a91f",
    "tangerine": "#f2862b", "ochre": "#c98d2e", "mustard": "#d4a42a",
    "gold": "#d6aa3a", "golden": "#d9a93b", "honey": "#d9a441", "butter": "#f6e08f",
    "buttercup": "#f4cf45", "buttercup-yellow": "#f2c94c", "yellow": "#f3cd3c",
    "lemon": "#f5e161", "lime": "#a8c94a", "chartreuse": "#b5c43a",
    "green": "#4b8b4e", "olive": "#6f7139", "moss": "#6c7a3c", "sage": "#a3b18f",
    "mint": "#a9dbc0", "seafoam": "#93cdb6", "jade": "#3f9b78", "emerald": "#2b8a5c",
    "pine": "#2f5a40", "forest": "#2f5233", "forest-green": "#2f5a35",
    "hunter-green": "#2e4d34",
    "teal": "#2f7f82", "deep-teal": "#1f5f66", "turquoise": "#3fb6b0",
    "aqua": "#66c9cf", "blue": "#3b6fb6", "sky-blue": "#89bde6",
    "cornflower": "#6b8fd6", "cobalt": "#2c4fa8", "denim": "#4f6d93",
    "indigo": "#3a3d7c", "navy": "#253457", "periwinkle": "#9aa3e0",
    "purple": "#7b4a9b", "violet": "#7f5ab3", "plum": "#6e3b5f",
    "dusty-plum": "#8a5d7c", "mauve": "#b08497", "lilac": "#c3a9d6",
    "lavender": "#b9a7d8",
}

_WORD = re.compile(r"[a-z]+(?:-[a-z]+)*")


def palette(outfit, limit=8):
    """Named colors in the outfit, in order of appearance."""
    found = []
    for word in _WORD.findall(outfit.lower()):
        names = [word] if word in COLORS else [p for p in word.split("-") if p in COLORS]
        for name in names:
            if COLORS[name] not in (c for _, c in found):
                found.append((name.replace("-", " "), COLORS[name]))
    return found[:limit]


def buttons(outfit, named=False):
    items = "".join(
        f'<li title="{esc(name)}"><span class="button" style="--c:{hexc}"></span>'
        f'<span class="label">{esc(name)}</span></li>'
        for name, hexc in palette(outfit))
    if not items:
        return ""
    cls = "buttons named" if named else "buttons"
    return f'<ul class="{cls}" aria-label="The palette">{items}</ul>'


# ---------- dates ----------

def d_of(f):
    return date.fromisoformat(f["date"])


def long_date(d):
    return f"{d:%A}, {d:%B} {d.day}"


def short_date(d):
    return f"{d:%a}, {d:%b} {d.day}"


def streak(fits):
    """Consecutive days ending on the latest fit."""
    days = {d_of(f) for f in fits}
    day, n = max(days), 0
    while day in days:
        n += 1
        day -= timedelta(days=1)
    return n


# ---------- components ----------

def photo(f, root, *, lazy=True, with_decor=False):
    kind = sky_of(f["condition"])
    if f["has_image"]:
        loading = ' loading="lazy"' if lazy else ' fetchpriority="high"'
        inner = (f'<img src="{root}images/{f["date"]}.webp" width="1600" '
                 f'height="1600" alt="{esc(f["outfit"])}"{loading} decoding="async">')
    else:
        inner = (f'<span class="no-photo" role="img" aria-label="No photo for '
                 f'this day">{HANGER.format(cls="")}</span>')
    return kind, (decor(kind) if with_decor else "") + inner


def weather(f):
    kind = sky_of(f["condition"])
    return f"""<dl class="wx">
  <div><dt>Sky</dt><dd>{icon(kind)}<span>{esc(f['condition'])}</span></dd></div>
  <div><dt>Temp</dt><dd><span class="temps">
    <span class="temps-nums"><span class="lo">{f['low_f']}°</span><span class="hi">{f['high_f']}°F</span></span>
    {thermometer(f['low_f'], f['high_f'])}
    <span class="sr-only"> low {f['low_f']}°F, high {f['high_f']}°F</span></span></dd></div>
  <div><dt>Rain</dt><dd>{raindrop(f['precip_pct'], f['date'])}<span>{f['precip_pct']}% chance</span></dd></div>
</dl>"""


def feature(f, root, *, on_day=False):
    kind, pic = photo(f, root, lazy=False, with_decor=True)
    d = d_of(f)
    if on_day:
        sky = f'<div class="sky sky-{kind}">{pic}</div>'
        top, cta = "", ""
    else:
        sky = (f'<a class="sky sky-{kind}" href="{root}day/{f["date"]}.html" '
               f'aria-label="Open {long_date(d)}">{pic}</a>')
        top = (f'<p class="eyebrow"><span data-latest="{f["date"]}">Latest fit</span>'
               f' · {long_date(d)}</p>')
        cta = (f'<a class="cta" href="{root}day/{f["date"]}.html">See the full look '
               f'<span class="arrow" aria-hidden="true">→</span></a>')
    return f"""<section class="feature{' on-day' if on_day else ''}">
  {sky}
  <div class="feature-body">
    {top}
    <p class="fit-text">{esc(f['outfit'])}</p>
    {buttons(f['outfit'], named=on_day)}
    {weather(f)}
    <aside class="why"><span class="why-label">Why this fit</span><p>{esc(f['reason'])}</p></aside>
    {cta}
  </div>
</section>"""


def calendar_grid(y, m, by_day, root):
    cells = []
    for d in calendar.Calendar(firstweekday=6).itermonthdates(y, m):
        if d.month != m:
            cells.append('<li class="cal-day is-blank" aria-hidden="true"></li>')
            continue
        f = by_day.get(d.day)
        if not f:
            cells.append(f'<li class="cal-day" data-date="{d}">'
                         f'<span class="num">{d.day}</span></li>')
            continue
        kind, pic = photo(f, root)
        label = f"{long_date(d)}: {f['condition']}, {f['high_f']}° / {f['low_f']}°"
        cells.append(
            f'<li class="cal-day has-fit" data-date="{d}"><a href="{root}day/{d}.html" '
            f'aria-label="{esc(label)}"><span class="sky sky-{kind}">{pic}</span>'
            f'<span class="num">{d.day}</span>{icon(kind, "mini")}'
            f'<span class="hi">{f["high_f"]}°</span></a></li>')
    heads = "".join(f'<span><span class="long">{n}</span><span class="short">{n[0]}'
                    f"</span></span>"
                    for n in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"))
    return (f'<div class="cal-weekdays" aria-hidden="true">{heads}</div>'
            f'<ol class="cal" role="list">{"".join(cells)}</ol>')


def rail(fits, root):
    items = []
    for f in reversed(fits[-RAIL_SIZE:]):
        kind, pic = photo(f, root)
        d = d_of(f)
        items.append(
            f'<li><a class="hanging" href="{root}day/{f["date"]}.html">'
            f'<span class="sky sky-{kind}">{pic}</span>'
            f'<span class="tag">{icon(kind)}<span>{d:%b} {d.day}</span>'
            f'<span class="t">{f["high_f"]}°/{f["low_f"]}°</span></span></a></li>')
    more = len(fits) > RAIL_SIZE
    sub = (f"The latest {RAIL_SIZE}, newest first." if more
           else "Every fit so far, newest first.")
    return f"""<section class="closet" aria-labelledby="closet-title">
  <h2 class="section-title" id="closet-title">The closet</h2>
  <p class="closet-sub">{sub} Scroll the rail →</p>
  <ul class="rail" role="list">{''.join(items)}</ul>
</section>"""


def footer(root):
    return f"""<footer class="foot">
  <p>Every morning: check the weather, dress for it, never repeat.</p>
  <p>Made with felt, forecasts &amp; a stubborn little ledger <span class="heart" aria-hidden="true">♥</span>
    · <a href="{root}fits.json">fits.json</a> · <a href="{REPO_URL}">moosewear on GitHub</a></p>
</footer>"""


def layout(title, body, root, *, description, body_class=""):
    css_v = _version(ASSETS / "style.css")
    js_v = _version(ASSETS / "site.js")
    hanger_mask = FAVICON.replace("%23c8601d", "black")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="theme-color" content="#fbf5ea" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1e1923" media="(prefers-color-scheme: dark)">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{esc(FONTS)}">
<link rel="stylesheet" href="{root}assets/style.css?v={css_v}">
<style>:root{{--hanger:url("{hanger_mask}")}}.sr-only{{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}}</style>
<script src="{root}assets/site.js?v={js_v}" defer></script>
</head>
<body class="{body_class}">
<div class="wrap">
{body}
{footer(root)}
</div>
</body>
</html>
"""


def _version(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def brand(root, small=False):
    cls = "brand brand-small" if small else "brand"
    return (f'<a class="{cls}" href="{root}index.html">{HANGER.format(cls="brand-mark")}'
            f'<span class="brand-name">moosewear</span></a>')


def masthead(fits, root):
    n, run = len(fits), streak(fits)
    where = fits[-1]["location"]
    plural = "" if n == 1 else "s"
    return f"""<header class="masthead">
  {brand(root)}
  <p class="tagline">Dressed for the weather. Never the same fit twice.</p>
  <ul class="stats" role="list">
    <li><b>{n}</b> fit{plural} worn</li>
    <li><b>0</b> repeats, ever</li>
    <li><b>{run}</b>-day streak</li>
    <li>📍 {esc(where)}</li>
  </ul>
</header>"""


# ---------- pages ----------

def month_name(key):
    y, m = (int(p) for p in key.split("-"))
    return f"{calendar.month_name[m]} {y}"


def month_page(key, fits, months, all_fits, root=""):
    y, m = (int(p) for p in key.split("-"))
    i = months.index(key)
    by_day = {d_of(f).day: f for f in fits}

    def nav(j, rel, glyph):
        if 0 <= j < len(months):
            return (f'<a href="{root}{months[j]}.html" rel="{rel}" '
                    f'aria-label="{month_name(months[j])}">{glyph}</a>')
        return f'<span aria-hidden="true">{glyph}</span>'

    is_latest = key == months[-1]
    n = len(fits)
    title = month_name(key)
    body = f"""{masthead(all_fits, root)}
<main>
{feature(all_fits[-1], root) if is_latest else ''}
<section class="month" aria-labelledby="month-title">
  <div class="month-head">
    <div>
      <h2 class="section-title" id="month-title">{calendar.month_name[m]} <span class="soft">{y}</span></h2>
      <p class="count">{n} fit{'' if n == 1 else 's'} this month<span class="hint"> · tap a day for the full look</span></p>
    </div>
    <nav class="month-nav" aria-label="Months">{nav(i - 1, 'prev', '‹')}{nav(i + 1, 'next', '›')}</nav>
  </div>
  {calendar_grid(y, m, by_day, root)}
</section>
{rail(all_fits, root)}
</main>"""
    latest = all_fits[-1]
    desc = (f"A daily weather fit, never repeated. Latest: {latest['outfit']}."
            if is_latest else f"Every fit worn in {title}.")
    page_title = "moosewear — the daily fit" if is_latest else f"{title} · moosewear"
    return layout(page_title, body, root, description=desc)


def day_page(f, prev_f, next_f, number):
    root = "../"
    d = d_of(f)

    def link(g, rel, word):
        if not g:
            return ""
        kind, pic = photo(g, root)
        return (f'<a class="{rel}" href="{g["date"]}.html" rel="{rel}">'
                f'<span class="sky sky-{kind}">{pic}</span><span class="txt">'
                f'<small>{word}</small><b>{short_date(d_of(g))}</b></span></a>')

    nav = ""
    if prev_f or next_f:
        nav = (f'<nav class="daynav" aria-label="Other days">'
               f'{link(prev_f, "prev", "← Before")}{link(next_f, "next", "After →")}</nav>'
               '<p class="kbd-hint">Tip: <kbd>←</kbd> <kbd>→</kbd> flip through the days</p>')
    body = f"""<div class="topbar">
  {brand(root, small=True)}
  <a class="pill-link" href="{root}{f['date'][:7]}.html">‹ Calendar</a>
</div>
<main>
<header class="day-head">
  <p class="eyebrow">Fit no. {number} · {d.year}</p>
  <h1>{long_date(d)}</h1>
  <p class="where">📍 {esc(f['location'])}</p>
</header>
{feature(f, root, on_day=True)}
{nav}
</main>"""
    return layout(f"{short_date(d)}, {d.year} · moosewear", body, root,
                  description=f"{long_date(d)}: {f['outfit']}.")


# ---------- build ----------

def load(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT * FROM outfits ORDER BY date")]
    finally:
        con.close()


def build(db, out, images=IMAGES):
    fits = load(db)
    if not fits:
        sys.exit("no outfits in ledger — nothing to build")
    for f in fits:
        f["has_image"] = (images / f"{f['date']}.webp").is_file()

    if out.exists():
        shutil.rmtree(out)
    (out / "day").mkdir(parents=True)
    shutil.copytree(ASSETS, out / "assets")
    if images.is_dir():
        shutil.copytree(images, out / "images")

    by_month = {}
    for f in fits:
        by_month.setdefault(f["date"][:7], []).append(f)
    months = sorted(by_month)

    for key in months:
        page = month_page(key, by_month[key], months, fits)
        (out / f"{key}.html").write_text(page, encoding="utf-8")
    (out / "index.html").write_text(
        month_page(months[-1], by_month[months[-1]], months, fits), encoding="utf-8")

    for i, f in enumerate(fits):
        prev_f = fits[i - 1] if i > 0 else None
        next_f = fits[i + 1] if i < len(fits) - 1 else None
        (out / "day" / f"{f['date']}.html").write_text(
            day_page(f, prev_f, next_f, i + 1), encoding="utf-8")

    public = [{k: v for k, v in f.items() if k != "has_image"} for f in fits]
    (out / "fits.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    return fits, months


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    db = Path(argv[0]) if len(argv) > 0 else ROOT / "wardrobe.db"
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "_site"
    fits, months = build(db, out)
    print(f"built {len(fits)} fits across {len(months)} month(s) -> {out}")


if __name__ == "__main__":
    main()
