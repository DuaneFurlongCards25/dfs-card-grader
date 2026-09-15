"""Shelf health, lot evaluation, grading outcomes and targets.

Arithmetic for the Feature Buildout spec (items 2, 3, 5 and 8), kept free of
Streamlit like dfs_buying and dfs_breaks so it can be tested against real
files and driven from a script.

## Piles — the tiers, and why they are not quite what the spec wrote

The spec's piles are Singles $1-3, Doubles $4-6, Triples $6-10, Home Runs $10+.
Read literally that leaves $3.00-$3.99 in no pile at all, and puts $6.00 in
two. On the 14 Sep 2026 report the $3.00-$3.99 band is the single largest
group of dead stock — 414 of the 882 listings — so the gap is not a rounding
detail.

The clearance file Duane actually ran that day
(eBay_FileExchange_Revise_DeadStock_Clearance_2026-09-14.csv) had already
settled it: $3.00-$3.99 was priced with the Doubles. The boundaries here are
taken from that file, not from the prose, so the app reproduces what was
already uploaded:

    Singles    under $3.00
    Doubles    $3.00 - $5.99
    Triples    $6.00 - $9.99
    Home Runs  $10.00 and up

## Dead stock — "180 days" means strictly over 180

Age > 180 with zero watchers gives 882 on the 14 Sep report, matching the
spec's fixture. Age >= 180 gives 986. The spec's prose says "≥ 180" but its
number says "> 180"; the number is what was actually acted on.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re

import dfs_buying as buying

# ─── Piles ────────────────────────────────────────────────────────────────────

PILES = ["singles", "doubles", "triples", "home_runs"]
PILE_LABEL = {"singles": "Singles", "doubles": "Doubles",
              "triples": "Triples", "home_runs": "Home Runs"}

# Lower bound of each pile. See the module docstring for why $3 is a Double.
DOUBLES_FROM = 3.00
TRIPLES_FROM = 6.00
HOME_RUN_FROM = 10.00


def pile(price) -> str:
    p = buying._money(price)
    if p >= HOME_RUN_FROM:
        return "home_runs"
    if p >= TRIPLES_FROM:
        return "triples"
    if p >= DOUBLES_FROM:
        return "doubles"
    return "singles"


# ─── Dead stock ──────────────────────────────────────────────────────────────

DEAD_AGE_DAYS = 180          # strictly older than this
AGE_BUCKETS = [(0, 30, "0-30"), (31, 60, "31-60"), (61, 90, "61-90"),
               (91, 180, "91-180"), (181, 365, "181-365"), (366, None, "365+")]

# What each pile is floored to. Home Runs are never auto-priced.
DEFAULT_FLOORS = {"singles": 0.99, "doubles": 1.99, "triples": 3.99}

# Duane's standing rule: these players' cards only ever get priced UP. A floor
# is by definition a price cut, so they go to manual review instead — even
# though the 14 Sep dead set happens to contain none of them.
NEVER_PRICE_DOWN = re.compile(r"\b(ohtani|messi|yamal|haaland)\b", re.I)

INFO_ROW = ["Info", "Version=1.0.0", "Template=fx_category_template_EBAY_US", "", ""]
REVISE_HEADER = ["*Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)",
                 "ItemID", "CustomLabel", "*StartPrice"]


def age_bucket(age_days) -> str | None:
    if age_days is None:
        return None
    for lo, hi, name in AGE_BUCKETS:
        if age_days >= lo and (hi is None or age_days <= hi):
            return name
    return None


def is_dead(listing, age_days: int = DEAD_AGE_DAYS) -> bool:
    return (listing.age_days is not None and listing.age_days > age_days
            and listing.watchers == 0)


def shelf_health(listings, age_days: int = DEAD_AGE_DAYS) -> dict:
    """Bucket counts across the whole shelf, plus the dead-stock set."""
    buckets = {name: 0 for _, _, name in AGE_BUCKETS}
    undated = 0
    for l in listings:
        b = age_bucket(l.age_days)
        if b is None:
            undated += 1
        else:
            buckets[b] += 1
    dead = [l for l in listings if is_dead(l, age_days)]
    by_pile = {p: [] for p in PILES}
    for l in dead:
        by_pile[pile(l.price)].append(l)
    return {"listings": len(listings), "buckets": buckets, "undated": undated,
            "dead": dead, "by_pile": by_pile}


def clearance_plan(dead, floors: dict | None = None) -> dict:
    """Split dead stock into an auto-revise set and a manual-review set.

    Three guards, each of which a naive "set everything to the floor" misses:
      * Home Runs ($10+) are never auto-priced — spec requirement.
      * NEVER_PRICE_DOWN players go to review, not to a cut.
      * A floor never RAISES a price. A $0.75 card is left alone rather than
        "cleared" to $0.99.
    """
    floors = {**DEFAULT_FLOORS, **(floors or {})}
    revise, review, unchanged = [], [], []
    for l in dead:
        p = pile(l.price)
        if p == "home_runs":
            review.append((l, "Home Run — $10+, price it by hand"))
            continue
        if NEVER_PRICE_DOWN.search(l.title or ""):
            review.append((l, "Star player — only ever priced up"))
            continue
        floor = round(float(floors[p]), 2)
        # Strictly below: a card already AT the floor still gets a row, which
        # is what the 14 Sep clearance file did (two $0.99 cards -> $0.99).
        # Only a card below the floor is left alone, so nothing is raised.
        if l.price < floor:
            unchanged.append(l)
            continue
        revise.append((l, floor))
    return {"revise": revise, "review": review, "unchanged": unchanged}


def revise_csv(revise) -> str:
    """eBay File Exchange Revise file, byte-for-byte the shape of the ones in
    this folder: Info row padded to five fields, LF line endings."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(INFO_ROW)
    w.writerow(REVISE_HEADER)
    for l, price in revise:
        w.writerow(["Revise", l.item_id, l.sku, f"{price:.2f}"])
    return buf.getvalue()


def review_csv(review) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["ItemID", "CustomLabel", "Title", "Price", "Age (days)", "Why"])
    for l, why in review:
        w.writerow([l.item_id, l.sku, l.title, f"{l.price:.2f}", l.age_days, why])
    return buf.getvalue()


# ─── Bulk lot evaluator ──────────────────────────────────────────────────────

_VALUE_RE = re.compile(r"\$?\s*(\d[\d,]*(?:\.\d{1,2})?)\s*$")


def parse_checklist(text: str) -> list:
    """One card per line, value last: 'Jaxson Dart Prizm Silver, 12.50'.

    Lines with no trailing value are kept with value None and reported, rather
    than dropped — a checklist that silently loses rows gives a verdict on a
    lot that is not the one being bought.
    """
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip().rstrip(",;\t ")
        if not line:
            continue
        m = _VALUE_RE.search(line)
        if m:
            name = line[:m.start()].strip().rstrip(",;\t -")
            out.append({"card": name or line, "value": buying._money(m.group(1))})
        else:
            out.append({"card": line, "value": None})
    return out


def evaluate_bulk_lot(cards, lot_cost, target_return: float = 0.35,
                      platform: str = "ebay") -> dict:
    """Two verdicts on one prospective lot, shown side by side.

    STRIKE / PASS is the ops-blueprint rule: at least one Home Run, and the
    Home Runs alone cover the lot price. The rest of the lot is upside.

    The 35% check is Duane's own buying rule, the one max_buy() already
    implements: every card's net after the measured 14.4% take and $0.75
    handling, and the lot has to clear its price by 35%. Neither replaces
    the other — a lot can strike on one big hit while failing 35% overall.
    """
    cost = buying._money(lot_cost)
    tiers = {p: {"count": 0, "value": 0.0, "net": 0.0} for p in PILES}
    unvalued = []
    home_run_value = 0.0
    total_net = 0.0
    for c in cards or []:
        v = c.get("value")
        if v is None:
            unvalued.append(c)
            continue
        p = pile(v)
        net = max(buying.net_after_fees(v, platform), 0.0)
        t = tiers[p]
        t["count"] += 1
        t["value"] = round(t["value"] + v, 2)
        t["net"] = round(t["net"] + net, 2)
        total_net += net
        if p == "home_runs":
            home_run_value += v

    strike = tiers["home_runs"]["count"] >= 1 and home_run_value >= cost > 0
    needed = round(cost * (1 + target_return), 2)
    total_net = round(total_net, 2)
    return {
        "tiers": tiers,
        "unvalued": unvalued,
        "cards": sum(t["count"] for t in tiers.values()),
        "gross": round(sum(t["value"] for t in tiers.values()), 2),
        "home_run_value": round(home_run_value, 2),
        "strike": strike,
        "strike_verdict": ("STRIKE: Profit secured. Home runs cover the lot."
                           if strike else "PASS: Margin insufficient."),
        "net": total_net,
        "needed_net": needed,
        "return_pct": round((total_net - cost) / cost * 100, 1) if cost else None,
        "meets_return": cost > 0 and total_net >= needed,
        "max_pay": round(total_net / (1 + target_return), 2),
    }


# ─── Grading outcomes ────────────────────────────────────────────────────────

BIG_RAW = 500.00         # above this raw cost the rule relaxes to 1.5x


def two_x_rule(est_psa10, raw_cost, grading_fee) -> dict:
    """Did the submission clear the 2x rule when it was sent?

    est. PSA 10 value >= 2 x (raw cost + grading fee), or 1.5x when raw cost
    is over $500. Judged on the estimate at submission — whether the card
    then graded a 10 is a separate question the gem rate answers.
    """
    est = buying._money(est_psa10)
    raw = buying._money(raw_cost)
    fee = buying._money(grading_fee)
    mult = 1.5 if raw > BIG_RAW else 2.0
    need = round(mult * (raw + fee), 2)
    return {"passed": est > 0 and est >= need, "multiple": mult,
            "needed": need, "est": est}


def _grade_num(g):
    m = re.search(r"(\d+(?:\.\d)?)", str(g or ""))
    return float(m.group(1)) if m else None


def gem_rate(rows, last_n: int = 20, grade_key: str = "grade_returned",
             date_key: str = "graded_date", low: float = 50.0,
             high: float = 90.0) -> dict:
    """Share of the last N graded submissions that came back a 10.

    Only rows with a grade count. A gem rate over ungraded rows is not a
    placeholder, it is a wrong number.
    """
    graded = [r for r in (rows or []) if _grade_num(r.get(grade_key)) is not None]
    graded.sort(key=lambda r: str(r.get(date_key) or r.get("date_submitted")
                                  or r.get("date_added") or ""), reverse=True)
    window = graded[:last_n]
    tens = sum(1 for r in window if _grade_num(r.get(grade_key)) == 10.0)
    rate = round(tens / len(window) * 100, 1) if window else None
    flag = None
    if rate is not None:
        if rate < low:
            flag = "low"
        elif rate > high:
            flag = "high"
    return {"graded": len(window), "tens": tens, "rate": rate, "flag": flag}


# ─── Targets ─────────────────────────────────────────────────────────────────

WEEK_NET_TARGET = 1000.00
MONTH_GROSS_TARGET = 30000.00
MONTH_PROFIT_TARGET = (8000.00, 9000.00)


def _sale_date(r):
    s = str(r.get("sale_date") or "")[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def targets(sales, today: dt.date | None = None, cost_of=None) -> dict:
    """This week and this month against Duane's goals.

    Weeks run Monday-Sunday. `cost_of(sale)` returns what that card cost, or
    None when no cost is on record. Without it, "profit" is net proceeds after
    platform fees only — which overstates profit by the cost of every card, so
    the result says which one it is instead of letting the label decide.
    """
    today = today or dt.date.today()
    wk_start = today - dt.timedelta(days=today.weekday())
    mo_start = today.replace(day=1)

    def roll(start):
        rows = [r for r in (sales or []) if (d := _sale_date(r)) and start <= d <= today]
        gross = sum(buying._money(r.get("gross_revenue")) for r in rows)
        net = sum(buying._money(r.get("net_proceeds")) for r in rows)
        cost, uncosted = 0.0, 0
        if cost_of:
            for r in rows:
                c = cost_of(r)
                if c is None:
                    uncosted += 1
                else:
                    cost += c
        return {"sales": len(rows), "gross": round(gross, 2), "net": round(net, 2),
                "cost": round(cost, 2), "uncosted": uncosted,
                "profit": round(net - cost, 2)}

    wk, mo = roll(wk_start), roll(mo_start)
    basis = "after card cost" if cost_of else "after fees only"
    return {
        "basis": basis,
        "week": {**wk, "start": wk_start, "target": WEEK_NET_TARGET,
                 "pct": round(wk["profit"] / WEEK_NET_TARGET * 100, 1)},
        "month": {**mo, "start": mo_start,
                  "gross_target": MONTH_GROSS_TARGET,
                  "gross_pct": round(mo["gross"] / MONTH_GROSS_TARGET * 100, 1),
                  "profit_target": MONTH_PROFIT_TARGET,
                  "profit_pct": round(mo["profit"] / MONTH_PROFIT_TARGET[0] * 100, 1)},
    }


# ─── Cost of a sold card (for true profit and portfolio cost basis) ──────────

def cost_resolver(lots, card_purchases=None):
    """Return cost_of(sku) -> per-card cost, or None when none is on record.

    Mirrors the Purchases tab's prefix rule exactly — longest registered prefix
    or alias wins, a trailing '*' alias matches without a dash — because a
    second, slightly different matcher would give P&L by Lot and the targets
    two different answers for the same sale. Deliberately NO first-two-segments
    fallback: that fallback invents a one-card "lot" with no cost, and a cost
    of None is honest where a guess is not.

    Per-card cost is the lot's total / its card count. A lot with no card count
    cannot be split, so its cards come back None rather than as the whole lot.
    Individual purchases match on the exact SKU and win over a lot.
    """
    per_card, known = {}, []
    for l in lots or []:
        if l.get("is_break"):
            continue
        pfx = str(l.get("lot_prefix") or "").strip().upper()
        if not pfx:
            continue
        n = int(buying._money(l.get("card_count")))
        cost = (buying._money(l.get("total_cost")) + buying._money(l.get("ship_cost"))) / n if n > 0 else None
        for p in [pfx] + [a.strip().upper() for a in str(l.get("alias_prefixes") or "").split(",") if a.strip()]:
            per_card[p] = cost
            known.append(p)
    known.sort(key=len, reverse=True)
    singles = {}
    for c in card_purchases or []:
        s = str(c.get("sku") or "").strip().upper()
        if s:
            q = max(int(buying._money(c.get("quantity")) or 1), 1)
            singles[s] = buying._money(c.get("cost_paid")) / q

    def cost_of(sku):
        s = str(sku or "").strip().upper()
        if not s:
            return None
        if s in singles:
            return round(singles[s], 2)
        for p in known:
            if (p.endswith("*") and s.startswith(p[:-1])) or s == p or s.startswith(p + "-"):
                c = per_card[p]
                return round(c, 2) if c is not None else None
        return None
    return cost_of


# ─── Unlisted inventory ──────────────────────────────────────────────────────

UNLISTED_WARN_DAYS = 3


def unlisted(lot_cards, live_skus, sold_skus, today=None,
             warn_days: int = UNLISTED_WARN_DAYS) -> dict:
    """Cards sitting in a Purchases lot that are neither live on eBay nor sold.

    Age runs from when the card was imported into its lot. 'Live' must come
    from a CURRENT active-listings report: the listings table keeps rows for
    listings that have since ended, so an old sync would count ended cards as
    listed and hide exactly the cards this exists to find.
    """
    today = today or dt.date.today()
    live = {str(s).strip().upper() for s in live_skus or [] if s}
    sold = {str(s).strip().upper() for s in sold_skus or [] if s}
    rows = []
    for c in lot_cards or []:
        sku = str(c.get("sku") or "").strip()
        if not sku or sku.upper() in live or sku.upper() in sold:
            continue
        try:
            made = dt.date.fromisoformat(str(c.get("created_at") or "")[:10])
            age = (today - made).days
        except ValueError:
            age = None
        flag = "red" if age is not None and age > warn_days * 2 else (
               "yellow" if age is not None and age > warn_days else "")
        rows.append({"lot": c.get("lot_prefix"), "sku": sku, "title": c.get("title"),
                     "age": age, "flag": flag})
    rows.sort(key=lambda r: -(r["age"] if r["age"] is not None else -1))
    total = len([c for c in lot_cards or [] if str(c.get("sku") or "").strip()])
    return {"in_lots": total, "unlisted": rows,
            "oldest": rows[0]["age"] if rows else None}


# ─── Numbered parallels ──────────────────────────────────────────────────────

SERIAL_RE = re.compile(r"^\s*#?\s*(?:\d{1,5}\s*)?/\s*(\d{1,5})\s*$")


def parse_serial(v):
    """Print run as an int. '/75', '#/75', '75' -> 75; '1/1' -> 1;
    '#106/125' -> 125 (the number after the slash is the run, the one before
    it is which copy). Anything else -> None."""
    s = str(v or "").strip()
    if not s:
        return None
    m = SERIAL_RE.match(s) or re.match(r"^\s*(\d{1,5})\s*$", s)
    return int(m.group(1)) if m else None


def serial_multiplier(serial, mode: str = "off", flat_pct: float = 15.0,
                      tiers=((25, 50.0), (99, 25.0))) -> float:
    """Premium applied on top of CardHedger FMV for a numbered card.

    Starts OFF. Duane has not set a value, and the spec says not to bake one
    in; the multiplier is shown and editable wherever it is used.
    `tiers` is (print run or tighter, % premium), tightest first.
    """
    n = parse_serial(serial)
    if n is None or mode == "off":
        return 1.0
    if mode == "flat":
        return round(1 + flat_pct / 100, 4)
    for run, pct in sorted(tiers):
        if n <= run:
            return round(1 + pct / 100, 4)
    return 1.0


# ─── Box-Row-Position ────────────────────────────────────────────────────────

LOCATION_RE = re.compile(r"^\s*B\s*(\d+)\s*-?\s*R\s*(\d+)\s*-?\s*P\s*(\d+)\s*$", re.I)


def normalize_location(v):
    """'b1-r2-p3' / 'B1 - R2 - P3' -> 'B1-R2-P3'. Invalid -> None."""
    m = LOCATION_RE.match(str(v or ""))
    return f"B{int(m.group(1))}-R{int(m.group(2))}-P{int(m.group(3))}" if m else None


def append_location(description: str, location) -> str:
    """End the eBay description with the location tag, once."""
    loc = normalize_location(location)
    desc = description or ""
    if not loc:
        return desc
    tag = f"Location: {loc}"
    desc = re.sub(r"\s*(?:<p>)?Location:\s*B\d+-R\d+-P\d+(?:</p>)?\s*$", "", desc)
    return f"{desc}<p>{tag}</p>" if "<" in desc else (f"{desc}\n{tag}" if desc else tag)
