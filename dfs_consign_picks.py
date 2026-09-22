"""Build the consignment picks workbook from an eBay active-listings report.

Duane ticks a column per consignor, and `dfs_consign.build_all` turns the
marked file into PDF manifests and an eBay End file. This is the step before
that: choosing what is even eligible, and — the part that matters when the
file is rebuilt days later — carrying forward the ticks already made.

Rebuilt rather than edited in place on purpose. Between one report and the
next, cards sell, prices move and the dead-stock clearance rewrites whole
bands of the shelf; a sheet built from Thursday's prices would have someone
shipping against numbers that no longer exist.

A previously ticked card that has since sold or ended cannot be shipped, so it
is reported rather than silently dropped.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import dfs_buying as buying
from dfs_consign import CONSIGNORS, MIN_PRICE

# Below the cheaper house's floor there is nothing to decide.
ELIGIBLE_FROM = min(MIN_PRICE.values())

HEAD = ["DC Sports87", "QuickConsign", "eBay Price", "Days Listed",
        "Watchers", "Card", "eBay Item ID", "SKU"]


def read_marks(xlsx_path):
    """{item_id: [consignor, ...]} from an earlier picks workbook."""
    from openpyxl import load_workbook
    out = {}
    try:
        ws = load_workbook(xlsx_path, data_only=True)["Cards"]
    except Exception:
        return out
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not r[6]:
            continue
        who = [name for name, col in (("DC Sports87", 0), ("QuickConsign", 1))
               if str(r[col] or "").strip()]
        if who:
            out[str(r[6]).strip()] = who
    return out


def build(report_text, out_path, *, previous=None, today=None,
          eligible_from: float = ELIGIBLE_FROM):
    today = today or dt.date.today()
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    listings = buying.read_ebay_report(report_text, today=today)
    marks = read_marks(previous) if previous else {}
    live = {l.item_id for l in listings}
    lost = {i: w for i, w in marks.items() if i not in live}

    rows = sorted([l for l in listings if l.price >= eligible_from],
                  key=lambda l: -l.price)

    wb = Workbook()
    s = wb.active
    s.title = "Summary"
    kept = sum(1 for l in rows if l.item_id in marks)
    for line in [
        ("DFS Cards — Consignment picks", True),
        (f"Built from the active-listings report of {today:%B %d, %Y}", False),
        ("", False),
        ("HOW TO USE", True),
        ("On the 'Cards' tab, mark column A for DC Sports87 or column B for QuickConsign.", False),
        ("Pick ✓ from the dropdown or type any mark — an x or a 1 counts too.", False),
        ("Mark ONE house per card. A card marked for both is refused rather than guessed at.", False),
        ("", False),
        ("FLOORS", True),
        (f"DC Sports87 takes cards at ${MIN_PRICE['DC Sports87']:.2f}+.", False),
        (f"QuickConsign is strict at ${MIN_PRICE['QuickConsign']:.2f}+ — under that, column B is greyed out.", False),
        ("", False),
        ("THIS FILE", True),
        (f"{len(rows):,} cards eligible (${eligible_from:.2f} and up, live on eBay today).", False),
        (f"{kept} tick(s) carried over from the previous file.", False),
        (f"{len(lost)} previously ticked card(s) are no longer listed — see below.", False),
    ]:
        c = s.cell(row=s.max_row + 1 if s.max_row > 1 or s["A1"].value else 1, column=1, value=line[0])
        if line[1]:
            c.font = Font(bold=True)
    if lost:
        s.cell(row=s.max_row + 2, column=1, value="TICKED BUT NO LONGER LISTED (sold or ended — do not ship)").font = Font(bold=True)
        for item, who in lost.items():
            s.cell(row=s.max_row + 1, column=1, value=f"    {item} — was marked {', '.join(who)}")
    s.column_dimensions["A"].width = 96

    ws = wb.create_sheet("Cards")
    ws.append(HEAD)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"

    grey = PatternFill("solid", fgColor="E8E8E8")
    for l in rows:
        who = marks.get(l.item_id, [])
        ws.append(["✓" if "DC Sports87" in who else "",
                   "✓" if "QuickConsign" in who else "",
                   round(l.price, 2), l.age_days, l.watchers,
                   l.title, l.item_id, l.sku])
        if l.price < MIN_PRICE["QuickConsign"]:
            ws.cell(row=ws.max_row, column=2).fill = grey

    dv = DataValidation(type="list", formula1='"✓"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"A2:B{ws.max_row}")

    for col, w in zip("ABCDEFGH", (13, 14, 11, 12, 10, 62, 16, 30)):
        ws.column_dimensions[col].width = w
    for col in "ABCDE":
        for c in ws[col][1:]:
            c.alignment = Alignment(horizontal="center")
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEAD))}{ws.max_row}"

    out_path = Path(out_path)
    wb.save(out_path)
    return {"file": out_path, "eligible": len(rows), "carried": kept,
            "lost": lost, "listings": len(listings)}
