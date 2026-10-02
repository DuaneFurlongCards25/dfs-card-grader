"""Selling the same card in more than one place without selling it twice.

## Who owns what

Card Dealer Pro is the cheap scanner for sub-$20 bulk, and it manages its own
channels — it lists to eBay/CollX/Whatnot/Shopify itself and auto-delists when
one of them sells. Those cards are imported here for cost and P&L only; this
module does not touch them.

Heystack handles the $20+ cards, where recognition is worth paying for. But
Heystack lists to eBay and nothing else, and CDP will not take those cards in
(its marketplace import is one-time, and inventory sync only covers listings
CDP itself created). So for Heystack cards CardPulse is the system of record,
and this module is what gets them onto other channels and off again.

## The rule that matters

A physical card is one card. If it is live on eBay and the website at once and
sells on either, the other listing has to come down — fast, by hand or by
file. `delist_plan` is that: it reads what sold, finds every other live
listing for the same SKU, and produces the file or list each channel needs.

Nothing here guesses. A sale with no matching inventory card is reported, not
quietly skipped, because an untracked sale is exactly the one that leaves a
dead listing up.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re

CHANNELS = ["ebay", "shopify", "instagram", "collx", "whatnot",
            "dc_sports", "quickconsign"]

CHANNEL_LABEL = {
    "ebay": "eBay", "shopify": "Website (Shopify)", "instagram": "Instagram",
    "collx": "CollX", "whatnot": "Whatnot", "dc_sports": "DC Sports87",
    "quickconsign": "QuickConsign",
}

# How a listing gets ended on each channel. Only eBay has a file format; the
# rest are a person doing something, so the plan says plainly which.
DELIST_METHOD = {
    "ebay": "File Exchange End file",
    "shopify": "set quantity 0 / archive",
    "instagram": "delete or mark SOLD on the post",
    "collx": "end in CollX",
    "whatnot": "end in Whatnot",
    "dc_sports": "tell the consignor",
    "quickconsign": "tell the consignor",
}

INFO_ROW = ["Info", "Version=1.0.0", "Template=fx_category_template_EBAY_US", "", ""]
END_HEADER = ["*Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)",
              "ItemID", "EndCode"]


def _money(v):
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v or "")) or 0)
    except ValueError:
        return 0.0


# ─── Shopify ─────────────────────────────────────────────────────────────────

SHOPIFY_COLS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags", "Published",
    "Option1 Name", "Option1 Value", "Variant SKU", "Variant Grams",
    "Variant Inventory Tracker", "Variant Inventory Qty",
    "Variant Inventory Policy", "Variant Fulfillment Service", "Variant Price",
    "Variant Requires Shipping", "Variant Taxable", "Image Src",
    "Image Position", "Image Alt Text", "Status", "Cost per item",
]


def _handle(sku: str) -> str:
    """Shopify handle: lowercase, url-safe, stable per card."""
    h = re.sub(r"[^a-z0-9]+", "-", str(sku or "").lower()).strip("-")
    return h or "card"


def shopify_csv(cards, *, published: bool = True, grams: int = 28) -> str:
    """Shopify product import, one product per card.

    Shopify takes extra images as extra rows carrying only the Handle and the
    image columns — which is how all ten scanner photos get in without
    repeating the product on the storefront. 28g is a card in a top loader and
    envelope; it only matters if shipping is weight-based.
    """
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=SHOPIFY_COLS, extrasaction="ignore",
                       lineterminator="\n")
    w.writeheader()
    for c in cards or []:
        sku = str(c.get("sku") or "").strip()
        if not sku:
            continue
        imgs = c.get("images") or []
        tags = [t for t in [c.get("sport"), c.get("year"), c.get("set_name"),
                            c.get("player"), c.get("parallel"), c.get("team"),
                            "Graded" if c.get("grade") else "Raw"] if t]
        w.writerow({
            "Handle": _handle(sku),
            "Title": c.get("title") or sku,
            "Body (HTML)": c.get("description") or _describe(c),
            "Vendor": c.get("manufacturer") or "DFS Cards",
            "Type": "Trading Card",
            "Tags": ", ".join(str(t) for t in tags),
            "Published": "TRUE" if published else "FALSE",
            "Option1 Name": "Title",
            "Option1 Value": "Default Title",
            "Variant SKU": sku,
            "Variant Grams": grams,
            "Variant Inventory Tracker": "shopify",
            # One physical card. Shopify must refuse a second order rather than
            # let the site sell what is already gone.
            "Variant Inventory Qty": 1,
            "Variant Inventory Policy": "deny",
            "Variant Fulfillment Service": "manual",
            "Variant Price": f"{_money(c.get('list_price') or c.get('est_value')):.2f}",
            "Variant Requires Shipping": "TRUE",
            "Variant Taxable": "TRUE",
            "Image Src": imgs[0] if imgs else "",
            "Image Position": 1 if imgs else "",
            "Image Alt Text": c.get("title") or "",
            "Status": "active" if published else "draft",
            "Cost per item": f"{_money(c.get('cost')):.2f}" if c.get("cost") else "",
        })
        for i, src in enumerate(imgs[1:], start=2):
            w.writerow({"Handle": _handle(sku), "Image Src": src,
                        "Image Position": i, "Image Alt Text": c.get("title") or ""})
    return buf.getvalue()


def _describe(c) -> str:
    bits = []
    for label, key in (("Player", "player"), ("Year", "year"), ("Set", "set_name"),
                       ("Card #", "card_number"), ("Parallel", "parallel"),
                       ("Team", "team"), ("Condition", "condition")):
        if c.get(key):
            bits.append(f"<li><b>{label}:</b> {c[key]}</li>")
    if c.get("grade"):
        bits.append(f"<li><b>Graded:</b> {c.get('grader') or ''} {c['grade']}</li>")
    return ("<p>" + (c.get("title") or "") + "</p><ul>" + "".join(bits) + "</ul>"
            "<p>Shipped in a top loader inside a rigid mailer. "
            "Questions welcome before you buy.</p>")


# ─── Instagram ───────────────────────────────────────────────────────────────

def ig_caption(card, *, price: float | None = None, handle: str = "@dfscards") -> str:
    """A caption a person can post without editing it first."""
    p = _money(price if price is not None else card.get("list_price"))
    head = card.get("title") or card.get("sku")
    tags = {"#sportscards", "#thehobby", "#cardcollector"}
    for k in ("sport", "player", "team", "manufacturer"):
        if card.get(k):
            tags.add("#" + re.sub(r"[^a-z0-9]", "", str(card[k]).lower()))
    if card.get("grade"):
        tags.add("#graded")
    if card.get("parallel"):
        tags.add("#" + re.sub(r"[^a-z0-9]", "", str(card["parallel"]).lower()))
    lines = [head]
    if p:
        lines.append(f"${p:,.2f} shipped")
    lines.append("")
    lines.append(f"DM to claim · {handle}")
    lines.append("")
    lines.append(" ".join(sorted(tags)[:12]))
    return "\n".join(lines)


def ig_pack(cards) -> list:
    """What to post, per card: the images to download and the caption."""
    return [{"sku": c.get("sku"), "caption": ig_caption(c),
             "images": (c.get("images") or [])[:10]} for c in cards or []]


# ─── Sold somewhere, still listed elsewhere ─────────────────────────────────

def delist_plan(sold, listings, *, exclude_channel_of_sale: bool = True) -> dict:
    """What has to come down, and from where.

    `sold`    — [{sku, channel, price, date}] from whichever channel reported it
    `listings`— card_listings rows [{sku, channel, external_id, status}]

    Returns the work split by channel, plus sales whose SKU matches no listing
    at all (reported, never silently dropped — that is the sale that leaves a
    dead listing up).
    """
    live = {}
    for l in listings or []:
        if (l.get("status") or "live") == "live":
            live.setdefault(str(l.get("sku") or "").strip().upper(), []).append(l)

    by_channel, unknown, already = {}, [], []
    for s in sold or []:
        sku = str(s.get("sku") or "").strip().upper()
        if not sku:
            continue
        rows = live.get(sku)
        if not rows:
            unknown.append(s)
            continue
        others = [r for r in rows
                  if not (exclude_channel_of_sale and r.get("channel") == s.get("channel"))]
        if not others:
            already.append(s)
        for r in others:
            by_channel.setdefault(r.get("channel") or "unknown", []).append({
                "sku": s.get("sku"), "external_id": r.get("external_id"),
                "sold_on": s.get("channel"), "price": s.get("price"),
                "how": DELIST_METHOD.get(r.get("channel"), "end it"),
            })
    return {"by_channel": by_channel, "unknown_sku": unknown,
            "nothing_to_do": already,
            "total": sum(len(v) for v in by_channel.values())}


def ebay_end_csv(rows) -> str:
    """File Exchange End file for the eBay side of a delist plan."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(INFO_ROW)
    w.writerow(END_HEADER)
    for r in rows or []:
        if r.get("external_id"):
            w.writerow(["End", r["external_id"], "NotAvailable"])
    return buf.getvalue()


def manual_delist_csv(by_channel) -> str:
    """Everything that cannot be ended by a file — a worklist, not a dead end."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Channel", "What to do", "SKU", "Listing ID", "Sold on", "Price"])
    for ch, rows in (by_channel or {}).items():
        if ch == "ebay":
            continue
        for r in rows:
            w.writerow([CHANNEL_LABEL.get(ch, ch), r["how"], r["sku"],
                        r.get("external_id") or "", CHANNEL_LABEL.get(r["sold_on"], r["sold_on"]),
                        f"{_money(r.get('price')):.2f}"])
    return buf.getvalue()


def listing_rows(cards, channel: str, *, price_field: str = "list_price") -> list:
    """card_listings rows for a batch just sent to a channel."""
    now = dt.datetime.utcnow().isoformat() + "Z"
    return [{
        "sku": c.get("sku"), "channel": channel, "external_id": None,
        "price": _money(c.get(price_field)), "status": "live",
        "listed_at": now, "updated_at": now,
    } for c in cards or [] if c.get("sku")]
