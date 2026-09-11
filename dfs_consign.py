"""Turn a marked consignment workbook into manifests and an eBay End file.

Duane marks each card in the 'Cards' tab of the picks workbook: column A for
DC Sports87, column B for QuickConsign. This module reads that file back and
produces, per consignor:

  * a PDF manifest listing every card by name — the document both sides use
    to check what was actually received
  * an eBay File Exchange End file for everything marked, so the listings
    come down the moment the cards leave

The manifest deliberately carries no prices. It is a receipt, not an offer,
and a consignor does not need Duane's eBay asking price to check a box.

A card marked for BOTH consignors is refused rather than guessed at: it goes
in neither manifest and is reported back, because shipping one card to two
houses is not something a script should resolve on its own.

No Streamlit imports, same as dfs_labels and dfs_relist, so it can run from a
script or be wired into the Consignments tab later.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import io
import subprocess
from pathlib import Path

CONSIGNORS = {"A": "DC Sports87", "B": "QuickConsign"}

# Lowest eBay price each house will take. QuickConsign is strict on its floor;
# a card under it is refused at read time rather than shipped and bounced.
MIN_PRICE = {"DC Sports87": 3.00, "QuickConsign": 5.00}

INFO = ["Info", "Version=1.0.0", "Template=fx_category_template_EBAY_US"]
ACTION = "*Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def read_marks(xlsx_path) -> dict:
    """{'DC Sports87': [card, ...], 'QuickConsign': [...], 'conflicts': [...]}.

    Any non-blank cell counts as a mark — a ✓ from the dropdown, an x, a 1.
    Reading only the literal ✓ would silently drop a card someone marked
    with an x, which is the likeliest thing a person types.
    """
    from openpyxl import load_workbook

    ws = load_workbook(xlsx_path, data_only=True)["Cards"]
    hdr = [str(c.value or "").strip() for c in ws[1]]
    col = {h: i for i, h in enumerate(hdr)}
    out = {name: [] for name in CONSIGNORS.values()}
    out["conflicts"] = []      # marked for both houses
    out["below_floor"] = []    # marked for a house that will not take it
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[col["Card"]]:
            continue
        card = {
            "card": str(row[col["Card"]]).strip(),
            "item": str(row[col["eBay Item ID"]] or "").strip(),
            "sku": str(row[col["SKU"]] or "").strip(),
            "price": float(row[col["eBay Price"]] or 0),
        }
        marked = [CONSIGNORS[k] for k, idx in (("A", 0), ("B", 1))
                  if str(row[idx] or "").strip()]
        if len(marked) > 1:
            out["conflicts"].append(card)
        elif marked:
            house = marked[0]
            if card["price"] < MIN_PRICE.get(house, 0):
                # Held out of the manifest AND the End file — the listing stays
                # up until someone decides where this card actually goes.
                out["below_floor"].append(dict(card, house=house))
            else:
                out[house].append(card)
    return out


_CSS = """
@page { size: letter; margin: 0.6in 0.6in 0.7in; }
body { font-family: Arial, Helvetica, sans-serif; color: #141A26; font-size: 10.5pt; }
.head { display: flex; justify-content: space-between; align-items: flex-end;
        border-bottom: 2px solid #1F2A44; padding-bottom: 8px; margin-bottom: 14px; }
.head h1 { font-size: 17pt; margin: 0; }
.head .to { font-size: 11pt; color: #4E5768; margin-top: 3px; }
.meta { text-align: right; font-size: 9.5pt; color: #4E5768; line-height: 1.5; }
.meta b { color: #141A26; font-size: 13pt; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: 8.5pt; letter-spacing: .06em; text-transform: uppercase;
     color: #4E5768; border-bottom: 1px solid #1F2A44; padding: 5px 6px; }
td { padding: 6px; border-bottom: 1px solid #D8DCE3; vertical-align: top; }
tr { page-break-inside: avoid; }
td.n { width: 28px; color: #7B8290; font-variant-numeric: tabular-nums; }
td.sku { font-family: Menlo, Consolas, monospace; font-size: 8.5pt; color: #4E5768; width: 32%; }
td.box, th.box { width: 58px; text-align: center; }
.cb { display: inline-block; width: 13px; height: 13px; border: 1.3px solid #141A26; }
.sign { margin-top: 26px; display: grid; grid-template-columns: 1fr 1fr; gap: 26px;
        font-size: 9.5pt; color: #4E5768; page-break-inside: avoid; }
.sign div { border-top: 1px solid #141A26; padding-top: 5px; }
.foot { margin-top: 14px; font-size: 8.5pt; color: #7B8290; }
"""


def manifest_html(consignor: str, cards: list, *, sender: str = "DFS Cards",
                  when: dt.date | None = None, logo_uri: str = "") -> str:
    when = when or dt.date.today()
    rows = "".join(
        f'<tr><td class="n">{i}</td><td>{html.escape(c["card"])}</td>'
        f'<td class="sku">{html.escape(c["sku"])}</td>'
        f'<td class="box"><span class="cb"></span></td></tr>'
        for i, c in enumerate(cards, 1))
    logo = (f'<img src="{logo_uri}" style="width:46px;height:46px;border-radius:6px;'
            f'margin-right:12px;vertical-align:middle;">' if logo_uri else "")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(sender)} → {html.escape(consignor)} manifest</title>
<style>{_CSS}</style></head><body>
<div class="head">
  <div>{logo}<span style="display:inline-block;vertical-align:middle;">
    <h1>Consignment Manifest</h1>
    <div class="to">{html.escape(sender)} &rarr; {html.escape(consignor)}</div></span></div>
  <div class="meta"><b>{len(cards)} cards</b><br>Shipped {when:%B %d, %Y}</div>
</div>
<table><thead><tr><th></th><th>Card</th><th>SKU</th><th class="box">Received</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="sign">
  <div>Packed by ({html.escape(sender)}) &nbsp;/&nbsp; date</div>
  <div>Received &amp; counted by ({html.escape(consignor)}) &nbsp;/&nbsp; date</div>
</div>
<div class="foot">Count on receipt and tick each card. Report any card listed here that
was not in the package, or in the package but not listed, to {html.escape(sender)}.</div>
</body></html>"""


def write_pdf(html_text: str, pdf_path) -> Path:
    """Render with headless Chrome — WeasyPrint's native libs are not
    installed on this Mac and reportlab is absent, but Chrome always is."""
    pdf_path = Path(pdf_path)
    tmp = pdf_path.with_suffix(".html")
    tmp.write_text(html_text, encoding="utf-8")
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", tmp.as_uri()],
                   check=True, capture_output=True)
    tmp.unlink(missing_ok=True)
    return pdf_path


def end_csv(cards: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(INFO)
    w.writerow([ACTION, "ItemID", "EndCode"])
    for c in cards:
        if c["item"]:
            w.writerow(["End", c["item"], "NotAvailable"])
    return buf.getvalue()


def _logo_uri() -> str:
    import base64
    f = Path(__file__).parent / "assets" / "dfs-logo-seal.png"
    try:
        return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()
    except OSError:
        return ""


def build_all(xlsx_path, out_dir, *, when: dt.date | None = None) -> dict:
    """Marked workbook in, everything needed to ship out.

    Writes one PDF manifest per consignor that has cards, and ONE End file
    covering every card that is actually going somewhere. Conflicts and
    below-floor marks are excluded from both and returned for review, so a
    listing is never ended for a card that is not leaving the building.
    """
    when = when or dt.date.today()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    marks = read_marks(xlsx_path)
    logo = _logo_uri()
    stamp = when.strftime("%Y-%m-%d")
    written, shipping = {}, []
    for house in CONSIGNORS.values():
        cards = marks[house]
        if not cards:
            continue
        slug = house.replace(" ", "")
        written[house] = write_pdf(
            manifest_html(house, cards, when=when, logo_uri=logo),
            out_dir / f"Manifest-{slug}-{stamp}.pdf")
        shipping += cards
    if shipping:
        end = out_dir / f"ebay-END-consignment-{stamp}.csv"
        end.write_text(end_csv(shipping), encoding="utf-8")
        written["end_file"] = end
    return {"files": written, "counts": {h: len(marks[h]) for h in CONSIGNORS.values()},
            "conflicts": marks["conflicts"], "below_floor": marks["below_floor"]}
