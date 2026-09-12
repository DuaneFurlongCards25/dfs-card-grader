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

# Team nicknames, copied from the sets already in app.py so this module stays
# importable and testable on its own. Aliases matter: a title may say "Niners"
# or "49ers", "A's" or "Athletics", and a spot bought as "Athletics" must still
# claim a card titled "A's".
NFL = {"49ers", "49's", "Niners", "Bears", "Bengals", "Bills", "Broncos",
       "Browns", "Buccaneers", "Cardinals", "Chargers", "Chiefs", "Colts",
       "Commanders", "Cowboys", "Dolphins", "Eagles", "Falcons", "Giants",
       "Jaguars", "Jets", "Lions", "Packers", "Panthers", "Patriots",
       "Raiders", "Rams", "Ravens", "Saints", "Seahawks", "Steelers",
       "Texans", "Titans", "Vikings"}
MLB = {"A's", "Angels", "Astros", "Athletics", "Blue Jays", "Braves",
       "Brewers", "Cardinals", "Cubs", "Diamondbacks", "Dodgers", "Giants",
       "Guardians", "Indians", "Mariners", "Marlins", "Mets", "Nationals",
       "Orioles", "Padres", "Phillies", "Pirates", "Rangers", "Rays",
       "Red Sox", "Reds", "Rockies", "Royals", "Tigers", "Twins",
       "White Sox", "Yankees"}
NBA = {"76ers", "Sixers", "Blazers", "Bucks", "Bulls", "Cavaliers", "Celtics",
       "Clippers", "Grizzlies", "Hawks", "Heat", "Hornets", "Jazz", "Kings",
       "Knicks", "Lakers", "Magic", "Mavericks", "Nets", "Nuggets", "Pacers",
       "Pelicans", "Pistons", "Raptors", "Rockets", "Spurs", "Suns",
       "Thunder", "Timberwolves", "Warriors"}
ALL_TEAMS = NFL | MLB | NBA

# Same club, different word. Either side of a pair claims the other's cards.
TEAM_ALIASES = {
    "49ers": {"49's", "niners"}, "49's": {"49ers", "niners"},
    "niners": {"49ers", "49's"},
    "athletics": {"a's"}, "a's": {"athletics"},
    "76ers": {"sixers"}, "sixers": {"76ers"},
    "guardians": {"indians"}, "indians": {"guardians"},
}


def _team_keys(value: str) -> set:
    """Every spelling of a team that should claim the same card."""
    v = (value or "").strip().lower()
    return {v} | TEAM_ALIASES.get(v, set())


def team_in_title(title: str):
    """The team a card belongs to, or None.

    Checks the END of the title first — 86% of football titles put the
    nickname last under the slot format — then anywhere, which catches the
    remaining 14% that carry it mid-title.
    """
    t = (title or "").strip()
    if not t:
        return None
    words = t.split()
    for n in (2, 1):                      # "Red Sox" before "Sox"
        if len(words) >= n:
            tail = " ".join(words[-n:]).strip(" .,")
            for team in ALL_TEAMS:
                if tail.lower() == team.lower():
                    return team
    low = t.lower()
    for team in sorted(ALL_TEAMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(team.lower())}\b", low):
            return team
    return None


def serial_in_title(title: str):
    """Print run as an int — '/25' -> 25. None when the card is unnumbered.

    Real store titles write the run four ways: "/25", "#/199", "#106/125"
    (card number then run), and "1/1". So the slash may be preceded by
    whitespace, a '#', or the card number itself. What it must NOT follow is a
    letter — that would read the "25" out of "PD-185/25"-style set codes and,
    worse, out of date ranges. Measured against the 11 Sep active-listings
    file: 237 titles carry a print run, and this catches all 237.
    """
    m = re.search(r"(?:^|[\s#\d])/\s?(\d{1,5})\b", title or "")
    return int(m.group(1)) if m else None


def _caps_name(title: str) -> str:
    """The ALL-CAPS run the slot title format puts first."""
    run, best = [], []
    for w in (title or "").split():
        core = w.strip("()[],.")
        if core.isupper() and len(core) >= 2 and not re.search(r"\d", core):
            run.append(core)
        else:
            if len(run) > len(best):
                best = run
            run = []
    if len(run) > len(best):
        best = run
    return " ".join(best)


def match_spot(title: str, spots):
    """Which spot claims this card? Returns the spot dict, or None.

    Deliberately returns None rather than guessing. A break always throws
    cards that belong to nobody's slot, and a wrong attribution corrupts the
    per-spot P&L in a way that is invisible later.
    """
    if not title or not spots:
        return None
    low = title.lower()
    caps = _caps_name(title)
    ser = serial_in_title(title)
    team = team_in_title(title)

    for sp in spots:
        kind = (sp.get("spot_type") or "").lower()
        val = (sp.get("spot_value") or "").strip()
        if not val:
            continue
        if "team" in kind:
            if team and team.lower() in _team_keys(val):
                return sp
        elif "player" in kind:
            v = val.lower()
            if v and (v in caps.lower() or v in low):
                return sp
        elif "serial" in kind:
            # "/25" or "25" — the spot is every card numbered to that or tighter
            m = re.search(r"(\d+)", val)
            if m and ser is not None and ser <= int(m.group(1)):
                return sp
    return None


def attribute(cards, spots) -> dict:
    """Split a break's cards across its spots. Unclaimed cards are returned.

    `cards` — dicts with at least a title, plus whatever P&L fields are needed.
    """
    by_spot = {sp.get("id") or sp.get("spot_value"): [] for sp in (spots or [])}
    unclaimed = []
    for c in (cards or []):
        sp = match_spot(c.get("title") or c.get("Title") or "", spots)
        if sp is None:
            unclaimed.append(c)
        else:
            by_spot[sp.get("id") or sp.get("spot_value")].append(c)
    return {"by_spot": by_spot, "unclaimed": unclaimed}


def spot_pnl(spot, cards, comps=None, fvf_pct=None) -> dict:
    """P&L for one spot — its own cost against what its cards returned."""
    cost = _money(spot.get("cost"))
    realized = round(sum(_money(c.get("net_proceeds")) for c in (cards or [])), 2)
    projected = 0.0
    if comps:
        try:
            from dfs_buying import lot_projection
            kw = {"fvf_pct": fvf_pct} if fvf_pct is not None else {}
            projected = lot_projection(comps, **kw)["net"]
        except Exception:
            projected = 0.0
    pl = round(realized - cost, 2)
    return {
        "cost": cost, "realized": realized, "projected": projected,
        "sold": len(cards or []), "pl": pl,
        "roi": round(pl / cost * 100, 1) if cost else None,
        "all_in_pl": round(realized + projected - cost, 2),
    }


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
create index if not exists idx_pl_is_break on purchase_lots(is_break);

-- One row per spot bought. Teams in a PYT break are never the same price,
-- so cost lives per spot, not on the break.
create table if not exists break_spots (
  id           bigint primary key generated always as identity,
  break_prefix text not null,
  spot_type    text not null default 'Team',
  spot_value   text not null,
  cost         numeric not null default 0,
  notes        text,
  created_at   timestamptz default now()
);
create index if not exists idx_bs_prefix on break_spots(break_prefix);"""
