"""2x1 thermal labels for the SKUs in a batch.

One label per card: the SKU in large type, the card name under it as a spot
check. The name is what makes the label useful — a SKU alone tells you nothing
when you're holding a card and trying to find its sleeve.

Output is a print-ready HTML page. Open it, Cmd-P, print to the thermal
printer with margins off and scaling at 100%. Page size is declared as 2x1in
so the printer feeds one label per card with no gap.
"""

from __future__ import annotations

import html
import io
import re

LABEL_W = "2in"
LABEL_H = "1in"

_CSS = """
@page { margin: 0; size: 2in 1in; }
body { margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif;
       background: #fff; color: #000; }
.label {
  width: 2in; height: 1in; box-sizing: border-box; padding: 0.07in 0.09in;
  display: flex; flex-direction: column; justify-content: center;
  page-break-after: always; break-after: page;
  border: 1px dashed #ccc; overflow: hidden;
}
.label:last-child { page-break-after: avoid; break-after: auto; }
.sku { font-size: 13px; font-weight: bold; line-height: 1.15;
       word-break: break-all; }
.name { font-size: 9px; line-height: 1.15; margin-top: 3px;
        overflow: hidden; }
.price { font-size: 9px; font-weight: bold; margin-top: 2px; }
.hint { font-family: Arial, sans-serif; font-size: 13px; color: #333;
        padding: 16px 20px; border-bottom: 1px solid #ddd; margin-bottom: 14px; }
.hint b { color: #000; }
@media print { .hint { display: none; } .label { border: none; } }
"""

_HINT = """<div class="hint">
<b>%(n)d labels · 2&quot; &times; 1&quot; thermal</b><br>
Print with <b>margins off</b> and <b>scaling 100%%</b> (not &quot;fit to page&quot;) —
scaling is what makes labels creep off the stock. In Chrome:
More settings &rarr; Paper size <b>2 x 1</b>, Margins <b>None</b>,
uncheck <b>Headers and footers</b>.<br>
The dashed edges are screen-only; they don't print.
</div>"""


def _shorten(text: str, limit: int) -> str:
    """Trim to a word boundary so a name never ends mid-word."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).rstrip(" ,-") + "…"


def label_name(ident, fallback: str = "") -> str:
    """The spot-check line: who and what, short enough to read at a glance.

    Deliberately not the eBay title — that leads with the year and brand,
    which is the least useful part when you're matching a card in hand.
    """
    if ident is None:
        return _shorten(fallback, 46)
    bits = [p for p in [
        (ident.player or "").strip(),
        f"#{ident.number}" if getattr(ident, "number", "") else "",
        (getattr(ident, "parallel", "") or "").strip(),
    ] if p]
    return _shorten(" ".join(bits) or fallback, 46)


def labels_html(items: list[dict], show_price: bool = True) -> str:
    """Print-ready page. Each item: {sku, name, price(optional)}."""
    blocks = []
    for it in items:
        sku = html.escape(str(it.get("sku") or "").strip())
        name = html.escape(_shorten(str(it.get("name") or ""), 46))
        price = it.get("price")
        line = ""
        if show_price and price not in (None, "", 0):
            try:
                line = f'<div class="price">${float(price):,.2f}</div>'
            except (TypeError, ValueError):
                line = ""
        blocks.append(
            f'<div class="label"><div class="sku">{sku}</div>'
            f'<div class="name">{name}</div>{line}</div>')

    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>SKU labels</title><style>" + _CSS + "</style></head><body>"
            + (_HINT % {"n": len(items)})
            + "".join(blocks) + "</body></html>")


def batch_of(sku: str) -> str:
    """The lot a SKU belongs to — the prefix with its sequence number cut off.

    `whatnot 08-28-26-00002` -> `whatnot 08-28-26`
    `POOKIEWHT-08-15-26-00013-4f2a` -> `POOKIEWHT-08-15-26`
    """
    s = (sku or "").strip()
    if not s:
        return "(no SKU)"
    # The separator is REQUIRED. With it optional, `\d{4,5}` could start part
    # way through a longer number: CHATTWHT-083026-00001 matched "83026-00001"
    # and yielded "CHATTWHT-0". The trailing group is the optional random
    # suffix some lots carry.
    return re.sub(r"[-_]\d{4,5}(?:-[A-Za-z0-9]+)?$", "", s) or s


# Column names differ between eBay's active-listings report, a PriceDesk upload
# file and a CDP export. Read whichever is present.
_SKU_COLS = ["Custom label (SKU)", "CustomLabel", "Custom Label", "SKU"]
_TITLE_COLS = ["Title", "*Title"]
_PRICE_COLS = ["Current price", "Start price", "*StartPrice", "StartPrice"]
_ITEM_COLS = ["Item number", "ItemID", "Item ID"]


def _pick(row: dict, names: list[str]) -> str:
    for n in names:
        if row.get(n) not in (None, ""):
            return str(row[n]).strip()
    return ""


def read_listings(text: str) -> list[dict]:
    """Parse any of the listing files into {sku, title, price, item, batch}.

    Handles the File Exchange `Info` preamble row, which sits above the real
    header and would otherwise be read as the header itself.
    """
    import csv

    lines = text.splitlines()
    if lines and lines[0].split(",")[0].strip().strip('"') == "Info":
        lines = lines[1:]

    out = []
    for row in csv.DictReader(io.StringIO("\n".join(lines))):
        sku = _pick(row, _SKU_COLS)
        title = _pick(row, _TITLE_COLS)
        if not sku and not title:
            continue
        price = _pick(row, _PRICE_COLS)
        out.append({
            "sku": sku,
            "title": title,
            "price": price,
            "item": _pick(row, _ITEM_COLS),
            "batch": batch_of(sku),
        })
    return out


_NOT_NAMES = {"RC", "AUTO", "WNBA", "MLB", "NBA", "NFL", "NHL", "UEFA", "PSA"}


# Two-letter words that are ordinary name parts, not initials — these get
# title-cased like everything else ("DE LA CRUZ" -> "De La Cruz").
_NAME_PARTICLES = {"DE", "LA", "LE", "DA", "DI", "DU", "VAN", "VON",
                   "JR", "SR", "II", "III", "MC", "ST"}


def _titlecase(name: str) -> str:
    """Title-case a name without flattening initials — JJ stays JJ, not Jj."""
    out = []
    for word in name.split():
        core = word.rstrip(".")
        keep = (len(core) <= 2 and core.isupper()
                and core not in _NAME_PARTICLES)
        out.append(word if keep else word.title())
    return " ".join(out)


def name_from_title(title: str) -> str:
    """Spot-check line from an eBay title alone, for listings already live.

    The player's name is in caps in our titles, so it can be lifted out and put
    first — the same shape the batch labels use, without needing the scan.
    """
    t = re.sub(r"\s+", " ", (title or "").strip())
    # Trailing "." is part of the name ("JR."), not a sentence end — capture it
    # or it gets orphaned into the parallel.
    # Runs of ALL-CAPS words. The trailing \b matters: without it "Topps"
    # matches as the single letter "T" and the real name is never reached.
    word = r"[A-Z][A-Z0-9'’\-]+\.?"
    m = re.search(rf"\b({word}(?:\s+{word})*)\b", t)
    player = (m.group(1).strip() if m else "")
    # A lone all-caps word like "RC" or a league tag isn't a name.
    if len(player) < 4 or player in _NOT_NAMES:
        return _shorten(t, 46)

    num = re.search(r"#\S+", t)
    rest = t[m.end():]
    if num:
        rest = rest.replace(num.group(0), "", 1)
    # Sport and league words earn their place in an eBay title (buyers search
    # them) but not on a label — you already know what you're holding.
    rest = re.sub(r"\b(Baseball|Basketball|Football|Soccer|Hockey|NBA|MLB|"
                  r"NFL|NHL|WNBA|Card)\b", " ", rest, flags=re.I)
    rest = re.sub(r"\s+", " ", rest).strip(" .,-–—")
    bits = [_titlecase(player), num.group(0) if num else "", rest]
    return _shorten(" ".join(b for b in bits if b), 46)


def labels_from_listings(items: list[dict], show_price: bool = True) -> str:
    """Labels for listings that are already live — no scan data needed."""
    return labels_html([{
        "sku": it["sku"],
        "name": name_from_title(it["title"]),
        "price": it.get("price"),
    } for it in items], show_price=show_price)


def labels_from_rows(rows: list[dict], scans: list[dict] | None = None,
                     show_price: bool = True) -> str:
    """Build labels straight off the eBay rows a batch just produced.

    `scans` is optional and only supplies a nicer name line; without it the
    eBay title is used, trimmed.
    """
    by_sku = {}
    for s in (scans or []):
        sku = (s.get("sku") or "").strip()
        if sku:
            by_sku[sku] = s.get("ident")

    items = []
    for r in rows:
        sku = r.get("CustomLabel", "")
        items.append({
            "sku": sku,
            "name": label_name(by_sku.get(sku), r.get("*Title", "")),
            "price": r.get("*StartPrice"),
        })
    return labels_html(items, show_price=show_price)
