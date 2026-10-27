#!/usr/bin/env python3
"""Build the moosewear daily-fit calendar site from the ledger.

Reads the wearer's SQLite ledger (default: wardrobe.db in the repo
root) and the per-day images in images/ (named YYYY-MM-DD.webp), and
writes a static site to _site/:

  index.html        the latest month, as a calendar
  <YYYY-MM>.html    one calendar page per month with fits
  day/<date>.html   one page per fit: big image, weather, outfit, why
  fits.json         the raw data, for anything that wants it
  images/           copied through

Standard library only. Run by .github/workflows/pages.yml on every
push to main, and by hand with:  python3 scripts/build_site.py
"""

import calendar
import html
import json
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "wardrobe.db"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "_site"
IMAGES = ROOT / "images"

CSS = """
:root { --ink:#3d2f23; --paper:#fdf8ef; --card:#fffdf7; --line:#e7dbc4;
        --accent:#c46a1b; --muted:#8a765c; }
* { box-sizing: border-box; }
body { margin:0; background:var(--paper); color:var(--ink);
       font-family: ui-rounded, "Segoe UI", system-ui, sans-serif; }
main { max-width: 880px; margin: 0 auto; padding: 20px 14px 48px; }
h1 { font-family: Georgia, "Times New Roman", serif; font-weight: 600;
     font-size: clamp(28px, 6vw, 44px); margin: 8px 0 2px; }
.sub { color: var(--muted); margin: 0 0 20px; }
h2.month { font-family: Georgia, serif; font-weight: 600;
           font-size: clamp(20px, 4.5vw, 28px); margin: 18px 0 10px;
           display:flex; justify-content:space-between; align-items:baseline; }
h2.month nav a { font-size: 15px; color: var(--accent); text-decoration:none;
                 margin-left: 14px; font-family: inherit; }
table.cal { width:100%; border-collapse: separate; border-spacing: 4px;
            table-layout: fixed; }
table.cal th { color: var(--muted); font-weight: 600; font-size: 12px;
               text-transform: uppercase; letter-spacing: .04em; padding: 2px 0; }
table.cal td { background: var(--card); border: 1px solid var(--line);
               border-radius: 10px; vertical-align: top; padding: 4px;
               height: 1px; }
td.empty-cell { background: transparent; border: none; }
td.plain .d { color: var(--muted); }
td .d { font-size: 12px; font-weight: 700; display:block; }
td a { color: inherit; text-decoration: none; display: block; }
td img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 7px;
         display: block; margin-top: 2px; }
td .cond { display:block; font-size: 10px; color: var(--muted);
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
td.today { outline: 2px solid var(--accent); outline-offset: -2px; }
.feature { margin-top: 28px; background: var(--card); border:1px solid var(--line);
           border-radius: 14px; padding: 16px; display: grid;
           grid-template-columns: 180px 1fr; gap: 16px; }
.feature img { width: 100%; border-radius: 10px; display:block; }
.feature h3 { margin: 2px 0 6px; font-family: Georgia, serif; }
.wx { color: var(--accent); font-weight: 600; }
p.why { color: var(--muted); }
.day img.big { width: min(420px, 100%); border-radius: 14px; display:block;
               margin: 10px 0; }
.daynav { display:flex; justify-content:space-between; margin-top: 24px; }
.daynav a, .back { color: var(--accent); text-decoration: none; font-weight: 600; }
footer { margin-top: 40px; color: var(--muted); font-size: 13px;
         border-top: 1px solid var(--line); padding-top: 12px; }
@media (max-width: 560px) {
  table.cal { border-spacing: 2px; }
  td .cond { display: none; }
  .feature { grid-template-columns: 1fr; }
  .feature img { max-width: 240px; }
}
"""

FOOTER = ("<footer>Every morning: check the weather, dress for it, never "
          "repeat. Served from the moosewear ledger (<code>wardrobe.db</code>) "
          "by a GitHub Action on every push to <code>main</code>.</footer>")


def esc(s):
    return html.escape(str(s), quote=True)


def wx_line(f):
    return (f"{esc(f['condition'])} · high {f['high_f']}°F / low "
            f"{f['low_f']}°F · {f['precip_pct']}% precip")


def month_page(month_key, fits, months_sorted):
    y, m = (int(p) for p in month_key.split("-"))
    by_day = {int(f["date"][8:10]): f for f in fits}
    idx = months_sorted.index(month_key)
    prev_link = (f'<a href="{months_sorted[idx-1]}.html">← {months_sorted[idx-1]}</a>'
                 if idx > 0 else "")
    next_link = (f'<a href="{months_sorted[idx+1]}.html">{months_sorted[idx+1]} →</a>'
                 if idx < len(months_sorted) - 1 else "")
    home = '<a href="index.html">Latest</a>' if month_key != months_sorted[-1] else ""
    weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(y, m)
    rows = []
    for week in weeks:
        cells = []
        for d in week:
            if d == 0:
                cells.append('<td class="empty-cell"></td>')
            elif d in by_day:
                f = by_day[d]
                cells.append(
                    f'<td><a href="day/{f["date"]}.html"><span class="d">{d}</span>'
                    f'<img src="images/{f["date"]}.webp" alt="Fit for {f["date"]}" '
                    f'loading="lazy"><span class="cond">{esc(f["condition"])}</span>'
                    f"</a></td>")
            else:
                cells.append(f'<td class="plain"><span class="d">{d}</span></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    title = f"{calendar.month_name[m]} {y}"
    latest = fits[-1]
    feature = ""
    if month_key == months_sorted[-1]:
        feature = f"""
<section class="feature">
  <a href="day/{latest['date']}.html"><img src="images/{latest['date']}.webp"
     alt="Latest fit"></a>
  <div>
    <h3>Latest fit — {esc(latest['date'])}</h3>
    <p class="wx">{wx_line(latest)}</p>
    <p>{esc(latest['outfit'])}</p>
    <p class="why">{esc(latest['reason'])}</p>
  </div>
</section>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>moosewear — {esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>🧥 moosewear</h1>
<p class="sub">A daily weather fit, never repeated. Tap a day for the full look.</p>
<h2 class="month">{esc(title)}<nav>{prev_link}{home}{next_link}</nav></h2>
<table class="cal">
<tr><th>Sun</th><th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th><th>Sat</th></tr>
{''.join(rows)}
</table>
{feature}
{FOOTER}
</main>
</body>
</html>
"""


def day_page(f, prev_f, next_f):
    prev_link = (f'<a href="{prev_f["date"]}.html">← {prev_f["date"]}</a>'
                 if prev_f else "<span></span>")
    next_link = (f'<a href="{next_f["date"]}.html">{next_f["date"]} →</a>'
                 if next_f else "<span></span>")
    d = date.fromisoformat(f["date"])
    title = d.strftime("%A, %B %-d, %Y")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>moosewear — {esc(f['date'])}</title>
<style>{CSS}</style>
</head>
<body>
<main class="day">
<a class="back" href="../index.html">← Calendar</a>
<h1>{esc(title)}</h1>
<p class="wx">{wx_line(f)} · {esc(f['location'])}</p>
<img class="big" src="../images/{f['date']}.webp" alt="Moose in the {f['date']} fit">
<p>{esc(f['outfit'])}</p>
<p class="why">{esc(f['reason'])}</p>
<div class="daynav">{prev_link}{next_link}</div>
{FOOTER}
</main>
</body>
</html>
"""


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    fits = [dict(r) for r in con.execute("SELECT * FROM outfits ORDER BY date")]
    if not fits:
        sys.exit("no outfits in ledger — nothing to build")

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "day").mkdir(parents=True)
    shutil.copytree(IMAGES, OUT / "images")

    by_month = {}
    for f in fits:
        by_month.setdefault(f["date"][:7], []).append(f)
    months_sorted = sorted(by_month)

    for key in months_sorted:
        page = month_page(key, by_month[key], months_sorted)
        (OUT / f"{key}.html").write_text(page, encoding="utf-8")
    latest_key = months_sorted[-1]
    (OUT / "index.html").write_text(
        month_page(latest_key, by_month[latest_key], months_sorted),
        encoding="utf-8")

    for i, f in enumerate(fits):
        prev_f = fits[i - 1] if i > 0 else None
        next_f = fits[i + 1] if i < len(fits) - 1 else None
        (OUT / "day" / f"{f['date']}.html").write_text(
            day_page(f, prev_f, next_f), encoding="utf-8")

    (OUT / "fits.json").write_text(json.dumps(fits, indent=2), encoding="utf-8")
    print(f"built {len(fits)} fits across {len(months_sorted)} month(s) -> {OUT}")


if __name__ == "__main__":
    main()
