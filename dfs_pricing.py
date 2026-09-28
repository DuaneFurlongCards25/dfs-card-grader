"""What a card actually nets, and what it must sell for to hit a target.

Two directions, same arithmetic:

  net(price)      you sold at $X — what landed, and what margin was that
  price_for(...)  you want 12% on this — what does it have to sell for

## Why the reverse is not just cost x 1.12

eBay's fixed fee steps at $10 ($0.30 below, $0.40 above), so the equation
changes shape depending on the answer. Solving with the wrong tier gives a
price a few cents off, which then reports a margin that is not the one asked
for. `price_for` solves BOTH tiers and keeps the solution that is consistent
with its own fee — and says so when neither is (a target that can only be met
by a price straddling the step).

## Two different rates, deliberately kept apart

The published schedule (12.35% + fixed) answers "what will eBay charge me".
The measured all-in rate (14.4%, from 1,492 real payouts) already swallows
promoted-listing spend and everything else that came out, and answers "what
actually lands". Mixing them double-counts promoted spend. Each preset says
which kind it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Platform:
    name: str
    fee_pct: float                  # % of the sale price
    fixed: float = 0.0              # flat per-order fee
    fixed_over: float | None = None # different flat fee above `fixed_break`
    fixed_break: float = 10.00
    measured: bool = False          # True = rate already includes ad spend
    note: str = ""

    def fixed_fee(self, price: float) -> float:
        if self.fixed_over is None:
            return self.fixed
        return self.fixed_over if price > self.fixed_break else self.fixed


# Rates Duane has either measured or been quoted. Anything uncertain is left
# for him to type rather than guessed at.
PLATFORMS = {
    "eBay (store — published schedule)": Platform(
        "eBay (store — published schedule)", 0.1235, 0.30, 0.40,
        note="Trading-card final value fee plus the per-order fee: $0.30 at "
             "$10 and under, $0.40 above. Promoted-listing spend is NOT in "
             "this — add an ad rate below if the listing is promoted."),
    "eBay (schedule as % of gross)": Platform(
        "eBay (schedule as % of gross)", 0.144, 0.0, None,
        note="14.4% — the same 12.35% plus per-order fee, expressed as one "
             "rate against the whole sale. Checked against 1,113 eBay sales: "
             "the stored fees match that formula to $7.87 in total. It is NOT "
             "a measurement and does NOT include promoted-listing spend, so "
             "add an ad rate if the card is promoted."),
    "eBay (no store subscription)": Platform(
        "eBay (no store subscription)", 0.1325, 0.30, 0.30,
        note="The rate without a store subscription."),
    "CollX": Platform(
        "CollX", 0.08, 0.0, None,
        note="8% commission (Duane, 28 Sep 2026). Checked against his 129 CollX "
             "sales: what actually left was 8-10% of the sale price, median "
             "10.0%, never more than 10%. Set this to 10 if you want the "
             "worst case — 99 of those 129 orders came in at 10%. "
             "Shipping is a wash: the buyer pays it and CollX deducts the "
             "label, so it is not part of the commission."),
    "DC Sports87 (consignment)": Platform(
        "DC Sports87 (consignment)", 0.185, 0.0, None, measured=True,
        note="18.5% of the money across 418 real DC payouts — but the median "
             "card gives up 25.5%, because the cut lands hardest on cheap "
             "cards. 25 cards sold at $0.99 returned $0.00. $3 minimum, "
             "singles only as of Sept 2026."),
    "QuickConsign (consignment)": Platform(
        "QuickConsign (consignment)", 0.20, 0.0, None,
        note="Rate not yet measured — confirm with them and edit. $5 minimum."),
    "Custom": Platform("Custom", 0.0, 0.0, None, note="Type your own rate."),
}

# Envelope, sleeve, top loader, label. Postage on the $0.99 eBay Standard
# Envelope sits inside the measured take rate, so it is not here.
DEFAULT_SUPPLIES = 0.75


def _money(v) -> float:
    try:
        return float(str(v).replace("$", "").replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def net(price, cost, platform: Platform, *, supplies: float = DEFAULT_SUPPLIES,
        shipping: float = 0.0, ad_pct: float = 0.0, qty: int = 1) -> dict:
    """What one sale leaves behind.

    `ad_pct` is promoted-listing spend, charged on the sale price like the
    final value fee. It is ignored for a measured rate, which already has it.
    """
    price, cost = _money(price), _money(cost)
    supplies, shipping = _money(supplies), _money(shipping)
    ads = 0.0 if platform.measured else price * (_money(ad_pct) / 100.0)
    pct_fee = price * platform.fee_pct
    fixed = platform.fixed_fee(price) if price > 0 else 0.0
    fees = round(pct_fee + fixed + ads, 2)
    out_of_pocket = round(cost + supplies + shipping, 2)
    proceeds = round(price - fees, 2)
    profit = round(proceeds - out_of_pocket, 2)
    return {
        "price": round(price, 2), "cost": round(cost, 2),
        "fee_pct": round(pct_fee, 2), "fixed": round(fixed, 2),
        "ads": round(ads, 2), "fees": fees,
        "supplies": round(supplies, 2), "shipping": round(shipping, 2),
        "proceeds": proceeds, "profit": profit,
        "margin": round(profit / price * 100, 2) if price else None,
        "roi": round(profit / cost * 100, 2) if cost else None,
        "take_pct": round(fees / price * 100, 2) if price else None,
        "breakeven": breakeven(cost, platform, supplies=supplies,
                               shipping=shipping, ad_pct=ad_pct),
        "qty": max(1, int(qty or 1)),
        "profit_total": round(profit * max(1, int(qty or 1)), 2),
    }


def _solve_price(cost, platform: Platform, *, target: float, basis: str,
                 supplies: float, shipping: float, ad_pct: float):
    """The price itself, with no result dict — so breakeven() can use it
    without net() and price_for() calling each other in a circle."""
    cost, supplies, shipping = _money(cost), _money(supplies), _money(shipping)
    t = _money(target) / 100.0
    rate = platform.fee_pct + (0.0 if platform.measured else _money(ad_pct) / 100.0)
    base_cost = cost + supplies + shipping

    def solve(fixed):
        if basis == "roi":
            denom = 1.0 - rate
            if denom <= 0:
                return None
            return (cost * (1.0 + t) + supplies + shipping + fixed) / denom
        denom = 1.0 - rate - t
        if denom <= 0:
            return None
        return (base_cost + fixed) / denom

    answers = []
    if platform.fixed_over is None:
        p = solve(platform.fixed)
        if p is not None:
            answers.append(p)
    else:
        low = solve(platform.fixed)
        if low is not None and low <= platform.fixed_break:
            answers.append(low)
        high = solve(platform.fixed_over)
        if high is not None and high > platform.fixed_break:
            answers.append(high)
        if not answers and solve(platform.fixed) is not None:
            # Target lands exactly on the fee step — charge just over it.
            answers.append(platform.fixed_break + 0.01)
    if not answers:
        return None
    price = max(answers) if basis == "roi" else min(answers) + 0.004
    return max(round(price, 2), 0.01)


def price_for(cost, platform: Platform, *, target: float, basis: str = "margin",
              supplies: float = DEFAULT_SUPPLIES, shipping: float = 0.0,
              ad_pct: float = 0.0) -> dict:
    """The sale price that hits a target.

    basis="margin" — profit as a share of the SALE price (12% of what the
                     buyer pays). Cannot reach 100%; fees and costs eat the
                     rest, so a target at or above (1 - fee rate) is refused.
    basis="roi"    — profit as a share of what you PAID (make 12% on the buy).
    """
    rate = platform.fee_pct + (0.0 if platform.measured else _money(ad_pct) / 100.0)
    price = _solve_price(cost, platform, target=target, basis=basis,
                         supplies=supplies, shipping=shipping, ad_pct=ad_pct)
    if price is None:
        why = (f"that margin is impossible — fees alone take {rate*100:.1f}% "
               "of every sale") if basis == "margin" else \
              "fees exceed 100% of the sale price"
        return {"price": None, "why": why}
    res = net(price, cost, platform, supplies=supplies, shipping=shipping,
              ad_pct=ad_pct)
    res["target"] = _money(target)
    res["basis"] = basis
    res["hit"] = res["margin"] if basis == "margin" else res["roi"]
    return res


def breakeven(cost, platform: Platform, *, supplies: float = DEFAULT_SUPPLIES,
              shipping: float = 0.0, ad_pct: float = 0.0):
    """The sale price where profit is exactly zero."""
    return _solve_price(cost, platform, target=0.0, basis="margin",
                        supplies=supplies, shipping=shipping, ad_pct=ad_pct)


def max_buy(price, platform: Platform, *, target: float, basis: str = "margin",
            supplies: float = DEFAULT_SUPPLIES, shipping: float = 0.0,
            ad_pct: float = 0.0):
    """Working backwards: the most payable for a card expected to sell at
    `price` while still hitting the target."""
    price = _money(price)
    supplies, shipping = _money(supplies), _money(shipping)
    t = _money(target) / 100.0
    rate = platform.fee_pct + (0.0 if platform.measured else _money(ad_pct) / 100.0)
    proceeds = price * (1.0 - rate) - platform.fixed_fee(price)
    if basis == "roi":
        if 1.0 + t <= 0:
            return None
        return round(max(0.0, (proceeds - supplies - shipping) / (1.0 + t)), 2)
    return round(max(0.0, proceeds - supplies - shipping - price * t), 2)
