"""Break economics — did buying into that break actually make money?

A break is a group buy: somebody opens a box or case live, and you pay for a
slot in it. The slot might be a team, a player, a division, or a serial-number
range. Whatever lands in your slot is yours. You then sell it, usually on eBay
or in the seller's own social channels.

The question nobody tracks honestly is whether the spots pay. It is easy to
remember the case hit and forget the eleven breaks before it that returned a
stack of base. This module exists to answer that from records rather than
memory.

## Why a break is modelled as a lot

Structurally a break IS a purchase lot: money out on a date, cards in, sold off
over time. Reusing `purchase_lots` means break P&L, ROI, turn rate, the
SKU-prefix rollup, the comp projection and the consignment flow all work on
breaks the day they are added, with no duplicated code. The break-specific
fields (breaker, platform, spot type) ride along as extra columns.

## Two numbers, never conflated

`realized` is money actually received, from sales_records.
`projected` is what the unsold cards comp at, which is a best case.

A break is only judged "paid" on realized money. Projection is shown beside it
so an open break is not mistaken for a loss just because nothing has sold yet —
but it never counts toward the verdict.
"""

from __future__ import annotations

import collections
import datetime as dt
import re

# What you can buy into. Free text is allowed too — these drive the dropdown.
SPOT_TYPES = [
    "Team (PYT)", "Random Team", "Player", "Division",
    "Serial Number", "Hit Draft", "Personal Break", "Other",
]

PLATFORMS = [
    "Whatnot", "Fanatics Live", "eBay Live", "Layton Sports",
    "Facebook Live", "Instagram Live", "In Person", "Other",
]


def _money(v) -> float:
    """A dollar figure from anywhere — form input, DB numeric, or "$1,234.56"."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v))
    try:
        return float(s) if s not in ("", "-", ".", "-.") else 0.0
    except ValueError:
        return 0.0


def break_cost(row) -> float:
    """All-in cost of the break: what was paid for spots, plus shipping.

    Shipping is part of the cost of getting the cards, not an afterthought.
    On a $20 team spot a $6 shipping charge is 30% of the outlay, and a break
    that looks break-even on spot price alone is a loss once it lands.
    """
    return round(_money(row.get("total_cost")) + _money(row.get("ship_cost")), 2)


def break_pnl(row, sales, comps=None, fvf_pct=None) -> dict:
    """P&L for one break.

    `sales`  — sales_records rows already filtered to this break.
    `comps`  — comp/asking values for the cards still unsold, any format.
    """
    cost = break_cost(row)
    realized = round(sum(_money(s.get("net_proceeds")) for s in (sales or [])), 2)
    sold_n = len(sales or [])

    projected = 0.0
    unsold_n = 0
    if comps:
        try:
            from dfs_buying import lot_projection
            kw = {"fvf_pct": fvf_pct} if fvf_pct is not None else {}
            proj = lot_projection(comps, **kw)
            projected, unsold_n = proj["net"], proj["cards"]
        except Exception:
            projected, unsold_n = 0.0, 0

    pl = round(realized - cost, 2)
    all_in = round(realized + projected - cost, 2)
    return {
        "cost": cost,
        "realized": realized,
        "projected": projected,
        "sold": sold_n,
        "unsold": unsold_n,
        "cards": int(row.get("card_count") or 0) or (sold_n + unsold_n),
        "pl": pl,
        "roi": round(pl / cost * 100, 1) if cost else None,
        "all_in_pl": all_in,
        "all_in_roi": round(all_in / cost * 100, 1) if cost else None,
        # Only realized money decides this. An open break is "open", not a loss.
        "verdict": ("paid" if pl > 0 else "lost") if sold_n and not unsold_n
                   else ("ahead" if pl > 0 else "open"),
        "recovered_pct": round(realized / cost * 100, 1) if cost else None,
    }


def summarize(rows) -> dict:
    """Roll many breaks up by breaker, platform and spot type.

    This is the point of the whole feature. One break tells you nothing —
    variance is enormous and a single case hit pays for a lot of base. Twenty
    breaks tell you which breaker, which platform and which kind of spot
    actually returns money, which is a buying decision you can act on.

    Only CLOSED breaks (everything sold) count toward win rate and ROI. An open
    break has unsold cards whose value is unknown, and letting those in would
    flatter or punish a breaker for cards nobody has tried to sell yet.
    """
    def bucket(key):
        out = collections.defaultdict(lambda: {
            "breaks": 0, "closed": 0, "wins": 0,
            "cost": 0.0, "realized": 0.0, "pl": 0.0,
        })
        for r in rows:
            k = (r.get(key) or "").strip() or "—"
            p = r["pnl"]
            b = out[k]
            b["breaks"] += 1
            b["cost"] += p["cost"]
            b["realized"] += p["realized"]
            if p["verdict"] in ("paid", "lost"):
                b["closed"] += 1
                b["pl"] += p["pl"]
                if p["pl"] > 0:
                    b["wins"] += 1
        for k, b in out.items():
            b["cost"] = round(b["cost"], 2)
            b["realized"] = round(b["realized"], 2)
            b["pl"] = round(b["pl"], 2)
            b["roi"] = round(b["pl"] / b["cost"] * 100, 1) if b["cost"] else None
            b["win_rate"] = round(b["wins"] / b["closed"] * 100, 1) if b["closed"] else None
        return dict(out)

    tot_cost = round(sum(r["pnl"]["cost"] for r in rows), 2)
    tot_real = round(sum(r["pnl"]["realized"] for r in rows), 2)
    closed = [r for r in rows if r["pnl"]["verdict"] in ("paid", "lost")]
    wins = [r for r in closed if r["pnl"]["pl"] > 0]
    return {
        "breaks": len(rows),
        "closed": len(closed),
        "open": len(rows) - len(closed),
        "cost": tot_cost,
        "realized": tot_real,
        "pl": round(tot_real - tot_cost, 2),
        "roi": round((tot_real - tot_cost) / tot_cost * 100, 1) if tot_cost else None,
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "by_breaker": bucket("breaker"),
        "by_platform": bucket("platform"),
        "by_spot_type": bucket("spot_type"),
        "by_buyer": bucket("bought_by"),
    }


def suggest_prefix(breaker: str, when=None) -> str:
    """A SKU prefix for the break, in the shape the lot rollup already expects.

    Lots resolve by the first two dash-separated segments, so the prefix has to
    carry one — BREAK-MMDDYY keeps every break in its own namespace while
    staying readable on a label.
    """
    when = when or dt.date.today()
    slug = re.sub(r"[^A-Za-z0-9]", "", (breaker or "BREAK")).upper()[:10] or "BREAK"
    return f"{slug}-{when:%m%d%y}"


SETUP_SQL = """-- Breaks ride on purchase_lots so every lot feature works on them.
alter table purchase_lots add column if not exists is_break    boolean not null default false;
alter table purchase_lots add column if not exists breaker     text;
alter table purchase_lots add column if not exists platform    text;
alter table purchase_lots add column if not exists product     text;
alter table purchase_lots add column if not exists spot_type   text;
alter table purchase_lots add column if not exists spot_detail text;
alter table purchase_lots add column if not exists spots       integer default 1;
alter table purchase_lots add column if not exists ship_cost   numeric default 0;
alter table purchase_lots add column if not exists bought_by   text;
create index if not exists idx_pl_is_break on purchase_lots(is_break);"""
