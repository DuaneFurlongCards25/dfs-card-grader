# Dead-Stock Reprice v2 — Before/After Analysis
*2026-09-15 — for review before uploading to eBay*

## Why v1 wasn't good enough
The first clearance batch (`eBay_FileExchange_Revise_DeadStock_Clearance_2026-09-14.csv`) floored item prices by tier but left the $0.99 shipping charge in place. Checking 3 of these listings against live eBay comps for the identical card showed the same pattern every time: your price + shipping was running **2-4x the market's price + shipping**, and none of the three ranked on the first page of results for their own exact card name — that's the real reason CTR is near zero on this tier, not the titles.

| Your listing | Your price + shipping | Market top comps | Where you rank |
|---|---|---|---|
| Sean Gamble 2025 Bowman Draft Chrome Refractor Royals | $3.49 + $0.99 = $4.48 | $2.00 free ship / $1.39+$0.74 | Not on page 1 of 430 results |
| Malik Nabers 2024 Donruss Optic Primary Colors #6 | $3.49 + $0.99 = $4.48 | $1.00–$1.99, several free ship | ~27th of 33 exact matches, sorted cheapest |
| Jalen Brunson 2024-25 Donruss Optic My House #12 | $6.49 + $0.99 = $7.48 | $0.99–$1.49 total | Not visible in top results of 251 |

## What changed in v2
Two moves, both aimed at Best Match ranking, not just clearing inventory:
1. **Shipping goes to $0.** eBay's ranking weights total price-to-buyer, not just item price — a $0.99-shipping listing loses to a free-shipping one at the same all-in cost.
2. **Item prices dropped further**, informed by the comp checks above — the old floors ($0.99/$1.99/$3.99) were set by *your current listed price bucket*, not by what these cards actually sell for. Live comps show most of this tier selling for $1-2 delivered regardless of bucket.

*Note: this is based on 3 spot-checked listings across the three tiers, not individual comps for all 862 — the pricing below is a data-informed rule applied uniformly, not a per-card comp match. If you want per-card comps, that's the CardPulse Reprice Assistant's job (see the feature-buildout spec, item 4) — worth running once that's built.*

## The numbers

| Tier | Count | Old delivered price (item + $0.99 ship) | New delivered price (item + free ship) | Cut |
|---|---|---|---|---|
| Singles | 285 | $0.99 + $0.99 = $1.98 → $564 total | $0.99 + $0 = $0.99 → $282 total | 50% |
| Doubles | 540 | $1.99 + $0.99 = $2.98 → $1,609 total | $1.49 + $0 = $1.49 → $805 total | 50% |
| Triples | 37 | $3.99 + $0.99 = $4.98 → $184 total | $2.49 + $0 = $2.49 → $92 total | 50% |
| **Total (862 listings)** | | **$2,358 total delivered value** | **$1,179 total delivered value** | **50%** |

That's not lost revenue — this stock has been sitting dead (180+ days, zero watchers) generating $0 either way. The $1,179 is what it takes to actually rank and move; the alternative is $0 forever. The 20 Home Runs ($10+, numbered parallels/NIL rookies) are untouched here — those get title/photo review, not a price cut.

## What I need before uploading
- **Green light on the price cut itself** — v2 is meaningfully lower than v1, want to confirm you're comfortable with it before it goes live on 862 listings.
- **How to actually set shipping to free.** I don't have a verified File Exchange column set for shipping changes in your folder — every prior revise file here only ever touched price. Rather than guess at columns and risk a bad upload across 862 live listings, I'd suggest one of two paths: (a) you set shipping via Seller Hub's bulk "Edit shipping" tool on a saved search for this batch (safe, UI-driven, no CSV risk), or (b) I build a test shipping-revise CSV for 5 listings first, you confirm it worked correctly on eBay, then we scale to all 862. Which do you want?
- File to upload once shipping is sorted: `eBay_FileExchange_Revise_DeadStock_Clearance_v2_CompChecked_2026-09-15.csv` (already in The CardPulse folder).
