"""Intake — one scan, one card record, every channel fed from it.

The Burbank model in one sentence: a card enters through one door, gets an
identity and a location at that moment, and everything afterwards (eBay,
website, Instagram, a pull ticket when it sells) is generated from that single
record. Nothing is re-keyed and nothing depends on a channel to remember it.

## Why the scanner export is the right feed

The phone app does not keep the cards — it uploads them and moves on. That
looked like a gap until the export was read: it carries SKU, title, price,
**ten image URLs**, condition, grade, description and the full item specifics
(sport, player, season, manufacturer, parallel, set, team, card number).

That is strictly more than the eBay report has ever given us. eBay tells you a
card is listed; the export tells you what the card IS. A card can only reach a
website or Instagram if its photos and specifics live somewhere we own, and
this is where they come from.

## Verified against both tools

A Heystack stack export and a Card Dealer Pro export are the same 39-column
eBay File Exchange shape (checked 2 Oct 2026 on GIRKSWHATNOT 10-01-26: three
cards, unique SKUs, 10 images and 14 specifics each). Heystack's Custom Name
strategy gives every card its own SKU — {eBay Custom Label}-{position}-{random}
— and once generated that SKU is saved to the card and reused on later
listings, which is what makes it usable as a durable identity.

## Two scanners, one pipe

Card Dealer Pro and Haystack One both publish eBay File Exchange files, so both
are read by header NAME rather than position. A column that moves, or is
spelled differently between the two tools, must not silently become a card
with no player on it.

## What this module will not do

It will not invent an identity. A row with no SKU is reported, not given a
generated one — a made-up SKU is a card that can never be matched back to the
listing it came from.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re

# Header aliases. Card Dealer Pro and Haystack One differ in wording; eBay's
# own template differs again. Matched case-insensitively, longest first.
FIELDS = {
    "sku":          ["custom label (sku)", "customlabel", "custom label", "sku"],
    "title":        ["title", "*title"],
    "price":        ["start price", "*startprice", "startprice", "price"],
    "images":       ["item photo url", "picurl", "pic url", "photo url"],
    "condition":    ["cd:card condition - (id: 40001)", "condition", "condition id"],
    "grader":       ["cd:professional grader - (id: 27501)", "grader"],
    "grade":        ["cd:grade - (id: 27502)", "grade"],
    "cert_number":  ["cda:certification number - (id: 27503)", "certification number"],
    "description":  ["description", "*description"],
    "sport":        ["c:sport", "*c:sport", "sport"],
    "player":       ["c:player/athlete", "*c:player/athlete", "player"],
    "year":         ["c:season", "*c:season", "season", "year"],
    "manufacturer": ["c:manufacturer", "*c:manufacturer", "manufacturer"],
    "parallel":     ["c:parallel/variety", "*c:parallel/variety", "parallel"],
    "set_name":     ["c:set", "*c:set", "set"],
    "team":         ["c:team", "*c:team", "team"],
    "card_number":  ["c:card number", "*c:card number", "card number"],
    "league":       ["c:league", "*c:league", "league"],
    "autographed":  ["c:autographed", "*c:autographed"],
    "category":     ["category id", "*category"],
}

# Specifics worth keeping verbatim for other channels, beyond the named columns.
SPECIFIC_PREFIXES = ("c:", "*c:", "cd:", "cda:")


def _money(v) -> float | None:
    s = re.sub(r"[^0-9.\-]", "", str(v or ""))
    try:
        return round(float(s), 2) if s else None
    except ValueError:
        return None


def _header_map(fieldnames) -> dict:
    """Map our field names onto whatever this file actually calls them."""
    lower = {(c or "").strip().lower(): c for c in fieldnames or []}
    out = {}
    for field, aliases in FIELDS.items():
        for a in aliases:
            if a in lower:
                out[field] = lower[a]
                break
    return out


def read_export(text: str) -> dict:
    """Parse a Card Dealer Pro / Haystack One eBay export into card rows.

    Returns {"cards": [...], "skipped": [...], "columns": n, "tool": str}.
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {"cards": [], "skipped": [], "columns": 0, "tool": "unknown"}

    # eBay templates may carry Info/#INFO preamble rows before the header.
    hdr_i = next((i for i, r in enumerate(rows)
                  if any("title" == (c or "").strip().lower().lstrip("*") for c in r)), 0)
    hdr = [(c or "").strip() for c in rows[hdr_i]]
    m = _header_map(hdr)
    body = [dict(zip(hdr, r)) for r in rows[hdr_i + 1:] if any((c or "").strip() for c in r)]

    # Which tool made this file cannot be read from the file.
    #
    # Checked 3 Oct 2026 across three real exports (CHATTWHAT, GIRKSWHATNOT,
    # CANCWHT): the headers are byte-identical, 39 columns, same names, same
    # order. Both products emit the same eBay File Exchange template.
    #
    # The old guess keyed on "CD:Card Condition" / "Custom label (SKU)", which
    # every one of them carries, so it answered "cdp" for every file including
    # Heystack's — stamping the wrong source_tool onto the cards. An honest
    # "unknown" lets the caller say, and the Intake screen asks.
    tool = "unknown"

    cards, skipped = [], []
    for d in body:
        def g(field):
            col = m.get(field)
            return (d.get(col) or "").strip() if col else ""

        sku = g("sku")
        title = g("title")
        if not sku:
            # No identity, no card. Inventing one makes it unmatchable later.
            skipped.append({"why": "no SKU", "title": title[:70]})
            continue

        imgs = [u.strip() for u in g("images").split("|") if u.strip().startswith("http")]
        specifics = {k: (v or "").strip() for k, v in d.items()
                     if k and k.lower().startswith(SPECIFIC_PREFIXES) and (v or "").strip()}

        cards.append({
            "sku": sku,
            "title": title or None,
            "list_price": _money(g("price")),
            "images": imgs,
            "player": g("player") or None,
            "year": g("year") or None,
            "set_name": g("set_name") or None,
            "card_number": g("card_number") or None,
            "parallel": g("parallel") or None,
            "sport": g("sport") or None,
            "team": g("team") or None,
            "manufacturer": g("manufacturer") or None,
            "condition": g("condition") or None,
            "grader": g("grader") or None,
            "grade": g("grade") or None,
            "cert_number": g("cert_number") or None,
            "description": g("description") or None,
            "specifics": specifics,
        })

    return {"cards": cards, "skipped": skipped, "columns": len(hdr), "tool": tool}


def check_skus(cards) -> dict:
    """Is every card individually identifiable?

    Older scanner exports put the STACK name in the SKU column, so all 56
    cards in a batch carried "Baseball RB batch 2 04-11-26". That is a lot
    label, not a card identity: it cannot be located, sold, or pulled from one
    channel when it sells on another. Heystack's "Customize SKUs" setting is
    where this gets fixed at source — this reports it rather than papering
    over it, because a generated SKU will not match the listing eBay already
    holds.
    """
    seen, dupes = {}, {}
    for c in cards:
        seen[c["sku"]] = seen.get(c["sku"], 0) + 1
    for sku, n in seen.items():
        if n > 1:
            dupes[sku] = n
    batch_label = len(seen) == 1 and len(cards) > 1
    return {"unique": len(seen), "cards": len(cards), "duplicates": dupes,
            "batch_label": batch_label,
            "ok": not dupes,
            "why": ("every card shares one SKU — that is the stack name, not a card "
                    "identity. Turn on per-card SKUs in Heystack (Selling → Customize "
                    "SKUs) and re-export." if batch_label else
                    f"{len(dupes)} SKU(s) used more than once" if dupes else "")}


def suffix_skus(cards, start: int = 1) -> list:
    """Make shared SKUs unique: BASE-0001, BASE-0002...

    Only safe BEFORE the cards are listed. Once eBay holds a listing, its SKU
    is frozen on inventory-managed items (error 21920278), so renaming here
    would leave the app and eBay disagreeing about the same card.
    """
    out, n = [], start
    for c in cards:
        c = dict(c)
        c["sku"] = f"{c['sku']}-{n:04d}"
        n += 1
        out.append(c)
    return out


def batch_code(tool: str, when: dt.date | None = None, seq: int = 1) -> str:
    when = when or dt.date.today()
    return f"{(tool or 'SCAN').upper()[:8]}-{when:%Y-%m-%d}-{seq:02d}"


def to_rows(cards, *, batch: str, tool: str, lot_prefix: str = "",
            status: str = "intake", cost_each: float | None = None) -> list:
    """Cards as inventory_cards rows, ready to upsert on sku.

    Every row carries the same keys — the Worker builds one column list from
    the first row of a batch, so a ragged payload silently drops columns.
    """
    now = dt.datetime.utcnow().isoformat() + "Z"
    out = []
    for c in cards:
        out.append({
            "sku": c["sku"],
            "title": c.get("title"),
            "player": c.get("player"),
            "year": c.get("year"),
            "set_name": c.get("set_name"),
            "card_number": c.get("card_number"),
            "parallel": c.get("parallel"),
            "sport": c.get("sport"),
            "team": c.get("team"),
            "manufacturer": c.get("manufacturer"),
            "condition": c.get("condition"),
            "grader": c.get("grader"),
            "grade": c.get("grade"),
            "cert_number": c.get("cert_number"),
            "description": c.get("description"),
            "images": c.get("images") or [],
            "specifics": c.get("specifics") or {},
            "list_price": c.get("list_price"),
            "cost": cost_each,
            "lot_prefix": lot_prefix or None,
            "intake_batch": batch,
            "source_tool": tool,
            "status": status,
            "status_updated_at": now,
            "updated_at": now,
        })
    return out


def summarize(cards) -> dict:
    """What came in — the numbers worth seeing before committing an import."""
    vals = [c.get("list_price") or 0 for c in cards]
    with_img = sum(1 for c in cards if c.get("images"))
    return {
        "cards": len(cards),
        "value": round(sum(vals), 2),
        "with_images": with_img,
        "without_images": len(cards) - with_img,
        "images_total": sum(len(c.get("images") or []) for c in cards),
        "graded": sum(1 for c in cards if c.get("grade")),
        "no_player": sum(1 for c in cards if not c.get("player")),
        "over_20": sum(1 for c in cards if (c.get("list_price") or 0) >= 20),
    }
