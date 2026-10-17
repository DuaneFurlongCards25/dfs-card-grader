# CardPulse Feature Buildout — Spec for Claude Code

**Read `CLAUDE.md` in this folder first — it has full architecture, secrets locations, deployment steps, and known-issue history. This spec assumes that context and only adds what's new.**

Context: this app already handles card research, scanning, reprice, purchases/P&L. The gaps below came out of an ops-planning review against Duane's actual eBay inventory data and three sourcing/ops strategy docs. Build in the order listed — items 1 and 2 unblock tonight's intake batch and the current dead-stock cleanup; the rest are structural.

---

## 0. Before writing code

- Grep `app.py` for the **Shipment Intake** tab (`tab5`) implementation to find its actual Supabase table name and schema — it's not in the documented `Supabase Tables Used` list in CLAUDE.md, so don't assume a name; confirm it first.
- Grep `app.py` for the **Reprice Assistant** section to confirm the exact session-state key and dataframe columns for comp/trend output — needed for item 3 below.
- Do not rename or drop any existing Supabase table/column without asking — `purchase_lots` and `sales_records` are live production tables with real data in them.

---

## 1. Inventory pipeline status tracking (highest priority)

**Problem:** A card can be added to CardPulse (via Shipment Intake or the Scan tab) and never make it to an eBay listing, with nothing surfacing that fact. Duane just took in a new batch tonight — this is the live test case.

**Build:**
- Add a `status` column (text, default `'intake'`) to whichever table backs Shipment Intake, with allowed values: `intake`, `priced`, `photographed`, `listed`, `sold`. If Shipment Intake doesn't already write one row per card, it needs to.
- Add a `status_updated_at` timestamp column, updated whenever `status` changes.
- New view/tab section: **"Unlisted Inventory"** — shows every card where `status != 'listed'` and `status != 'sold'`, sorted by how long it's been sitting (`now() - status_updated_at`), with a visible age in days.
- Flag rows red/yellow when age exceeds a configurable threshold (default 3 days — Duane's sourcing docs assume same-day-or-next-day listing).
- When a card is exported via the Scan tab's eBay CSV export, or added to a File Exchange revise/relist batch, auto-update its `status` to `listed` if a matching record exists (match on SKU/Custom Label).

**Acceptance:** Opening the app after an intake session shows a clear count of "X cards intaken, Y still unlisted, oldest N days" — no manual CSV cross-referencing required.

---

## 2. Aging / dead-stock detector (built into the app, not a one-off script)

**Problem:** Right now finding "180+ days old, zero watchers" listings requires manually pulling an eBay report and running a script outside the app. This needs to be a standing feature since it will recur every month.

**Build:**
- New tab section (in Operations or a new "Health" section): upload an eBay "All active listings" CSV (same format already used elsewhere in the app — see `eBay-all-active-listings-report-*.csv` files in this folder for the exact columns) and compute:
  - Age in days per listing (`Start date` parsing — note the format is `%b-%d-%y %H:%M:%S PDT/PST`, strip the timezone abbreviation before parsing with `strptime`, it fails otherwise)
  - Buckets: 0-30 / 31-60 / 61-90 / 91-180 / 181-365 / 365+
  - A "dead stock" flag: age ≥ 180 days AND watchers = 0
- Auto-tier each dead-stock row using the Piles system already used elsewhere in Duane's docs: Singles $1-3, Doubles $4-6, Triples $6-10, Home Runs $10+.
- One-click export: a File Exchange-format Revise CSV (`Action,ItemID,CustomLabel,StartPrice` — see any `eBay_FileExchange_Revise_*.csv` in this folder for the exact header/format) that floors Singles/Doubles/Triples to a configurable price (defaults: $0.99/$1.99/$3.99), and excludes Home Runs ($10+) into a separate "manual review" export instead of auto-pricing them.
- Store the last-run date/results so re-running monthly is one click, not a rebuild.

**Acceptance:** Running this on a fresh active-listings export reproduces the same numbers as the manual pull did (882 dead listings as of 2026-09-14 — use as a test fixture if that file's still in the folder).

---

## 3. Bulk lot evaluator (pre-purchase)

**Problem:** Card Research's Grade-vs-Flip evaluates one card. There's no tool for scoring a prospective bulk lot buy before committing money.

**Build:**
- New section (Purchases tab or standalone): input a lot cost and a list of expected cards (paste a checklist, or CSV upload with estimated values).
- Auto-tier each card via the Piles system, sum values per tier.
- Implement the "strike" logic from the ops blueprint:
  ```python
  def evaluate_bulk_lot(lot_cards, lot_cost):
      hits = {"singles": 0, "doubles": 0, "triples": 0, "home_runs": 0}
      potential_revenue = 0
      for card in lot_cards:
          if card.value >= 10:
              hits["home_runs"] += 1
              potential_revenue += card.value
          elif 6 <= card.value < 10: hits["triples"] += 1
          elif 4 <= card.value < 6: hits["doubles"] += 1
          elif 1 <= card.value < 3: hits["singles"] += 1
      if hits["home_runs"] >= 1 and potential_revenue >= lot_cost:
          return "STRIKE: Profit Secured. Home runs cover the lot."
      return "PASS: Margin Insufficient."
  ```
- Also show it against Duane's own existing rule (35% return after 14.4% eBay fee, max-pay-per-card table already in his buying criteria) as a second verdict alongside the strike/pass call — don't replace his existing math, show both.
- Wire this into `dfs_buying.py` if that's where similar logic already partially lives — check it first rather than duplicating.

**Acceptance:** Given a pasted checklist and a lot price, returns both verdicts (strike/pass, and his 35%-return check) with per-tier breakdown.

---

## 4. Cost Basis vs. Estimated Current Value (ECV), persisted

**Problem:** `purchase_lots` tracks cost. Current market value only exists transiently in the Reprice Assistant's session state — never saved. There's no way to answer "what is my inventory actually worth right now" without re-running repricing on everything.

**Build:**
- Add `est_current_value` and `ecv_updated_at` columns to the per-card inventory table (whichever table holds individual cards — likely the same one from item 1's Shipment Intake work, or wherever Reprice Assistant reads/writes inventory rows; confirm structure before adding).
- When Reprice Assistant runs a comp/trend refresh on a card, persist the resulting comp value as `est_current_value` instead of only holding it in `st.session_state`.
- Add a simple portfolio summary metric: total Cost Basis vs. total ECV across all unsold inventory, shown somewhere visible (Operations tab header or a new Overview).

**Acceptance:** After running Reprice Assistant once, closing and reopening the app still shows the updated ECV per card — it survives a session refresh.

---

## 5. Grading outcome tracking

**Problem:** The 2x-rule and 70%-gem-rate targets from the ops docs are strategy, not tracked. Submission Tracker shows cards added from research, but not what a card actually graded once it comes back.

**Build:**
- Add fields to the submission tracker's backing table: `estimated_psa10_value`, `actual_grade` (nullable until known), `graded_date`.
- When `actual_grade` is filled in, compute whether the submission passed the 2x rule at time of submission (est. PSA10 value ≥ 2 × (raw cost + grading fee), or 1.5× if raw cost > $500).
- Add a rolling gem-rate metric: `(count of actual_grade == 10) / (count of graded submissions)` over the last N submissions, displayed with a flag if it drifts under 50% or over 90%.

**Acceptance:** After manually logging a handful of past submission outcomes, the app shows a real gem-rate percentage, not a placeholder.

---

## 6. Box-Row-Position (BRP) location field

**Problem:** No location field exists anywhere in the schema. Needed to make the "list everything, sub-two-minute pull" approach viable at volume.

**Build:**
- Add a `location` text column (format `B#-R#-P#`) to the per-card inventory table.
- Editable in the Scan tab review table and in Shipment Intake.
- When exporting an eBay Add/Revise CSV, append `Location: B#-R#-P#` to the end of the item description automatically (not just store it — it has to end up on the live listing to be useful).

**Acceptance:** A card scanned with a location set produces an eBay CSV row whose description ends with the location tag.

---

## 7. Numbered-parallel pricing fix (flagged in CLAUDE.md already, prioritize it)

**Problem:** CardHedger doesn't store print runs, so FMV on a `/25` or `/99` card understates real value. This directly undercuts Duane's core buying criteria (he specifically targets numbered parallels /99 or lower).

**Build:** Per the "Planned fix" already noted in CLAUDE.md — add a manual Serial # field (`/75` format) to the Scan review table, and apply a configurable premium multiplier to FMV when a serial number is present (start conservative, make it tunable, don't hardcode a permanent multiplier without Duane's input on the value).

**Acceptance:** A scanned numbered parallel shows an adjusted price distinct from its base-parallel FMV, with the adjustment visible/editable, not silently baked in.

---

## 8. Targets dashboard

**Problem:** No single screen shows progress against Duane's actual goals: $1k/week net profit (near-term), $30k gross / $8-9k profit per month (long-term).

**Build:**
- Simple Overview section: pull from Sales & P&L data, show current week's net profit vs. $1k target, current month's gross vs. $30k and profit vs. $8-9k, with a plain progress bar or percentage — no new data source needed, this is a rollup of what Sales & P&L already computes.

**Acceptance:** Opens to a single number: "this week: $X net of $1,000 target."

---

## Do not build yet (explicitly out of scope for this pass)
- GemRate official API integration — still pending pricing research per CLAUDE.md, don't build against it until a key exists.
- Stripe/monetization — explicitly deferred until after beta testing per CLAUDE.md.
- Anything touching the eBay API — already confirmed rejected, don't re-attempt.
