"""Import the spreadsheet someone already keeps.

## The problem this solves

A dealer taking in 100+ cards a weekend and tracking them by hand in Excel
does not have a scanner export, a SKU column, or eBay's File Exchange layout.
`dfs_intake` reads those exports and is right to refuse anything else — a
made-up SKU on a card that eBay already holds can never be matched back.

A personal spreadsheet is the opposite case. There is no listing to match, so
an identity has to be *created*, and the columns are whatever that person
happened to name them: "Player" or "Name" or "Card", "Cost" or "Paid" or "$".

So this module maps rather than assumes. Headers are guessed, the guess is
shown, and the person corrects it before anything is written. A column that
is guessed wrong and silently imported puts the purchase price in the asking
price, which is worse than not importing at all.

## What it will not do

It will not import a row with nothing to identify the card — no player and no
title. A row of blank cells with a price attached is not a card, and once
imported it is a permanent piece of litter in an inventory of thousands.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re

# Our field → header names seen in the wild. Matched case-insensitively and
# punctuation-blind, longest first so "card number" beats "card".
GUESSES: dict[str, list[str]] = {
    "player":      ["player", "playername", "name", "athlete", "card", "description",
                    "cardname", "item"],
    "year":        ["year", "season", "yr"],
    "set_name":    ["set", "setname", "product", "brand", "release"],
    "card_number": ["cardnumber", "cardno", "card#", "no", "number", "#"],
    "parallel":    ["parallel", "variation", "variant", "insert", "refractor",
                    "color", "colour"],
    "team":        ["team", "club"],
    "sport":       ["sport", "category", "league"],
    "manufacturer": ["manufacturer", "maker", "company"],
    "grade":       ["grade", "psa", "bgs", "sgc"],
    "grader":      ["grader", "gradingcompany", "gradedby"],
    "cert_number": ["cert", "certnumber", "certno", "serial", "slabnumber"],
    "condition":   ["condition", "cond"],
    "cost":        ["cost", "paid", "purchaseprice", "buyprice", "costbasis", "mycost",
                    "pricepaid", "buy"],
    "list_price":  ["listprice", "price", "askingprice", "asking", "sellprice",
                    "value", "estvalue", "marketvalue", "fmv", "comp"],
    "quantity":    ["qty", "quantity", "count", "copies"],
    "location":    ["location", "box", "where", "storage", "slot", "bin"],
    "notes":       ["notes", "note", "comment", "comments", "remarks"],
    "sku":         ["sku", "customlabel", "id", "cardid", "inventoryid"],
}

NUMERIC = {"cost", "list_price", "quantity"}
REQUIRED_ONE_OF = ("player", "title")


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9#]", "", str(s or "").strip().lower())


def _money(v):
    s = re.sub(r"[^0-9.\-]", "", str(v if v is not None else ""))
    if not s or s in {"-", "."}:
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def read_table(data: bytes, filename: str = "") -> dict:
    """Read a CSV or Excel file into headers + rows of strings.

    Everything is read as text. Pandas will happily turn a card number like
    "07" into the integer 7, and "1/1" into a date — both of which destroy the
    thing that identifies the card.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        try:
            import openpyxl
        except ImportError:
            return {"headers": [], "rows": [], "error": "openpyxl is needed for Excel files"}
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        grid = [["" if c is None else str(c) for c in row]
                for row in ws.iter_rows(values_only=True)]
    else:
        text = data.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        grid = [list(r) for r in csv.reader(io.StringIO(text), dialect)]

    # The header is the first row with at least two non-empty cells — people
    # put a title or a date above the table more often than not.
    head_i = next((i for i, r in enumerate(grid)
                   if sum(1 for c in r if str(c).strip()) >= 2), None)
    if head_i is None:
        return {"headers": [], "rows": [], "error": "no readable table in that file"}

    headers = [str(c).strip() for c in grid[head_i]]
    rows = []
    for r in grid[head_i + 1:]:
        if not any(str(c).strip() for c in r):
            continue
        rows.append({headers[i]: (str(r[i]).strip() if i < len(r) and r[i] is not None else "")
                     for i in range(len(headers))})
    return {"headers": [h for h in headers if h], "rows": rows, "error": "",
            # 1-based row of the first data line, so problems can name the row
            # the person actually sees in Excel rather than an internal index.
            "first_data_row": head_i + 2}


def guess_mapping(headers) -> dict:
    """Our field → their column, for the headers we recognise.

    Each column is claimed once. Without that, a sheet with both "Cost" and
    "Price" can map both onto the same field and one of the two numbers
    vanishes silently.
    """
    norm = {h: _norm(h) for h in headers}
    taken: set[str] = set()
    out: dict[str, str] = {}
    # Longest alias first: "cardnumber" must win over "card" for Card Number.
    for field, aliases in sorted(GUESSES.items(),
                                 key=lambda kv: -max(len(a) for a in kv[1])):
        for alias in sorted(aliases, key=len, reverse=True):
            hit = next((h for h in headers
                        if h not in taken and norm[h] == alias), None)
            if hit is None:
                hit = next((h for h in headers
                            if h not in taken and alias in norm[h]), None)
            if hit:
                out[field] = hit
                taken.add(hit)
                break
    return out


def make_sku(prefix: str, n: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "", (prefix or "CARD").upper())[:16] or "CARD"
    return f"{base}-{n:04d}"


def preview(rows, mapping, *, prefix: str, limit: int = 8,
            first_data_row: int = 2) -> dict:
    """What the import will produce, and what it will refuse — before writing."""
    built, problems = [], []
    seen_sku: set[str] = set()
    n = 0
    for i, r in enumerate(rows, start=first_data_row):
        def g(field):
            col = mapping.get(field)
            return (r.get(col) or "").strip() if col else ""

        player, title = g("player"), g("title")
        if not player and not title:
            problems.append({"row": i, "why": "nothing identifies this card "
                                              "(no player and no description)"})
            continue

        n += 1
        sku = g("sku") or make_sku(prefix, n)
        if sku in seen_sku:
            problems.append({"row": i, "why": f"duplicate SKU {sku}"})
            continue
        seen_sku.add(sku)

        for field in NUMERIC:
            raw = g(field)
            if raw and _money(raw) is None:
                problems.append({"row": i, "why": f"{field} is not a number: {raw!r}"})

        built.append(_row(r, mapping, sku, prefix))

    return {"cards": built, "problems": problems,
            "sample": built[:limit],
            "value": round(sum(c.get("list_price") or 0 for c in built), 2),
            "cost": round(sum(c.get("cost") or 0 for c in built), 2)}


def _hash(num: str) -> str:
    """"#12" and "12" both render as "#12" — people write it either way."""
    num = (num or "").strip()
    return f"#{num.lstrip('#')}" if num else ""


def _row(r, mapping, sku: str, prefix: str) -> dict:
    def g(field):
        col = mapping.get(field)
        return (r.get(col) or "").strip() if col else ""

    player = g("player")
    title = g("title") or " ".join(x for x in [g("year"), g("set_name"), player,
                                               _hash(g("card_number")),
                                               g("parallel")] if x).strip()
    return {
        "sku": sku,
        "title": title or player or None,
        "player": player or None,
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
        "description": g("notes") or None,
        "images": [],
        "specifics": {},
        "list_price": _money(g("list_price")),
        "cost": _money(g("cost")),
        "location": g("location") or None,
        "lot_prefix": prefix or None,
    }


def to_rows(cards, *, batch: str, status: str = "intake") -> list:
    """inventory_cards rows. Every row carries identical keys — the Worker
    builds its column list from the first row of a batch, so a ragged payload
    silently drops columns for everything after it."""
    now = dt.datetime.utcnow().isoformat() + "Z"
    out = []
    for c in cards:
        row = dict(c)
        row.update({"intake_batch": batch, "source_tool": "spreadsheet",
                    "status": status, "status_updated_at": now, "updated_at": now})
        out.append(row)
    return out
