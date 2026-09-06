"""Buying and triage — what to pay for a card, and what to do with the ones
already on the shelf.

Deliberately free of Streamlit imports so it can be driven from a script, a
test, or a cron job as well as the UI.

Two jobs, both arithmetic rather than opinion:

  max_buy      the most you can pay and still make your return, worked
               backwards from the money that actually lands
  triage       what to do with a listing you already own — auction it, leave
               it, consign it, or stop listing it one at a time

Every rate here is measured from real payouts, not a fee schedule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Measured over 1,492 real payouts, so promoted-listing spend and per-order
# fees are already inside these numbers.
TAKE_RATE = {"ebay": 0.144, "dc_sports": 0.177, "collx": 0.213}
DEFAULT_TAKE = 0.165

# Envelope, sleeve, top loader, label. Postage on the $0.99 eBay Standard
# Envelope is inside the take rate.
HANDLING = 0.75

# Measured from 1,510 sales and 3,720 live listings on 5 Sep 2026. These are
# not round numbers picked for tidiness — each is where the behaviour changes.
#
#   under $10   3,555 listings, 2.6% carry a watcher, and the whole band is
#               16% of revenue for 64% of the work
#   $10-25        114 listings, 21.9% carry a watcher
#   $25-50         26 listings, 30.8%
#   $50-100        18 listings, 61.1%
#
# So $10 is where cards stop being worth listing individually, and $25 is
# where enough people are watching for an auction to find a bidder.
BULK_CEILING = 10.00
AUCTION_FLOOR = 25.00

# A listing that has not sold in this long is not going to at that price.
STALE_DAYS = 60


@dataclass
class BuySignal:
    """What a card is worth paying for."""
    query: str = ""
    card_id: str = ""
    description: str = ""
    player: str = ""
    number: str = ""
    variant: str = ""
    image: str = ""
    raw: float | None = None
    psa9: float | None = None
    psa10: float | None = None
    sales_7d: int = 0
    sales_30d: int = 0
    gain_pct: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def sits(self) -> bool:
        return self.sales_30d < 5

    @property
    def velocity(self) -> str:
        n = self.sales_30d
        if n >= 100:
            return "very liquid"
        if n >= 30:
            return "liquid"
        if n >= 10:
            return "moves"
        if n >= 3:
            return "slow"
        return "almost never sells"

    def max_buy(self, target_return: float = 0.35,
                platform: str = "ebay") -> float | None:
        price = self.raw
        if not price or price <= 0:
            return None
        take = TAKE_RATE.get(platform, DEFAULT_TAKE)
        net = price * (1 - take) - HANDLING
        if net <= 0:
            return None
        return round(net / (1 + target_return), 2)


# A card that does not trade is not worth its comp. The comp says what the
# last buyer paid; the 30-day count says whether there is a next one. The
# complaint about past buys was never that the price was wrong — it was that
# the cards sat for months, and whoever owns them does the waiting.
VELOCITY_HAIRCUT = [(30, 1.00), (10, 0.85), (5, 0.65), (1, 0.40), (0, 0.00)]


def haircut(sales_30d: int) -> float:
    for floor, mult in VELOCITY_HAIRCUT:
        if sales_30d >= floor:
            return mult
    return 0.0


def net_after_fees(price: float, platform: str = "ebay") -> float:
    """What actually lands from a sale at this price."""
    take = TAKE_RATE.get(platform, DEFAULT_TAKE)
    return round(price * (1 - take) - HANDLING, 2)


# ─── Triage ───────────────────────────────────────────────────────────────────

ACTIONS = ["auction", "keep", "reprice", "consign", "bulk", "end"]

ACTION_LABEL = {
    "auction": "🔨 Auction",
    "keep":    "✅ Leave it",
    "reprice": "🏷️ Reprice",
    "consign": "🚚 Consign",
    "bulk":    "📦 Bulk lot",
    "end":     "🛑 End it",
}


@dataclass
class Listing:
    item_id: str = ""
    sku: str = ""
    title: str = ""
    price: float = 0.0
    watchers: int = 0
    age_days: int | None = None
    fmt: str = ""

    @property
    def net(self) -> float:
        return net_after_fees(self.price)


@dataclass
class Triaged:
    listing: Listing
    action: str
    reason: str
    suggested_start: float = 0.0


def triage(listing: Listing, *,
           bulk_ceiling: float = BULK_CEILING,
           auction_floor: float = AUCTION_FLOOR,
           stale_days: int = STALE_DAYS) -> Triaged:
    """Decide what to do with one listing already on the shelf.

    The ordering matters. Watchers are checked before price, because a watched
    card has told you something no threshold can: somebody wants it and will
    not pay the asking price. That is the definition of an auction candidate.
    """
    L = listing
    stale = L.age_days is not None and L.age_days > stale_days

    # Proven demand, unsold. Auction converts a watcher into a bidder.
    if L.watchers >= 2 and L.price >= auction_floor:
        return Triaged(L, "auction",
                       f"{L.watchers} watching and it still has not sold — "
                       f"they want it, not at that price.", 0.99)
    if L.watchers == 1 and L.price >= auction_floor:
        return Triaged(L, "auction",
                       "One watcher. Enough interest to open low, not enough "
                       "to risk a dollar start.", round(L.price * 0.35, 2))

    # Expensive and nobody watching: the price is the problem, not the format.
    # A no-reserve auction here is how a $400 card leaves for $40.
    if L.price >= 100 and L.watchers == 0:
        return Triaged(L, "reprice",
                       "No watchers at this price. Reprice before you ever "
                       "consider auctioning it — a dollar start on this is a "
                       "donation.")

    # Below the line where listing one at a time pays for the time it takes.
    if L.price < bulk_ceiling:
        net = L.net
        return Triaged(L, "bulk",
                       f"Nets ${net:.2f} after fees. At ~3.6 min a card to "
                       f"list and ship, this band is 64% of the work and 16% "
                       f"of the money.")

    if stale and L.watchers == 0:
        return Triaged(L, "consign",
                       f"{L.age_days} days, no watchers. It is not going to "
                       f"sell here at this price — let a consignor's audience "
                       f"see it.")

    if L.price >= auction_floor:
        return Triaged(L, "keep",
                       "Priced where cards move and not stale yet. Leave it.")

    return Triaged(L, "keep", "Nothing wrong with it — give it more time.")


def triage_all(listings, **kw) -> list:
    return [triage(l, **kw) for l in listings]


def summarise(triaged: list) -> dict:
    """Counts and money by action, for the headline row."""
    out = {}
    for t in triaged:
        a = out.setdefault(t.action, {"count": 0, "ask": 0.0, "net": 0.0})
        a["count"] += 1
        a["ask"] += t.listing.price
        a["net"] += t.listing.net
    for a in out.values():
        a["ask"] = round(a["ask"], 2)
        a["net"] = round(a["net"], 2)
    return out


# ─── Reading an eBay active-listings report ──────────────────────────────────

def _money(v) -> float:
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v) or "") or 0)
    except ValueError:
        return 0.0


def _age_days(start: str, today) -> int | None:
    """How long a listing has been up.

    eBay writes this as "May-31-25 19:56:24 PDT". Parsing only the slashed
    formats returned None for every single row, which silently emptied the
    consign bucket — the one that decides what leaves the shelf. A date parser
    that fails quietly is worse than one that raises.
    """
    import datetime as dt
    s = (start or "").strip()
    if not s:
        return None
    head = s.split()[0]                       # drop the time and the zone
    for fmt in ("%b-%d-%y", "%b-%d-%Y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return (today - dt.datetime.strptime(head, fmt).date()).days
        except ValueError:
            continue
    return None


def read_ebay_report(text_or_rows, today=None) -> list:
    """Parse an eBay active-listings CSV into Listings.

    eBay puts a preamble above the real header, so the header is found by
    looking for the row that contains "Item number" rather than assumed to be
    first — which is how this breaks silently when they change the preamble.
    """
    import csv
    import datetime as dt
    today = today or dt.date.today()

    if isinstance(text_or_rows, str):
        rows = list(csv.reader(text_or_rows.splitlines()))
    else:
        rows = list(text_or_rows)

    hdr = None
    for i, row in enumerate(rows):
        if row and any("Item number" in (c or "") for c in row):
            hdr, rows = row, rows[i + 1:]
            break
    if not hdr:
        return []

    out = []
    for row in rows:
        if len(row) < 10:
            continue
        d = dict(zip(hdr, row))
        price = _money(d.get("Current price") or d.get("Start price"))
        if not price:
            continue
        out.append(Listing(
            item_id=(d.get("Item number") or "").strip(),
            sku=(d.get("Custom label (SKU)") or "").strip(),
            title=(d.get("Title") or "").strip(),
            price=price,
            watchers=int(_money(d.get("Watchers"))),
            age_days=_age_days(d.get("Start date", ""), today),
            fmt=(d.get("Format") or "").strip(),
        ))
    return out

# ─── Slabs ────────────────────────────────────────────────────────────────────
# A graded card is a different card. The 2024 Prizm Jayden Daniels Neon Green
# Pulsar is $20 raw and $34.90 in a PSA 9; the Topps Chrome Sapphire is $18.51
# raw and $80.00 in a PSA 9 — more than four times the raw price. Pricing a
# slab off the raw comp is not a small error, and it is the error that made two
# real cards look six times overpriced when they were not.
#
# So the grade is read off the line the seller typed, and the FMV endpoint is
# asked for that grade specifically.

GRADERS = {
    "psa": "PSA", "bgs": "BGS", "beckett": "BGS", "sgc": "SGC",
    "cgc": "CGC", "csg": "CSG", "hga": "HGA", "ace": "ACE",
}

# "PSA 9", "psa9", "BGS 9.5", "SGC 10", "PSA GEM MT 10", "CGC 9.5"
_GRADE_RE = re.compile(
    r"\b(psa|bgs|beckett|sgc|cgc|csg|hga|ace)[\s\-:]*"      # no \b: "sgc10" has none
    r"(?:gem\s*mt|gem|mint|mt|nm)?[\s\-:]*"
    r"(10(?:\.0)?|9(?:\.5)?|8(?:\.5)?|7(?:\.5)?|6(?:\.5)?|[1-5](?:\.5)?)\b",
    re.I)

# A bare "PSA 10" with no number is still a slab; and "raw"/"ungraded" is
# explicit about not being one.
_RAW_RE = re.compile(r"\b(raw|ungraded|no\s*grade)\b", re.I)


def parse_grade(line: str) -> str:
    """The grade label CardHedger wants ('PSA 9'), or 'Raw'.

    Returns 'Raw' both when the line says so and when it says nothing — an
    ungraded card is the common case and the safe default, because pricing a
    raw card as a slab overpays and that is the expensive direction.
    """
    if _RAW_RE.search(line or ""):
        return "Raw"
    m = _GRADE_RE.search(line or "")
    if not m:
        return "Raw"
    grader = GRADERS.get(m.group(1).lower(), m.group(1).upper())
    num = m.group(2)
    if num.endswith(".0"):
        num = num[:-2]
    return f"{grader} {num}"


def strip_grade(line: str) -> str:
    """The line without its grade, for searching the catalogue.

    "psa 9" in a search query matches nothing useful — the catalogue indexes
    the card, not the slab.
    """
    return re.sub(r"\s{2,}", " ", _GRADE_RE.sub(" ", _RAW_RE.sub(" ", line or ""))).strip()


def is_graded(grade: str) -> bool:
    return bool(grade) and grade.strip().lower() != "raw"
