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

def _tag(*parts) -> str:
    return "#" + re.sub(r"[^a-z0-9]", "", " ".join(str(p or "") for p in parts).lower())


def ig_hashtags(card, limit: int = 22) -> list:
    """Hashtags worth having, in the order Instagram rewards.

    Specific first, broad last. A post tagged only #sportscards competes with
    millions; #juniorcaminero competes with hundreds, and that is where a
    collector actually finds the card. Instagram allows 30 — past roughly 22
    the extra ones are noise that makes the caption look like spam.
    """
    tags: list[str] = []

    def add(t):
        if t and t != "#" and t not in tags:
            tags.append(t)

    player = str(card.get("player") or "").strip()
    add(_tag(player))                                   # #juniorcaminero
    if card.get("year") and player:
        add(_tag(player, "rookie") if _is_rookie(card) else _tag(card["year"], player))
    add(_tag(card.get("set_name")))                     # #bowmanchromemega
    add(_tag(card.get("manufacturer")))
    par = str(card.get("parallel") or "")
    if par and par.lower() not in {"base", "none"}:
        add(_tag(par))
    add(_tag(card.get("team")))
    if card.get("grade"):
        add(_tag(card.get("grader") or "psa", str(card["grade"]).replace("/", "")))
        add("#gradedcards")
        if str(card.get("grade")).startswith("10"):
            add("#gemmint")
    if _is_auto(card):
        add("#autograph")
        add("#oncard")
    if _is_rookie(card):
        add("#rookiecard")
        add("#rc")
    sport = str(card.get("sport") or "").lower()
    for s, extra in (("base", ["#baseballcards", "#mlb"]),
                     ("foot", ["#footballcards", "#nfl"]),
                     ("basket", ["#basketballcards", "#nba"]),
                     ("soccer", ["#soccercards", "#futbol"]),
                     ("hockey", ["#hockeycards", "#nhl"])):
        if s in sport:
            for e in extra:
                add(e)
    for broad in ("#thehobby", "#sportscards", "#cardcollector", "#whodoyoucollect",
                  "#cardsforsale", "#sportscardsforsale", "#hobbyfamily"):
        add(broad)
    return tags[:limit]


def _is_auto(card) -> bool:
    hay = " ".join(str(card.get(f) or "") for f in
                   ("parallel", "title", "set_name", "description")).lower()
    return (str(card.get("autographed") or "").lower() in {"yes", "true", "1"}
            or "auto" in hay or "signed" in hay)


def _is_rookie(card) -> bool:
    hay = " ".join(str(card.get(f) or "") for f in
                   ("parallel", "title", "set_name", "description")).lower()
    return bool(re.search(r"\b(rookie|rc|1st bowman|first bowman)\b", hay))


def market_line(market) -> str:
    """The part of "why this card matters" the app can actually prove.

    A caption sells on a reason to care, and the honest reasons available here
    are market facts: what the card has done lately and what copies really
    sold for. Awards, prospect rankings and "Cy Young favourite" are not in
    any data CardPulse holds — those come from the seller, who knows them, in
    the `why` line. Inventing one would put a false claim under a photo with
    the seller's name on it.
    """
    if not market:
        return ""
    bits = []
    pct = market.get("trend_pct")
    if pct not in (None, ""):
        try:
            pct = float(pct)
            if abs(pct) >= 3:
                bits.append(f"{'📈 Up' if pct > 0 else '📉 Down'} {abs(pct):.0f}% "
                            f"over {market.get('trend_days', 30)} days")
        except (TypeError, ValueError):
            pass
    sold = [s for s in (market.get("recent_sold") or []) if s]
    if sold:
        shown = ", ".join(f"${float(s):,.0f}" for s in sold[:3])
        bits.append(f"🧾 Recent sales: {shown}")
    if market.get("pop"):
        bits.append(f"🏆 POP {market['pop']}")
    return "\n".join(bits)


def ig_caption(card, *, price: float | None = None, handle: str = "@dfscards",
               hook: str = "", story: bool = False, tags: bool = True,
               why: str = "", market=None) -> str:
    """A caption that can be posted without editing it first.

    Instagram is not a claim sale. The first line is read in a scrolling feed
    before anyone sees the price, so it leads with what makes the card worth
    stopping for; the details follow; the ask is explicit, because "DM to
    claim" is what turns a like into a sale.

    `story` gives the short version — a Story has no room for hashtags and
    they do nothing there.
    """
    p = _money(price if price is not None else card.get("list_price"))
    player = str(card.get("player") or "").strip()
    head = " ".join(x for x in [str(card.get("year") or "").strip(),
                                str(card.get("set_name") or "").strip(),
                                player] if x) or card.get("title") or card.get("sku")

    marks = []
    if _is_rookie(card):
        marks.append("ROOKIE")
    if _is_auto(card):
        marks.append("AUTO ✍️")
    par = str(card.get("parallel") or "").strip()
    if par and par.lower() not in {"base", "none"}:
        said = {w for w in re.split(r"\W+", head.lower()) if w}
        kept = [w for w in par.split() if w.lower() not in said
                and w.lower() not in {"auto", "autograph", "autographed",
                                      "rookie", "rc", "prospect"}]
        if kept:
            marks.insert(0, " ".join(kept))

    if not hook:
        if card.get("grade") and str(card["grade"]).startswith("10"):
            hook = "💎 GEM MINT 💎"
        elif _is_rookie(card) and _is_auto(card):
            hook = "✍️ ROOKIE AUTO ✍️"
        elif _is_auto(card):
            hook = "✍️ ON-CARD AUTO ✍️"
        else:
            hook = "🔥 JUST IN 🔥"

    lines = [hook, "", head]
    if marks:
        lines.append(" · ".join(marks))
    if card.get("grade"):
        lines.append(_grade_line(card))
    # Why a collector should care, before the price. The seller's own line
    # first — they know the player news — then the market facts we can prove.
    if why.strip():
        lines += ["", why.strip()]
    _ml = market_line(market)
    if _ml:
        lines += ["", _ml]
    lines.append("")
    lines.append(f"💵 ${p:,.0f} shipped" if p and p == int(p)
                 else (f"💵 ${p:,.2f} shipped" if p else "💵 Make an offer"))
    lines.append(f"📩 DM to claim — {handle}")
    if story:
        return "\n".join(l for l in lines if l is not None)
    lines += ["", "Shipped same or next day, tracked and sleeved. 🙌", ""]
    if tags:
        lines.append(" ".join(ig_hashtags(card)))
    return "\n".join(lines)


# ─── Facebook claim sales ────────────────────────────────────────────────────
#
# A different animal from an eBay listing. In a buy/sell/trade group the
# seller posts one photo per card with a short caption and the first person
# to comment claims it. The caption is read on a phone, in a fast-scrolling
# feed, so it is four short lines and no hashtags — hashtags read as spam in
# these groups and get posts removed.
#
# Modelled on James Pjura's own posts (MLB Baseball Cards Buy/Sell/Trade,
# Oct 2026), which are the format his buyers already recognise:
#
#     Franklin Arias 2025 Bowman Chrome 1st ✍️ AUTOGRAPH
#     PSA 9 - Mint
#     Red Sox #1 Prospect ⬆️TOP
#     $275
#
# The handwritten name-and-date card in the photo is a group requirement for
# proof of ownership and cannot be automated. Nothing here tries to.

GRADE_WORD = {
    "10": "GEM MT", "9.5": "GEM MT", "9": "Mint", "8.5": "NM-MT+",
    "8": "NM-MT", "7.5": "NM+", "7": "NM", "6": "EX-MT", "5": "EX",
}


def _grade_line(card, tagline: str = "") -> str:
    """"PSA 9 - Mint", or "PSA 9 - The Best Ever 🐐".

    Sellers routinely swap the grade word for a line of hype, because the
    number already says the condition and the words are what sell it. Both of
    James Pjura's posts do one or the other, so this takes either.

    Raw cards say RAW rather than leaving a blank line — in a claim sale
    "is it graded?" is otherwise the first comment every time.
    """
    grade = str(card.get("grade") or "").strip()
    grader = str(card.get("grader") or "").strip().upper()
    if not grade:
        cond = tagline or str(card.get("condition") or "").strip()
        return f"RAW - {cond}" if cond else "RAW"
    # SGC and BGS write dual grades as "10/10" (card / autograph). The word
    # is looked up from the first number; the full "10/10" still prints,
    # because that second number is the thing buyers ask about.
    _lookup = grade.split("/")[0].strip()
    _lookup = _lookup.rstrip("0").rstrip(".") if "." in _lookup else _lookup
    word = tagline or GRADE_WORD.get(_lookup, "")
    return " ".join(x for x in [grader or "PSA", grade, f"- {word}" if word else ""] if x)


def fb_caption(card, *, price=None, note: str = "", tagline: str = "",
               show_number: bool = False) -> str:
    """One card, one post. Three or four short lines, no hashtags.

    `tagline` goes after the grade ("PSA 9 - The Best Ever 🐐"); `note` goes
    on its own line ("Red Sox #1 Prospect ⬆️TOP"). Sellers use both shapes.
    """
    bits = [str(card.get("player") or "").strip(),
            str(card.get("year") or "").strip(),
            str(card.get("set_name") or "").strip()]
    # A scanner writes the parallel as "Chrome Prospect Autograph" while the
    # set is already "Bowman Chrome 1st", so printing both gives "Bowman
    # Chrome 1st Chrome Prospect Autograph ✍️ AUTOGRAPH". Drop the words the
    # set line already said, and the auto wording the ✍️ tag covers.
    par = str(card.get("parallel") or "").strip()
    if par and par.lower() not in {"base", "none"}:
        said = {w for w in re.split(r"\W+", " ".join(bits).lower()) if w}
        kept = [w for w in par.split()
                if w.lower() not in said
                # The marker line already says these, so the parallel must not
                # repeat them: "Rookie Autograph" + the tag gave
                # "…Mega Rookie ROOKIE AUTOGRAPH ✍️".
                and w.lower() not in {"auto", "autograph", "autographed",
                                      "prospect", "rookie", "rc"}]
        if kept:
            bits.append(" ".join(kept))
    # Card number off by default: the buyer is looking at a photo, and
    # neither of the real posts this is modelled on carries one. On for
    # sets where the number is how the card is identified.
    num = str(card.get("card_number") or "").strip().lstrip("#")
    if num and show_number:
        bits.append(f"#{num}")
    head = " ".join(b for b in bits if b)
    # "ROOKIE AUTOGRAPH ✍️" — a rookie auto is the single most saleable thing
    # in a claim sale, and sellers put both words in the first line every time.
    _hay = " ".join(str(card.get(f) or "") for f in
                    ("parallel", "title", "set_name", "description")).lower()
    _rookie = bool(re.search(r"\b(rookie|rc|1st bowman|first bowman)\b", _hay))
    _auto = (str(card.get("autographed") or "").lower() in {"yes", "true", "1"}
             or "auto" in _hay or "signed" in _hay)
    if _auto:
        head += (" ROOKIE AUTOGRAPH ✍️" if _rookie else " ✍️ AUTOGRAPH")
    elif _rookie:
        head += " ROOKIE"

    p = _money(price if price is not None else card.get("list_price"))
    lines = [head, _grade_line(card, tagline)]
    if note.strip():
        lines.append(note.strip())
    lines.append(f"${p:,.0f}" if p and p == int(p) else (f"${p:,.2f}" if p else "Make offer"))
    return "\n".join(l for l in lines if l)


# How buyers actually pay in these groups, and what each costs the seller.
# Goods & Services is the one that carries seller protection; friends-and-
# family and Zelle do not, which is why the distinction is recorded rather
# than assumed — it decides both the fee and whether there is any recourse.
PAYMENT_METHODS = {
    "PayPal G&S":      {"pct": 0.0299, "fixed": 0.49, "gs": True,
                        "note": "2.99% + $0.49. Protected."},
    "PayPal F&F":      {"pct": 0.0,    "fixed": 0.0,  "gs": False,
                        "note": "Free, but no protection and against PayPal's terms "
                                "for goods."},
    "Venmo G&S":       {"pct": 0.019,  "fixed": 0.10, "gs": True,
                        "note": "1.9% + $0.10 on a business profile. Protected."},
    "Venmo F&F":       {"pct": 0.0,    "fixed": 0.0,  "gs": False,
                        "note": "Free, no protection."},
    "Zelle":           {"pct": 0.0,    "fixed": 0.0,  "gs": False,
                        "note": "Free and instant, but no protection and no reversals."},
    "Cash / in person":{"pct": 0.0,    "fixed": 0.0,  "gs": False, "note": "Free."},
    "Other":           {"pct": 0.0,    "fixed": 0.0,  "gs": False,
                        "note": "Enter the fee yourself."},
}


def payment_fee(method: str, order_total: float) -> float:
    """What the processor takes from one order.

    Charged on the whole order including shipping, which is how they bill it —
    worked out per order, never per card, or the fixed part is counted once
    for every card in a multi-card claim.
    """
    m = PAYMENT_METHODS.get(method) or PAYMENT_METHODS["Other"]
    if not m["pct"] and not m["fixed"]:
        return 0.0
    return round(_money(order_total) * m["pct"] + m["fixed"], 2)


DEFAULT_SHIP_NOTE = ("Shipping is $6 bubble mailer with tracking for as many cards "
                     "as you buy! $10 priority mail for orders over $350+")


def fb_header(*, title: str = "THE WEEK'S BEST CLAIM SALE", when: str = "",
              low=None, high=None, ship_note: str = DEFAULT_SHIP_NOTE) -> str:
    """The post that opens a claim sale, above the individual cards."""
    lines = [f"🔥{title}🔥", "", "💥" * 10]
    if when:
        lines.append(f"🔥🔥🔥 STARTS {when} 🔥🔥🔥")
    lines += ["🆕 NEW INVENTORY 👀", "", "GOATS 🐐", "HOF ✅", "ROOKIES 📈",
              "GEM MINT SLABS 💎", "AUTOGRAPHS ✍️", ""]
    if low is not None and high is not None:
        lines.append(f"~~~~Cards for ALL Collectors ${low:,.0f}-${high:,.0f}~~~~")
    lines += ["First to claim gets the card! ✅", "Offers welcome too 😎",
              '🔥🔥 TAG 🏷 AND DROP A "W" TO WATCH 🔥🔥', "", ship_note]
    return "\n".join(lines)


def claim_totals(claims, *, ship_small: float = 6.0, ship_large: float = 10.0,
                 large_over: float = 350.0) -> list:
    """Who owes what, once the comments stop.

    `claims` — [{buyer, sku, price}]. A buyer taking six cards pays one
    shipping charge, which is the whole appeal of a claim sale and also the
    arithmetic that goes wrong by hand at 11pm with forty comments to read.
    """
    by_buyer: dict[str, list] = {}
    for c in claims or []:
        buyer = str(c.get("buyer") or "").strip()
        if not buyer:
            continue
        by_buyer.setdefault(buyer, []).append(c)

    out = []
    for buyer, items in sorted(by_buyer.items(), key=lambda kv: kv[0].lower()):
        cards_total = round(sum(_money(i.get("price")) for i in items), 2)
        ship = ship_large if cards_total > large_over else ship_small
        out.append({
            "buyer": buyer, "cards": len(items), "cards_total": cards_total,
            "shipping": ship, "total": round(cards_total + ship, 2),
            "skus": [i.get("sku") for i in items],
            "items": items,
        })
    return out


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
