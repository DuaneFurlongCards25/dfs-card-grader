"""Find listings that are stale but demonstrably sell — the relist shortlist.

The question this answers is not "what is old" and not "what is valuable". It
is: **which cards have proven demand and a listing that has gone cold?**

Those are the only ones worth spending time relisting. A card nobody has
bought stays unsold on a fresh listing too; a card that sells regularly and
has been sitting 150 days is a listing problem, not an inventory problem.

Demand proof comes from Duane's OWN eBay sales, not a third-party comp:

  * the **player** sold in the last 90 days  — the hard requirement
  * the **set** sold in the last 90 days     — secondary weight

Requiring the player is deliberate. Scoring on set alone put a $405 Konnor
Griffin auto at the top of the list with zero player sales behind it, purely
because Bowman's Best sells 23 cards a quarter.

## Relisting does NOT mean rescanning

A relist must never go back through Haystack. A scan is $0.18 and the card is
already catalogued — the photos, description and specifics exist on the live
listing. The path is: end here, then eBay Seller Hub → **Sell Similar**, which
carries the photos and description across at no cost. This module therefore
produces an END file and a worksheet, never a Haystack input file.
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import io
import re

STALE_DAYS = 45          # a listing younger than this has not had its chance
                         # Duane's number. It barely changes the shortlist —
                         # the top 50 have a median age of 125-150 days whether
                         # the cutoff is 30 or 90 — but it keeps recently
                         # relisted cards out of a list about relisting.
MAX_PER_PLAYER = 3       # first pass returned 18 Nick Kurtz cards out of 50
PRICE_CEILING = 200.0    # the big autos are held back by hand, not by a rule

SETS = [
    "Bowman's Best", "Bowman Draft", "Bowman Chrome", "Bowman Mega Box",
    "Bowman University", "Bowman", "Topps Chrome Sapphire",
    "Topps Cosmic Chrome", "Topps Chrome", "Topps Finest", "Topps Resurgence",
    "Topps Update", "Topps Heritage", "Topps", "Panini Prizm", "Panini Select",
    "Panini Mosaic", "Donruss Optic", "Panini Donruss", "Panini",
]


def _money(v) -> float:
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v) or "") or 0)
    except ValueError:
        return 0.0


def _date(s):
    s = (s or "").split()[0] if s else ""
    for fmt in ("%b-%d-%y", "%b-%d-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def set_of(title: str) -> str:
    """Longest set name present, so 'Bowman's Best' wins over 'Bowman'."""
    low = (title or "").lower()
    return next((s for s in SETS if s.lower() in low), "")


def player_of(title: str) -> str:
    """The player, read off the ALL-CAPS run the title format puts first.

    Case-insensitive fallback matters: four Pete Crow-Armstrong sales were
    undercounted as three because one title was in title case, and the caps
    run missed it entirely.
    """
    m = re.search(r"\b([A-Z][A-Z'.\-]{1,}(?:\s+[A-Z][A-Z'.\-]{1,}){1,2})\b",
                  title or "")
    if m:
        return m.group(1).strip()
    # Title-case fallback: scan token by token and take the longest run of
    # capitalised words that are not set/brand vocabulary.
    #
    # A phrase regex does not work here. On "2024 Bowman Chrome Pete
    # Crow-Armstrong #45" it matches "Bowman Chrome Pete" as one phrase,
    # discards all three for containing "Bowman", and resumes past "Pete" —
    # leaving "Crow-Armstrong" alone and unmatchable. That undercounted Pete
    # Crow-Armstrong's sales as 3 when he had 4.
    stop = {w.lower() for s in SETS for w in s.split()}
    stop |= {"mega", "box", "refractor", "chrome", "rookie", "rookies",
             "prospect", "prospects", "series", "update", "stars",
             "anniversary", "edition", "variation", "auto", "the", "of"}
    best, run = [], []
    for w in (title or "").split():
        core = w.strip("()[],#")
        ok = (bool(re.match(r"^[A-Z][A-Za-z'.\-]+$", core))
              and core.lower().strip(".'-") not in stop
              and not re.search(r"\d", core))
        if ok:
            run.append(core)
        else:
            if len(run) > len(best):
                best = run
            run = []
    if len(run) > len(best):
        best = run
    return " ".join(best).upper() if len(best) >= 2 else ""


def _rows(text_or_rows, key_col):
    if isinstance(text_or_rows, str):
        rows = list(csv.reader(io.StringIO(text_or_rows)))
    else:
        rows = list(text_or_rows)
    for i, r in enumerate(rows):
        if r and any(key_col in (c or "") for c in r):
            return r, rows[i + 1:]
    return None, []


def demand_from_orders(text, sport: str = "") -> dict:
    """Count sales per player and per set from an eBay orders report."""
    hdr, body = _rows(text, "Sales Record Number")
    players, sets_, revenue = collections.Counter(), collections.Counter(), collections.Counter()
    total = 0
    for r in body:
        if len(r) < 30:
            continue
        d = dict(zip(hdr, r))
        t = (d.get("Item Title") or "").strip()
        price = _money(d.get("Sold For"))
        if not t or not price:
            continue
        if sport:
            try:
                import sys
                sys.path.insert(0, "/Users/duanefurlong/Desktop/PriceDesk")
                from pricing.sportword import decide
                if decide(t)[0] != sport:
                    continue
            except Exception:
                pass
        total += 1
        p = player_of(t)
        if p and len(p) > 4:
            players[p] += 1
            revenue[p] += price
        s = set_of(t)
        if s:
            sets_[s] += 1
    return {"players": players, "sets": sets_, "revenue": revenue, "total": total}


def candidates(listings_text, demand: dict, *, sport: str = "",
               stale_days: int = STALE_DAYS, limit: int = 50,
               per_player: int = MAX_PER_PLAYER,
               ceiling: float = PRICE_CEILING,
               exclude: set | None = None, today=None) -> list:
    """Stale listings whose player has proven demand, best first."""
    today = today or dt.date.today()
    exclude = exclude or set()
    hdr, body = _rows(listings_text, "Item number")
    if not hdr:
        return []
    players, sets_ = demand["players"], demand["sets"]
    out = []
    for r in body:
        if len(r) < 10:
            continue
        d = dict(zip(hdr, r))
        t = (d.get("Title") or "").strip()
        price = _money(d.get("Current price") or d.get("Start price"))
        if not t or not price or price > ceiling:
            continue
        item = (d.get("Item number") or "").strip()
        if item in exclude:
            continue
        if sport:
            try:
                import sys
                sys.path.insert(0, "/Users/duanefurlong/Desktop/PriceDesk")
                from pricing.sportword import decide
                if decide(t)[0] != sport:
                    continue
            except Exception:
                pass
        start = _date(d.get("Start date", ""))
        age = (today - start).days if start else 999
        if age < stale_days:
            continue
        p, s = player_of(t), set_of(t)
        psales = players.get(p, 0)
        if not psales:                      # the hard requirement
            continue
        ssales = sets_.get(s, 0)
        watch = int(_money(d.get("Watchers")))
        score = (psales * 30 + min(ssales, 62) * 0.4 + price * 2.0
                 + min(age, 200) * 0.08 + watch * 10)
        out.append({
            "item": item, "sku": (d.get("Custom label (SKU)") or "").strip(),
            "title": t, "price": price, "watchers": watch, "age": age,
            "player": p, "set": s, "player_sales": psales, "set_sales": ssales,
            "score": round(score, 1),
        })
    out.sort(key=lambda x: -x["score"])
    seen, picked = collections.Counter(), []
    for x in out:
        if seen[x["player"]] >= per_player:
            continue
        seen[x["player"]] += 1
        picked.append(x)
        if len(picked) >= limit:
            break
    return picked


INFO = ["Info", "Version=1.0.0", "Template=fx_category_template_EBAY_US"]
ACTION = "*Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)"


def end_csv(rows: list) -> str:
    """File Exchange End file. Relist afterwards with Seller Hub Sell Similar."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(INFO)
    w.writerow([ACTION, "ItemID", "EndCode"])
    for x in rows:
        w.writerow(["End", x["item"], "NotAvailable"])
    return buf.getvalue()


def worksheet_csv(rows: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["ItemID", "SKU", "Price", "AgeDays", "Watchers", "Player",
                "PlayerSales90d", "Set", "SetSales90d", "Score", "Title"])
    for x in rows:
        w.writerow([x["item"], x["sku"], f'{x["price"]:.2f}', x["age"],
                    x["watchers"], x["player"], x["player_sales"], x["set"],
                    x["set_sales"], x["score"], x["title"]])
    return buf.getvalue()
