"""Master inventory — every card you own, where it sits, and what state it is in.

The listings table only knows about cards that are live on eBay, which is
roughly 4,000 of an estimated 40-50,000. This module is the record for all of
them. Free-standing arithmetic like dfs_buying / dfs_breaks / dfs_health: no
Streamlit, so it can be tested against real files and driven from a script.

## Two levels, because 45,000 cards cannot each be scanned

  inventory_cards   one row per SKU — anything worth tracking on its own.
  inventory_boxes   one row per physical box — counted and located bulk.

A card moves from a box to its own row when it is pulled to be listed. Bulk
never has to be itemized to be counted and found.

## Identity is the SKU

Not SPORT-YEAR-CARDNUMBER, which gives every 2024 basketball #75 in every set,
player and parallel the same id. SKUs are already unique per card and already
printed on the labels and the eBay listings.

## What sync is allowed to change

Sync writes only what eBay and the sales records actually know: title, price,
item number, and status. It never touches location, cost, box or notes — those
are typed by a person and a report has no opinion about them. The Worker's
upsert only updates the columns it is sent, so leaving them out of the payload
is what protects them.
"""

from __future__ import annotations

import csv
import datetime as dt
import re

import dfs_buying as buying

# ─── Statuses ────────────────────────────────────────────────────────────────

STATUSES = ["intake", "priced", "listed", "ended", "sold",
            "bulk", "consigned", "grading", "missing"]

STATUS_LABEL = {
    "intake":    "📥 Intake",
    "priced":    "🏷️ Priced",
    "listed":    "🟢 Listed",
    "ended":     "⏸️ Ended — back on shelf",
    "sold":      "💵 Sold",
    "bulk":      "📦 Bulk",
    "consigned": "🚚 Consigned",
    "grading":   "🔬 At grading",
    "missing":   "❓ Missing",
}

# States a person set on purpose. A sync only overrides them with hard facts:
# the card is live on eBay, or it sold.
MANUAL_STATES = {"bulk", "consigned", "grading", "missing"}

# eBay's thresholds as used on the pull ticket. Verify against eBay's current
# policy — they are shown as reminders, not enforced.
AUTHENTICITY_GUARANTEE_FROM = 250.00
SIGNATURE_FROM = 750.00

PAGE = 10_000            # the Worker's per-request cap


# ─── Location ────────────────────────────────────────────────────────────────

_LOC = re.compile(r"^\s*B\s*(\d+)\s*(?:-?\s*R\s*(\d+)\s*(?:-?\s*P\s*(\d+))?)?\s*$", re.I)


def parse_location(v):
    """'b14-r2-p7' -> ('B14', 2, 7). 'B14' or 'B14-R2' are accepted too, so a
    box can be located before its rows are. Anything else -> None."""
    m = _LOC.match(str(v or ""))
    if not m:
        return None
    return (f"B{int(m.group(1))}",
            int(m.group(2)) if m.group(2) else None,
            int(m.group(3)) if m.group(3) else None)


def format_location(box, row=None, pos=None) -> str:
    if not box:
        return ""
    s = str(box).upper()
    if row:
        s += f"-R{int(row)}"
        if pos:
            s += f"-P{int(pos)}"
    return s


def location_sort_key(card):
    """Box, row, position — numerically, so B2 comes before B10."""
    p = parse_location(card.get("location"))
    if not p:
        return (1, 10**9, 10**9, 10**9, str(card.get("sku") or ""))
    return (0, int(p[0][1:]), p[1] or 0, p[2] or 0, str(card.get("sku") or ""))


# ─── Paging ──────────────────────────────────────────────────────────────────

def fetch_all(get, table, params: str = "", page: int = PAGE, max_pages: int = 20):
    """Read a whole table through a Worker that caps each request.

    The Worker has no offset, so this pages on id: id > last seen, ordered by
    id. `get(table, params)` is the app's _neon_get. A short page means done.
    """
    out, last = [], 0
    sep = "&" if params else "?"
    for _ in range(max_pages):
        q = f"{params}{sep}id=gt.{last}&order=id.asc&limit={page}"
        rows = get(table, q) or []
        out.extend(rows)
        if len(rows) < page:
            break
        last = rows[-1]["id"]
    return out


# ─── Sync from what eBay and sales already know ─────────────────────────────

def sync_rows(report_listings, sales, lot_cards, existing, today=None) -> dict:
    """Build the upsert payload that brings inventory in line with reality.

    Status precedence: sold > listed > everything else. A card that WAS listed
    and is no longer in the current report, and has not sold, is 'ended' — it
    should be back on a shelf, which is exactly the card that goes missing.

    Every returned row has the same keys, because the Worker builds one column
    list from the first row of a batch.
    """
    today = today or dt.date.today()
    now = dt.datetime.utcnow().isoformat() + "Z"
    exist = {str(e.get("sku") or "").strip().upper(): e for e in existing or []}
    live = {}
    for l in report_listings or []:
        k = (l.sku or "").strip()
        if k:
            live[k.upper()] = l
    sold = {}
    for s in sales or []:
        k = str(s.get("sku") or "").strip()
        if k:
            sold.setdefault(k.upper(), s)

    rows, counts = {}, {"new": 0, "changed": 0, "same": 0}

    def put(sku, title, price, item, status, lot):
        key = sku.upper()
        cur = exist.get(key)
        old = (cur or {}).get("status")
        row = {
            "sku": sku,
            "title": title or (cur or {}).get("title"),
            "list_price": price if price is not None else (cur or {}).get("list_price"),
            "item_number": item or (cur or {}).get("item_number"),
            "lot_prefix": lot or (cur or {}).get("lot_prefix"),
            "status": status,
            "status_updated_at": now if status != old else (cur or {}).get("status_updated_at") or now,
            "updated_at": now,
        }
        if cur is None:
            counts["new"] += 1
        elif status != old or row["list_price"] != cur.get("list_price") or row["title"] != cur.get("title"):
            counts["changed"] += 1
        else:
            counts["same"] += 1
            return
        rows[key] = row

    lot_of = {str(c.get("sku") or "").strip().upper(): c.get("lot_prefix")
              for c in lot_cards or [] if c.get("sku")}

    for key, l in live.items():
        put(l.sku.strip(), l.title, l.price, l.item_id, "listed", lot_of.get(key))

    for key, s in sold.items():
        if key in live:            # relisted, or quantity > 1: live wins today
            continue
        cur = exist.get(key)
        if cur is None and key not in lot_of:
            continue               # a sale with no card on record: history, not stock
        put(str(s.get("sku")).strip(), s.get("title"), None, s.get("item_number"),
            "sold", lot_of.get(key))

    for c in lot_cards or []:
        sku = str(c.get("sku") or "").strip()
        key = sku.upper()
        if not sku or key in live or key in sold or key in rows:
            continue
        cur = exist.get(key)
        if cur is None:
            put(sku, c.get("title"), None, None, "intake", c.get("lot_prefix"))

    for key, cur in exist.items():
        if key in live or key in sold or key in rows:
            continue
        if cur.get("status") == "listed":
            put(cur["sku"], cur.get("title"), None, None, "ended", None)

    return {"rows": list(rows.values()), "counts": counts}


# ─── Reconcile ───────────────────────────────────────────────────────────────

def reconcile(inventory, report_listings) -> dict:
    """What disagrees between inventory and the live eBay report, both ways."""
    inv = {str(c.get("sku") or "").strip().upper(): c for c in inventory or []}
    live = {(l.sku or "").strip().upper(): l for l in report_listings or [] if l.sku}
    no_sku = [l for l in report_listings or [] if not (l.sku or "").strip()]
    return {
        "live_not_in_inventory": [live[k] for k in live if k not in inv],
        "listed_not_live": [c for k, c in inv.items()
                            if c.get("status") == "listed" and k not in live],
        "live_but_other_status": [(inv[k], live[k]) for k in live
                                  if k in inv and inv[k].get("status") not in ("listed",)],
        "live_no_location": [inv[k] for k in live
                             if k in inv and not parse_location(inv[k].get("location"))],
        "no_sku_on_ebay": no_sku,
    }


# ─── Pull list ───────────────────────────────────────────────────────────────

_ORDER_COLS = {
    "sku":   ["Custom label", "Custom Label", "Custom label (SKU)", "SKU"],
    "title": ["Item title", "Item Title", "Title"],
    "qty":   ["Quantity", "Qty"],
    "price": ["Sold for", "Sold For", "Item subtotal", "Total price", "Sale Price"],
    "order": ["Order number", "Order Number", "Sales record number", "Sales Record Number"],
    "buyer": ["Buyer username", "Buyer Username", "Buyer name", "Buyer Name"],
    "item":  ["Item number", "Item Number"],
}


def read_orders(text: str) -> list:
    """Rows of an eBay orders report. The header is found by content, not
    position, because eBay puts blank and summary rows above it."""
    rows = list(csv.reader((text or "").splitlines()))
    hdr_i = next((i for i, r in enumerate(rows)
                  if any(c.strip() in _ORDER_COLS["title"] for c in r)), None)
    if hdr_i is None:
        return []
    hdr = [c.strip() for c in rows[hdr_i]]

    def pick(d, field):
        for name in _ORDER_COLS[field]:
            if d.get(name, "").strip():
                return d[name].strip()
        return ""

    out = []
    for r in rows[hdr_i + 1:]:
        d = dict(zip(hdr, r))
        title = pick(d, "title")
        if not title:
            continue
        out.append({"sku": pick(d, "sku"), "title": title,
                    "qty": int(buying._money(pick(d, "qty")) or 1),
                    "price": buying._money(pick(d, "price")),
                    "order": pick(d, "order"), "buyer": pick(d, "buyer"),
                    "item": pick(d, "item")})
    return out


def pull_list(orders, inventory) -> dict:
    """Sold cards, sorted into the order you would walk the shelves."""
    inv = {str(c.get("sku") or "").strip().upper(): c for c in inventory or []}
    lines = []
    for o in orders or []:
        card = inv.get(o["sku"].upper()) if o["sku"] else None
        loc = (card or {}).get("location") or ""
        lines.append({
            **o,
            "location": loc,
            "located": bool(parse_location(loc)),
            "in_inventory": card is not None,
            "authenticity_guarantee": o["price"] >= AUTHENTICITY_GUARANTEE_FROM,
            "signature": o["price"] >= SIGNATURE_FROM,
        })
    lines.sort(key=location_sort_key)
    return {"lines": lines,
            "unlocated": [l for l in lines if not l["located"]],
            "not_in_inventory": [l for l in lines if not l["in_inventory"]]}


# ─── Summary ─────────────────────────────────────────────────────────────────

def summary(cards, boxes=None) -> dict:
    by = {s: 0 for s in STATUSES}
    located = cost = value = 0
    for c in cards or []:
        by[c.get("status") if c.get("status") in by else "intake"] += 1
        if parse_location(c.get("location")):
            located += 1
        if c.get("status") not in ("sold",):
            cost += buying._money(c.get("cost"))
            value += buying._money(c.get("est_value") or c.get("list_price"))
    on_hand = len(cards or []) - by["sold"]
    box_cards = sum(int(buying._money(b.get("card_count"))) for b in boxes or [])
    return {"cards": len(cards or []), "on_hand": on_hand, "by_status": by,
            "located": located,
            "located_pct": round(located / on_hand * 100, 1) if on_hand else None,
            "cost": round(cost, 2), "value": round(value, 2),
            "boxes": len(boxes or []), "box_cards": box_cards,
            "total_on_hand": on_hand + box_cards}


SETUP_SQL = """-- Master inventory. Run once in Neon (console.neon.tech → dfs-crm-prod →
-- SQL Editor → main branch). Also needs inventory_cards and inventory_boxes
-- in the Worker's ALLOWED_TABLES, then a Worker deploy.

create table if not exists inventory_cards (
  id                 bigint primary key generated always as identity,
  sku                text not null unique,
  title              text,
  player             text,
  year               text,
  set_name           text,
  card_number        text,
  parallel           text,
  serial             text,
  sport              text,
  grader             text,
  grade              text,
  cert_number        text,
  status             text not null default 'intake',
  status_updated_at  timestamptz default now(),
  location           text,          -- B#-R#-P#
  box_code           text,          -- B# — the box this card lives in
  lot_prefix         text,
  item_number        text,
  list_price         numeric,
  cost               numeric,
  est_value          numeric,
  est_value_at       timestamptz,
  notes              text,
  created_at         timestamptz default now(),
  updated_at         timestamptz default now()
);
create index if not exists idx_inv_status   on inventory_cards(status);
create index if not exists idx_inv_box      on inventory_cards(box_code);
create index if not exists idx_inv_lot      on inventory_cards(lot_prefix);

create table if not exists inventory_boxes (
  id           bigint primary key generated always as identity,
  box_code     text not null unique,  -- B14
  label        text,                  -- "2023 Prizm FB base"
  sport        text,
  pile         text,                  -- singles / doubles / triples / home_runs / mixed
  card_count   integer default 0,
  est_value    numeric,               -- whole box
  shelf        text,                  -- where the box itself sits
  notes        text,
  counted_at   timestamptz,
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);"""
