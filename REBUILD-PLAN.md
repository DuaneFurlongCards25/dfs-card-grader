# CardPulse → web app — review of Leumas Live, and the plan

Written 17 Oct 2026, after reading Leumas Live v2.21.1395's full rendered
interface (120k characters of it). Not its source code — its *interface*.
What he chose to show, and in what order, is the part worth learning from and
the part that is ours to use.

Context worth keeping in mind: Leumas said himself he started from another app
he liked and kept improving it. That is this, one step further on.

---

## 1. What he is actually running

A single-page web app — React-shaped, Supabase for sign-in and database, eBay
OAuth for the live connection. Everything loads once and runs in the browser.
That is why it feels instant and CardPulse does not: **Streamlit re-runs the
whole script on every click.** Our measured floor is ~1s per query and ~1.9s to
sign in. His is a browser filtering an array it already holds.

That single architectural fact is most of "I like his better."

---

## 2. The eight things he does better, and why each one works

**1 — One grid is the app.** Inventory is a table with checkboxes and two
menus: `Filters ▾` and `Actions ▾`. List, reprice, combine, hold, pause, label,
export — all of it happens to the rows you ticked, without leaving the page.
CardPulse spreads the same work across seven tabs, so you have to know which
tab a job lives in before you can start it.

**2 — A colour contract, stated in one line.** Printed right in the app:

> "Teal buttons read. Gold buttons change a live marketplace — you always
> confirm first. Red buttons remove."

Three sentences and you can never again be unsure whether a button is about to
touch a live listing. We have nothing like this, and it costs almost nothing.

**3 — Preview first, always.** Every destructive or marketplace-touching
action is dry-run → review → approve → push. His duplicate merger, his import
reconciler, his combine scanner all say some version of "nothing changes until
you approve." That is a *trust* feature, and trust is what makes someone
willing to click the big buttons.

**4 — Onboarding that unlocks.** "Get your account set up — 0 of 10 steps
done. Each step unlocks the next feature." You are never staring at a full app
wondering where to begin. Directly relevant: this is what Taylor will hit.

**5 — He explains his own numbers, underneath them.** Verbatim from his
dashboard:

> "Avg daily deposit — what eBay actually paid you over the last 90 days,
> after fees and refunds, divided by 90."

Nobody has to ask what a number means or go and check it in a spreadsheet.
Our Sales & P&L has numbers with no such sentence under them.

**6 — It works on the phone, properly.** A bottom bar: Pick · Orders ·
Inventory · Home · More. Built for standing at a card show, not for a desk.

**7 — Pricing is rules, not a spreadsheet.** Bands (market $X–$Y lists at $Z),
floors, multipliers, rounding to .99, a max % move per apply, and the smart
one — **band-edge stickiness**: a card whose market hovers at a band boundary
keeps its price until the market clears the edge by 3%, so it moves on a trend
and not on noise. That is a real answer to a real problem in our Sunday
Reprice, and it is ours to implement because it is an idea, not his code.

**8 — He names the source of truth and then reconciles to it.** "Leumas is the
source of truth. Syncs no longer overwrite your data — they just report what
eBay shows." Then an eBay Mismatches page listing every disagreement for you to
fix in bulk. Our reconciliation is a CSV diff we run and read; his is a
permanent page that is either empty or has work on it.

---

## 3. Where he does not fit us — read this before copying anything

**He has the eBay API. We do not, and we are not pretending otherwise.**
His live sync, his ReviseItem price pushes, his instant order feed — all of it
rests on an API we have been refused. Our equivalent is the loop we already
have: download the active-listings report, diff it, emit a File Exchange CSV,
upload it. Slower, entirely workable, and already built. **Every "sync" in our
version means that loop, and the UI should say so plainly rather than implying
something live.**

Worth noting for later: he is approved as an *application developer*, which is
a different door from the one a seller knocks on. Having a real app may be what
eventually opens it for us. Not a dependency — a possibility.

**He is TCG-first; we are graded sports.** His market prices come from
TCGplayer. For a PSA 10 rookie that number does not exist. **Our price source
is CardHedger FMV, which we already have a direct connection to** — and for
our inventory it is simply better data than his.

**Things of his we should not build:** playable decks, set-completion grids,
reverse-holo tracking, master-set lots. All Pokémon machinery. His own roadmap
lists "Sports cards at scale" as *not built yet* — which is the gap our app
already lives in.

**Things we have that he does not:** PSA cert handling, grade-vs-flip analysis,
CardHedger comps, the photo scanner we shipped today, post graphics, breaks,
consignment, DC Sports, Whatnot buying. None of that goes away.

---

## 4. The plan

### Target

| | Today | After |
|---|---|---|
| Address | `thecardpulse.streamlit.app` | **`app.dfscards.com`** |
| Front end | Streamlit, server-rendered | React + Vite, static on Cloudflare Pages |
| API | `dfs-cards-api` Worker | **same Worker** — already has auth, Neon, R2 |
| Database | Neon | **same Neon** — no migration |
| Phone | unusable | bottom bar, works at a show |

Only the front end is replaced. The Worker, the database, the pricing logic and
the scanner all stay. This is not starting over.

### How it gets built without ever leaving you without an app

Six slices. **Each one ends with something you can use**, and Streamlit keeps
running the whole time until nothing needs it.

**1 · Shell + inventory grid (read-only).** Sign in, the nav, and the one
screen that is the app: every listing in a virtualised table, instant
filter/sort/search, checkbox selection. No actions yet. The moment this exists
you will feel the difference, because 4,481 rows will filter with no wait.

**2 · Actions on the selection.** The seven Operations tabs become bulk actions
on ticked rows: reprice, promote, end & relist, export to Heystack / Card Luma
/ Shopify, build the File Exchange CSV. Preview → approve → download, every
time. Colour contract and its legend go in here.

**3 · Orders, sales and P&L.** Order import, the sold-card detector that caught
12 cards about to be relisted, margins by lot. Plain-English sentence under
every number.

**4 · Pricing rules.** Bands, floors, rounding, max-move cap, band-edge
stickiness — fed by CardHedger FMV. This replaces Sunday Reprice with something
that explains itself before it changes anything.

**5 · Phone + scanner + posts.** Bottom bar, the scanner we built today folded
in so a shot becomes a draft listing, and the post graphics.

**6 · Retire Streamlit.** Only when nothing is left that needs it.

### What goes in from the start, because retrofitting it is harder

- The button colour contract, with its legend
- Preview-before-apply on anything that touches money or a live listing
- A sentence under every number saying where it came from
- A setup guide that unlocks — the thing Taylor will meet first

---

## 5. Open questions

1. `app.dfscards.com`, or a different subdomain? (The apex stays on Shopify.)
2. Hybrid transition as above, or a straight cutover?
3. Which screen frustrates you most in CardPulse today — that one gets built
   first after the grid.
