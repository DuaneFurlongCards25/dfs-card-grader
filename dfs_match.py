"""Find the right CardHedger card for an eBay listing title.

CardHedger's AI matcher returns null for cards that are demonstrably in its
database. Jac Caglianone 2026 Topps Chrome Logofractor #131 is there, priced
at $13.64 raw, and `card-match` answers null for it — because the matcher only
evaluates the first ten search hits, and a player with 88 cards buries the
parallel you actually own under base, X-Fractor and Sapphire.

A plain search by player and card number returns every variant. This module
picks the right one from that list.

## Why the parallel is the whole problem

Within one player and card number, the variants differ only by parallel:
Base $0.49, X-Fractor $5.63, Logofractor $13.64, Image Variation $30.00. Pick
the wrong row and the reprice is wrong by 60x, silently. So the parallel is
scored hardest, in BOTH directions — a candidate carrying a parallel the title
never mentions is penalised exactly like a title parallel the candidate lacks.

## Deliberately refuses rather than guesses

A card number that does not match is disqualifying, not a deduction. Below
MIN_SCORE nothing is returned. A wrong price that looks confident is worse
than an empty cell a person can see and fill in.
"""

from __future__ import annotations

import re

# Parallel / variety words that actually separate one row from another.
# Ordered longest-first at compile time so "mini-diamond" wins over "diamond".
_PARALLEL = [
    "superfractor", "logofractor", "x-fractor", "xfractor", "refractor",
    "mini-diamond", "cracked ice", "image variation", "raywave", "sapphire",
    "atomic", "shimmer", "speckle", "velocity", "geometric", "reptilian",
    "negative", "prism", "prizm", "mojo", "lava", "aqua", "wave", "seams",
    "border", "disco", "choice", "holo", "foil", "hyper", "scope", "pulsar",
    "orange", "purple", "yellow", "green", "blue", "red", "gold", "black",
    "pink", "silver", "bronze", "neon", "teal", "white", "camo", "ice",
    "rainbow", "electric", "canvas", "vintage", "stock",
]
_PAR_RE = re.compile(r"\b(" + "|".join(sorted(
    (re.escape(w) for w in _PARALLEL), key=len, reverse=True)) + r")\b", re.I)

# Words that look like parallels but are set or product names.
_NOT_PARALLEL = {"prizm"}          # "Panini Prizm" is a set, not a parallel

_SET_NOISE = {"baseball", "basketball", "football", "soccer", "hockey",
              "the", "of", "and", "set", "base"}

MIN_SCORE = 3.0


def parse_title(title: str) -> dict:
    """Pull player, year, card number and parallel words out of a listing title."""
    t = re.sub(r"\s+", " ", (title or "").strip())
    year = None
    m = re.search(r"\b((?:19|20)\d{2})(?:-\d{2})?\b", t)
    if m:
        year = m.group(1)
    num = None
    m = re.search(r"#\s*([A-Za-z0-9][A-Za-z0-9\-]*)", t)
    if m:
        num = m.group(1).strip("-")
    # The slot title format opens with the player's name in caps.
    caps = []
    for w in t.split():
        core = w.strip("().,#/")
        if core.isupper() and len(core) >= 2 and not re.search(r"\d", core):
            caps.append(core.title())
        elif caps:
            break
    player = " ".join(caps) if caps else None
    return {"title": t, "player": player, "year": year, "number": num,
            "parallels": _parallels(t)}


def _parallels(text: str) -> set:
    found = {w.lower().replace("-", "") for w in _PAR_RE.findall(text or "")}
    return found - _NOT_PARALLEL


def _num_eq(a, b) -> bool:
    na = re.sub(r"[^a-z0-9]", "", str(a or "").lower())
    nb = re.sub(r"[^a-z0-9]", "", str(b or "").lower())
    return bool(na) and na == nb


def score(card: dict, want: dict) -> float:
    """How well one search hit matches the listing. Higher is better."""
    s = 0.0
    cset = (card.get("set") or "").lower()
    variant = (card.get("variant") or "").lower()
    title_l = want["title"].lower()

    if want["number"]:
        if _num_eq(card.get("number"), want["number"]):
            s += 3.0
        else:
            return -99.0          # different card, not a worse match

    if want["year"]:
        if want["year"] in cset:
            s += 2.0
        elif re.search(r"\b(19|20)\d{2}\b", cset):
            s -= 1.5              # a year, and it is the wrong one

    for w in set(re.findall(r"[a-z']{3,}", cset)) - _SET_NOISE:
        if w in title_l:
            s += 0.6

    want_par, got_par = want["parallels"], _parallels(variant + " " + cset)
    if want_par or got_par:
        s += 3.0 * len(want_par & got_par)
        s -= 1.5 * len(got_par - want_par)
        s -= 1.5 * len(want_par - got_par)
    if not want_par and variant in ("base", ""):
        s += 2.0                  # plain title, plain card
    return s


def raw_price(card: dict):
    for p in card.get("prices") or []:
        if str(p.get("grade", "")).strip().lower() == "raw":
            try:
                return float(p["price"])
            except (TypeError, ValueError, KeyError):
                pass
    return None


def pick(cards, want: dict, min_score: float = MIN_SCORE):
    """Best candidate, or (None, reason). Ties break toward a priced card."""
    if not cards:
        return None, "no candidates"
    scored = [(score(c, want), c) for c in cards]
    best = max(scored, key=lambda sc: (sc[0], raw_price(sc[1]) is not None))
    if best[0] < min_score:
        return None, f"best score {best[0]:.1f} below {min_score}"
    return best[1], f"score {best[0]:.1f} of {len(cards)} candidates"


def search_payloads(want: dict) -> list:
    """Search calls to try, cheapest and most specific first."""
    out = []
    if want["player"] and want["number"]:
        out.append({"player": want["player"], "number": want["number"],
                    "page": 1, "page_size": 100})
    if want["player"]:
        out.append({"player": want["player"], "page": 1, "page_size": 100})
    if not out and want["title"]:
        out.append({"search": want["title"][:120], "page": 1, "page_size": 50})
    return out


# ─── eBay sold search ────────────────────────────────────────────────────────
# Verified against live eBay on 23 Sep 2026 with a card CardHedger cannot
# price (Konnor Griffin 2025 Bowman's Best B25-KG Purple Refractor /75):
#
#   full listing title ................ 0 results
#   without the team nickname ......... 2 exact results ($344.99 / $799.99)
#
# Three things in a DFS title are poison to an eBay search, because no other
# seller writes them the same way: the "#" before the card number, the "/75"
# print run, and the team nickname the slot format appends. The card number
# itself stays — it is what makes the search exact.

_EBAY_DROP = re.compile(
    r"\b(RC|AU|AUTO|AUTOGRAPH|MEM|PATCH|SP|SSP|HOT|LOT|NM|MINT|"
    r"HOBBY|RETAIL|JUMBO|HTA|CHOICE|ROOKIE)\b", re.I)


def _teams():
    try:
        from dfs_breaks import ALL_TEAMS
        return ALL_TEAMS
    except Exception:
        return set()


def ebay_query(title: str) -> str:
    """Trim a listing title down to what eBay's sold search can actually find."""
    q = re.sub(r"\s+", " ", (title or "").strip())
    q = q.replace("#", " ")                        # "#B25-KG" -> "B25-KG"
    q = re.sub(r"(?:^|[\s(])/\s?\d{1,5}\b", " ", q)   # print run
    q = re.sub(r"\b\d{1,5}\s*/\s*\d{1,5}\b", " ", q)  # "22/350"
    q = _EBAY_DROP.sub(" ", q)
    q = re.sub(r"[()\[\]!]", " ", q)
    q = re.sub(r"\s{2,}", " ", q).strip()
    # Trailing team nickname — one or two words, e.g. "Red Sox", "49ers".
    teams = {t.lower() for t in _teams()}
    if teams:
        for _ in range(2):
            words = q.split()
            if len(words) >= 2 and words[-1].lower().strip(".,") in teams:
                q = " ".join(words[:-1])
            elif len(words) >= 3 and " ".join(words[-2:]).lower() in teams:
                q = " ".join(words[:-2])
            else:
                break
    return q.strip()


def ebay_sold_url(title: str) -> str:
    import urllib.parse as _up
    return ("https://www.ebay.com/sch/i.html?_nkw="
            + _up.quote_plus(ebay_query(title)[:120])
            + "&_sacat=261328&LH_Sold=1&LH_Complete=1&_sop=13")
