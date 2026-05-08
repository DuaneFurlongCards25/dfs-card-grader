import streamlit as st
import pandas as pd
import json
import urllib.request
import urllib.parse
import ssl
import random
import string
from datetime import date
from pathlib import Path
import io

# ─── Constants ────────────────────────────────────────────────────────────────
APP_VERSION = "1.2.3"

# Members-only tiers require PSA Collectors Club membership
PSA_FEES_ALL = {
    "Value Bulk (~75 days)":                {"fee": 32.99},
    "Value Plus (~45 days)":                {"fee": 49.99},
    "Value Max (~35 days)":                 {"fee": 64.99},
    "Regular (~25 days)":                   {"fee": 79.99},
    "Express (~15 days)":                   {"fee": 149.00},
    "Super Express (~7 days)":              {"fee": 299.00},
    "Walk-Through (~7 days, $10k insured)": {"fee": 599.00},
}
PSA_FEES = {k: v["fee"] for k, v in PSA_FEES_ALL.items()}
EBAY_FEE = 0.1325

# ─── Secrets ──────────────────────────────────────────────────────────────────
def get_secret(section, key, default=""):
    try:
        return st.secrets[section][key]
    except Exception:
        return default

SUPABASE_URL = get_secret("supabase", "url")
SUPABASE_KEY = get_secret("supabase", "key")
DEFAULT_EBAY_KEY = get_secret("ebay", "app_id")
CARDHEDGER_KEY = get_secret("cardhedger", "api_key")
CARDHEDGER_BASE = "https://api.cardhedger.com"

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DFS Card Grader",
    page_icon="💎",
    layout="wide",
    menu_items={"About": "DFS Card Grader — © 2025 DFS Cards LLC"},
)

# ─── Mobile CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Hide Streamlit toolbar (GitHub, edit, share icons) ── */
[data-testid="stToolbar"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; }

/* ── Page padding ── */
.block-container { padding-top: 2.5rem !important; }

@media (max-width: 768px) {
    /* Tighten page padding */
    .block-container {
        padding: 0.75rem 0.75rem 2rem !important;
    }

    /* Stack every column row vertically */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0.25rem !important;
    }
    [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }

    /* Bigger tap targets for buttons */
    .stButton > button {
        min-height: 48px !important;
        font-size: 1rem !important;
        width: 100% !important;
    }

    /* Full-width inputs */
    .stTextInput > div, .stNumberInput > div, .stSelectbox > div {
        width: 100% !important;
    }
    .stTextInput input, .stNumberInput input {
        font-size: 1rem !important;
        min-height: 44px !important;
    }

    /* Shrink tab labels so all 3 fit on one row */
    .stTabs [data-baseweb="tab"] {
        font-size: 0.75rem !important;
        padding: 6px 8px !important;
    }

    /* Metrics: show 2-up on mobile instead of cramped 4-up */
    [data-testid="metric-container"] {
        min-width: 45% !important;
    }

    /* Download button full width */
    .stDownloadButton > button {
        width: 100% !important;
        min-height: 48px !important;
    }

    /* Disclaimer card mobile padding */
    div[data-testid="stMarkdownContainer"] > div[style*="max-width:680px"] {
        margin: 20px auto !important;
        padding: 24px 16px !important;
    }

    /* Dataframes: allow horizontal scroll instead of squishing */
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
    }

    /* Hide sidebar toggle label on very small screens */
    .st-emotion-cache-eczf16 { font-size: 0 !important; }
}
</style>
""", unsafe_allow_html=True)

# ─── Admin panel ──────────────────────────────────────────────────────────────
ADMIN_PASSWORD = get_secret("admin", "password")

def gen_code():
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=4)) + "-" + "".join(random.choices(chars, k=4))
    return f"DFS-{suffix}"

def admin_get_codes():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/access_codes?select=id,code,name,active,usage_count,last_used,created_at&order=id.asc",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return []

def admin_insert_code(code, name):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    data = json.dumps({"code": code, "name": name}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/access_codes",
        data=data,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10):
            return True
    except Exception:
        return False

def admin_toggle_code(code_id, active):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    data = json.dumps({"active": active}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/access_codes?id=eq.{code_id}",
        data=data,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10):
            return True
    except Exception:
        return False

if st.query_params.get("admin") == "true":
    if not st.session_state.get("admin_authed"):
        st.markdown(
            """
            <div style="max-width:380px; margin:80px auto; padding:36px 28px;
                        background:#1e2130; border-radius:12px;
                        border:1px solid #2e3250; text-align:center;">
                <div style="font-size:2rem; margin-bottom:8px;">🔐</div>
                <h2 style="margin-bottom:16px;">Admin Access</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )
        a1, a2, a3 = st.columns([1, 2, 1])
        with a2:
            pw = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Admin password")
            if st.button("Unlock", use_container_width=True, type="primary"):
                if pw == ADMIN_PASSWORD:
                    st.session_state.admin_authed = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
        st.stop()

    # ── Admin dashboard ──
    st.markdown("## 🔐 DFS Card Grader — Admin")
    st.caption(f"v{APP_VERSION} · Access code management")
    st.markdown("---")

    codes = admin_get_codes()

    st.markdown(f"### 👥 Access Codes ({len(codes)} total)")

    for row in codes:
        c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
        c1.markdown(f"**{row['name']}**")
        c2.code(row["code"])
        c3.markdown("🟢 Active" if row["active"] else "🔴 Inactive")
        c4.markdown(f"Uses: **{row['usage_count']}**")
        last = (row.get("last_used") or "Never")[:10]
        c5.markdown(f"Last: {last}")

        if row["active"]:
            if st.button(f"Revoke", key=f"rev_{row['id']}"):
                admin_toggle_code(row["id"], False)
                st.success(f"Revoked {row['name']}")
                st.rerun()
        else:
            if st.button(f"Reinstate", key=f"rei_{row['id']}"):
                admin_toggle_code(row["id"], True)
                st.success(f"Reinstated {row['name']}")
                st.rerun()
        st.markdown("---")

    st.markdown("### ➕ Create New Access Code")
    n1, n2, n3 = st.columns([2, 2, 1])
    new_name = n1.text_input("Name", placeholder="e.g. John Smith")
    new_code = n2.text_input("Code (auto-generated, editable)", value=gen_code())
    if n3.button("Create", type="primary", use_container_width=True):
        if new_name and new_code:
            if admin_insert_code(new_code.strip().upper(), new_name.strip()):
                st.success(f"✅ Created code for **{new_name}**: `{new_code.upper()}`")
                st.rerun()
            else:
                st.error("Failed — code may already exist.")
        else:
            st.warning("Enter a name and code.")

    st.stop()

# ─── Access code gate ─────────────────────────────────────────────────────────
def validate_code(code: str):
    """Returns (name, valid) by checking Supabase access_codes table."""
    if not SUPABASE_URL:
        return None, False
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = (f"{SUPABASE_URL}/rest/v1/access_codes"
           f"?code=eq.{urllib.parse.quote(code.strip().upper())}&active=eq.true&select=id,name,usage_count")
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            rows = json.loads(r.read().decode())
        if rows:
            return rows[0]["name"], rows[0]["id"]
        return None, False
    except Exception:
        return None, False

def record_code_use(code_id: int):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    import datetime
    data = json.dumps({
        "usage_count": f"usage_count + 1",
        "last_used": datetime.datetime.utcnow().isoformat() + "Z",
    }).encode()
    # Use RPC-style raw SQL via PostgREST
    rpc_data = json.dumps({"p_id": code_id}).encode()
    # Simpler: just PATCH with a fresh read-modify-write
    url = f"{SUPABASE_URL}/rest/v1/access_codes?id=eq.{code_id}"
    # Fetch current count first
    req = urllib.request.Request(url + "&select=usage_count", headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            current = json.loads(r.read().decode())[0]["usage_count"]
        import datetime as dt
        patch = json.dumps({
            "usage_count": current + 1,
            "last_used": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }).encode()
        req2 = urllib.request.Request(url, data=patch, headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }, method="PATCH")
        with urllib.request.urlopen(req2, context=ctx, timeout=10):
            pass
    except Exception:
        pass

if not st.session_state.get("access_granted"):
    st.markdown(
        """
        <div style="max-width:420px; margin:60px auto; padding:36px 28px;
                    background:#1e2130; border-radius:12px;
                    border:1px solid #2e3250; text-align:center;">
            <div style="font-size:2.2rem; margin-bottom:8px;">💎</div>
            <h2 style="margin-bottom:4px;">DFS Card Grader</h2>
            <p style="color:#aaa; font-size:0.85rem; margin-bottom:24px;">
                Enter your access code to continue.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    gc1, gc2, gc3 = st.columns([1, 2, 1])
    with gc2:
        entered_code = st.text_input("Access Code", placeholder="DFS-XXXX-XXXX", label_visibility="collapsed")
        if st.button("Enter", use_container_width=True, type="primary"):
            clean_code = entered_code.strip().upper()
            # Owner bypass — never touches Supabase
            if clean_code == "DFS-MASTER":
                st.session_state.access_granted = True
                st.session_state.access_name = "Duane"
                st.session_state.access_code_id = 1
                st.session_state.agreed = True
                st.rerun()
            else:
                name, code_id = validate_code(entered_code)
                if name and code_id:
                    st.session_state.access_granted = True
                    st.session_state.access_name = name
                    st.session_state.access_code_id = code_id
                    record_code_use(code_id)
                    st.rerun()
                else:
                    st.error("Invalid or inactive access code.")
    st.stop()

# ─── Disclaimer gate ──────────────────────────────────────────────────────────
if not st.session_state.get("agreed"):
    st.markdown(
        """
        <div style="max-width:680px; margin:40px auto; padding:32px 24px;
                    background:#1e2130; border-radius:12px;
                    border:1px solid #2e3250; text-align:center;">
            <div style="font-size:2.5rem; margin-bottom:8px;">💎</div>
            <h2 style="margin-bottom:4px;">DFS Card Grader</h2>
            <p style="color:#aaa; font-size:0.85rem; margin-bottom:24px;">
                Please read and accept the disclaimer before continuing.
            </p>
            <div style="text-align:left; background:#0f1117; border-radius:8px;
                        padding:20px; margin-bottom:24px;
                        font-size:0.88rem; color:#ccc; line-height:1.7;">
                <strong style="color:#fafafa;">Disclaimer</strong><br><br>
                DFS Card Grader is a research and decision-support tool only.
                All pricing data (GemRate, eBay) is pulled from third-party sources
                and may be incomplete, delayed, or inaccurate. Gem rates and market
                values fluctuate — always verify data independently before submitting
                cards for grading.<br><br>
                All grading decisions and associated costs are <strong style="color:#fafafa;">
                solely your responsibility</strong>. DFS Cards LLC assumes no liability
                for financial outcomes resulting from use of this tool.<br><br>
                <span style="font-size:0.8rem; color:#888;">
                DFS Cards LLC · 8601 E Palo Verde Dr · Scottsdale, AZ 85250<br>
                ©️ 2025 DFS Cards LLC. All rights reserved.
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_l, col_btn, col_r = st.columns([2, 2, 2])
    with col_btn:
        if st.button("✅ I Understand & Agree", use_container_width=True, type="primary"):
            st.session_state.agreed = True
            st.rerun()
    st.stop()

# ─── SSL ──────────────────────────────────────────────────────────────────────
def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

# ─── Supabase tracker ─────────────────────────────────────────────────────────
TRACKER_COLS = [
    "id", "date_added", "card_description", "year", "set_name", "parallel",
    "raw_buy_price", "psa_tier", "psa_fee", "psa10_avg_price", "target_price",
    "gem_rate", "go_no_go", "est_net", "est_roi",
    "date_submitted", "status", "grade_returned",
    "actual_sell_price", "actual_net", "actual_roi", "notes",
]

def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def sb_get():
    if not SUPABASE_URL:
        return []
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/grading_tracker?order=id.asc",
        headers=sb_headers(),
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return []

def sb_insert(row: dict):
    if not SUPABASE_URL:
        return
    data = json.dumps(row).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/grading_tracker",
        data=data,
        headers=sb_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        pass

def sb_update(row_id: int, updates: dict):
    if not SUPABASE_URL:
        return
    data = json.dumps(updates).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/grading_tracker?id=eq.{row_id}",
        data=data,
        headers={**sb_headers(), "Prefer": "return=minimal"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10):
            pass
    except Exception:
        pass

def sb_delete(row_id: int):
    if not SUPABASE_URL:
        return
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/grading_tracker?id=eq.{row_id}",
        headers=sb_headers(),
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10):
            pass
    except Exception:
        pass

# ─── GemRate API ──────────────────────────────────────────────────────────────
def _gemrate_single(query: str):
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        "https://www.gemrate.com/universal-search-query",
        data=data,
        headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception:
        return []

def _build_queries(query: str):
    """Expand user query into multiple GemRate-friendly variants."""
    q = query.strip()
    queries = [q]
    ql = q.lower()

    # auto / autograph expansion
    if "auto" in ql and "autograph" not in ql:
        queries.append(q.lower().replace("auto", "autograph").strip())
        queries.append(q + " rookie autograph")

    # rc → rookie
    if " rc" in ql or ql.endswith(" rc"):
        queries.append(q.lower().replace(" rc", " rookie").strip())

    # rookie without auto → add autograph variant
    if "rookie" in ql and "auto" not in ql and "autograph" not in ql:
        queries.append(q + " autograph")

    # prizm / optic / chrome shortcuts
    for shorthand, full in [("prizm", "Prizm"), ("optic", "Optic"), ("chrome", "Chrome")]:
        if shorthand in ql and full not in q:
            queries.append(q.replace(shorthand, full))

    return list(dict.fromkeys(queries))  # dedupe while preserving order

@st.cache_data(ttl=3600, show_spinner=False)
def search_gemrate(query: str):
    queries = _build_queries(query)
    seen_ids = set()
    combined = []
    for q in queries:
        for r in _gemrate_single(q):
            gid = r.get("gemrate_id") or r.get("id") or str(r)
            if gid not in seen_ids:
                seen_ids.add(gid)
                combined.append(r)
    # Sort: prioritise results where set_name or parallel contains user keywords
    ql = query.lower()
    keywords = [w for w in ql.split() if len(w) > 2]
    def relevance(r):
        text = f"{r.get('set_name','')} {r.get('parallel','')} {r.get('name','')}".lower()
        return sum(1 for kw in keywords if kw in text)
    combined.sort(key=relevance, reverse=True)
    return combined

# ─── eBay scraper fallback (no API key required) ──────────────────────────────
import re as _re

@st.cache_data(ttl=1800, show_spinner=False)
def _scrape_ebay_sold(query: str, max_results: int = 15):
    q = urllib.parse.quote_plus(query)
    url = (f"https://www.ebay.com/sch/i.html?_nkw={q}"
           f"&LH_Sold=1&LH_Complete=1&_sop=13&_ipg=25")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    # Each listing lives in a <li class="s-item ..."> block
    items = _re.split(r'class="s-item["\s]', html)
    results = []
    for chunk in items[1:]:
        # Title
        tm = _re.search(r's-item__title[^>]*>([^<]{5,})<', chunk)
        title = tm.group(1).strip() if tm else ""
        if not title or title.lower() in ("shop on ebay", "results matching fewer words"):
            continue
        # Price — handle ranges like "$12.00 to $15.00" by taking the first
        pm = _re.search(r'\$\s*([\d,]+\.?\d*)', chunk)
        if not pm:
            continue
        try:
            price = float(pm.group(1).replace(",", ""))
        except ValueError:
            continue
        if price <= 0:
            continue
        # Image
        im = _re.search(r's-item__image-img[^>]+src="([^"]+)"', chunk)
        image = im.group(1) if im else ""
        # Link
        lm = _re.search(r'href="(https://www\.ebay\.com/itm/[^"]+)"', chunk)
        item_url = lm.group(1).split("?")[0] if lm else ""
        results.append({"title": title, "price": price, "date": "", "image": image, "url": item_url})
        if len(results) >= max_results:
            break
    return results

# ─── eBay Finding API ─────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ebay_sold(query: str, app_id: str, max_results: int = 15):
    if not app_id:
        return _scrape_ebay_sold(query, max_results)
    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "keywords": query,
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "sortOrder": "EndTimeSoonest",
        "paginationInput.entriesPerPage": str(max_results),
    }
    url = "https://svcs.ebay.com/services/search/FindingService/v1?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=12) as r:
            data = json.loads(r.read().decode())
        items = (data.get("findCompletedItemsResponse", [{}])[0]
                     .get("searchResult", [{}])[0]
                     .get("item", []))
        results = []
        for item in items:
            price_val = (item.get("sellingStatus", [{}])[0]
                             .get("currentPrice", [{}])[0]
                             .get("__value__", ""))
            end_time = (item.get("listingInfo", [{}])[0]
                            .get("endTime", [None])[0] or "")
            title = item.get("title", [""])[0]
            try:
                price = float(price_val)
            except Exception:
                continue
            image = item.get("galleryURL", [""])[0]
            item_url = item.get("viewItemURL", [""])[0]
            results.append({"title": title, "price": price, "date": end_time[:10], "image": image, "url": item_url})
        return results
    except Exception:
        return []

def ebay_avg(sold_items):
    if not sold_items:
        return None
    prices = sorted(x["price"] for x in sold_items)
    if len(prices) >= 6:
        cut = max(1, len(prices) // 10)
        prices = prices[cut:-cut]
    return round(sum(prices) / len(prices), 2)

# ─── CardHedger API ───────────────────────────────────────────────────────────
def _ch_post(endpoint: str, payload: dict):
    if not CARDHEDGER_KEY:
        return None
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{CARDHEDGER_BASE}{endpoint}", data=data,
        headers={"X-API-Key": CARDHEDGER_KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

@st.cache_data(ttl=1800, show_spinner=False)
def ch_search(query: str):
    result = _ch_post("/v1/cards/card-search", {"search": query, "page": 1, "page_size": 5})
    if not result:
        return []
    for key in ("cards", "data", "results", "items"):
        if key in result and isinstance(result[key], list):
            return result[key]
    return result if isinstance(result, list) else []

@st.cache_data(ttl=1800, show_spinner=False)
def ch_comps(card_id, grade: str):
    return _ch_post("/v1/cards/comps", {
        "card_id": card_id, "grade": grade,
        "count": 20, "include_raw_prices": True,
    }) or {}

@st.cache_data(ttl=3600, show_spinner=False)
def ch_price_history(card_id, grade: str, days: int = 90):
    return _ch_post("/v1/cards/prices-by-card", {
        "card_id": card_id, "grade": grade, "days": days,
    }) or {}

def _extract_price(p):
    for k in ("price", "sale_price", "sold_price", "value", "amount"):
        try:
            v = float(p[k])
            if v > 0:
                return v
        except Exception:
            pass
    return None

def calculate_trend(history_data):
    """Return (direction, pct_change) from CardHedger price history."""
    prices = []
    if isinstance(history_data, list):
        prices = history_data
    elif isinstance(history_data, dict):
        for key in ("prices", "data", "sales", "history", "results"):
            if key in history_data and isinstance(history_data[key], list):
                prices = history_data[key]
                break
    vals = [_extract_price(p) for p in prices]
    vals = [v for v in vals if v]
    if len(vals) < 4:
        return None, 0.0
    mid = len(vals) // 2
    older_avg = sum(vals[:mid]) / mid
    recent_avg = sum(vals[mid:]) / (len(vals) - mid)
    if older_avg == 0:
        return None, 0.0
    pct = ((recent_avg - older_avg) / older_avg) * 100
    direction = "up" if pct > 5 else "down" if pct < -5 else "flat"
    return direction, pct

def trend_badge(direction, pct):
    if direction == "up":
        return f"📈 Trending Up +{pct:.0f}%"
    elif direction == "down":
        return f"📉 Trending Down {pct:.0f}%"
    return f"➡️ Flat ({pct:+.0f}%)"

# ─── URL builders ─────────────────────────────────────────────────────────────
def gemrate_url(gid):
    return f"https://www.gemrate.com/card/{gid}"

def ebay_raw_url(desc):
    q = urllib.parse.quote_plus(desc + " raw")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1&LH_BIN=1&_sop=13"

def ebay_graded_sold_url(desc):
    q = urllib.parse.quote_plus(desc + " PSA 10")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1&LH_BIN=1&_sop=13"

def ebay_graded_buy_url(desc):
    q = urllib.parse.quote_plus(desc + " PSA 10")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_BIN=1&_sop=15"

# ─── ROI logic ────────────────────────────────────────────────────────────────
def target_price(raw_cost, psa_tier, roi=4.0):
    fee = PSA_FEES.get(psa_tier, 50)
    return (raw_cost * roi + fee) / (1 - EBAY_FEE)

def calc_net_roi(raw_cost, psa_tier, graded_price):
    fee = PSA_FEES.get(psa_tier, 50)
    net = graded_price * (1 - EBAY_FEE) - fee - raw_cost
    roi = (net / raw_cost * 100) if raw_cost > 0 else 0
    return round(net, 2), round(roi, 1)

def verdict(raw_cost, psa_tier, gem_rate, graded_price, min_gem, roi_target):
    if gem_rate is None or gem_rate < min_gem:
        return "❌ NO-GO", "red", f"Gem rate {gem_rate or 0:.1f}% below {min_gem:.0f}% floor"
    tgt = target_price(raw_cost, psa_tier, roi_target)
    net, roi = calc_net_roi(raw_cost, psa_tier, graded_price)
    if graded_price >= tgt:
        return "✅ GO", "green", f"Gem 10 avg ${graded_price:,.0f} clears ${tgt:,.0f} target | Net ~${net:,.0f} | ROI ~{roi:.0f}%"
    return "❌ NO-GO", "red", f"Gem 10 avg ${graded_price:,.0f} needs ${tgt:,.0f} for {roi_target:.0f}× | ROI only ~{roi:.0f}%"

def fmt_gem(g):
    if g is None:
        return "—"
    return "<0.1%" if g < 0.05 else f"{g:.1f}%"

def gem_signal(g):
    if g is None or g < 40:
        return "🔴"
    if g < 60:
        return "🟡"
    return "🟢"

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💎 DFS Card Grader")
    st.caption(f"Gem rate research + grading ROI calculator · v{APP_VERSION}")
    access_name = st.session_state.get("access_name", "")
    if access_name:
        st.markdown(f"👤 **{access_name}**")
    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    roi_target = st.number_input("ROI target (×)", min_value=1.0, max_value=20.0, value=4.0, step=0.5)
    min_gem = st.number_input("Min gem rate (%)", min_value=0.0, max_value=100.0, value=40.0, step=5.0)
    default_tier = st.selectbox("Default grading tier", list(PSA_FEES.keys()), index=0)

    st.markdown("---")
    st.markdown("**Grading fees**")
    for tier, info in PSA_FEES_ALL.items():
        st.caption(f"${info['fee']:.2f} — {tier.split('(')[0].strip()}")
    st.caption(f"eBay sell fee: {EBAY_FEE*100:.2f}%")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🔍 Card Research", "📦 Inventory Check", "📬 Submission Tracker", "📥 Downloads"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Card Research
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## 🔍 Card Research")
    st.markdown("Search any card — owned or not. Get gem rate, graded value comps, and eBay links.")
    st.caption("Tip: include the full set name for best results — e.g. *Steph Curry Topps Chrome Paradox* not just *Steph Curry Paradox*")

    col_q, col_btn = st.columns([5, 1])
    with col_q:
        query = st.text_input("Search", placeholder="e.g.  Curry Topps Chrome Paradox  |  Luka Prizm RC auto  |  Wemby Optic", label_visibility="collapsed")
    with col_btn:
        do_search = st.button("Search", use_container_width=True, type="primary")

    if query and (do_search or st.session_state.get("last_q") != query):
        st.session_state.last_q = query
        with st.spinner("Searching GemRate..."):
            st.session_state.gr_results = search_gemrate(query)

    results = st.session_state.get("gr_results", [])

    if results:
        st.markdown(f"**{len(results)} result(s) from GemRate**")
        rows = [{
            "Signal": gem_signal(r.get("gem_rate")),
            "Year": r.get("year", ""),
            "Set": r.get("set_name", ""),
            "Player": r.get("name", ""),
            "Parallel": r.get("parallel") or "Base",
            "#": r.get("card_number", ""),
            "Grader": r.get("population_type", ""),
            "Total Pop": f"{r.get('total_population', 0):,}",
            "Gem Copies": f"{r.get('gems', 0):,}",
            "Gem Rate": fmt_gem(r.get("gem_rate")),
        } for r in results]

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=280)

        gr_search_url = f"https://www.gemrate.com/search?q={urllib.parse.quote_plus(query)}"
        st.caption(f"Don't see the card? [Search directly on GemRate ↗]({gr_search_url}) — their database may use a different set name.")

        opts = [
            f"{r.get('year','')} {r.get('set_name','')} {r.get('name','')} "
            f"{r.get('parallel') or 'Base'} #{r.get('card_number','')}"
            for r in results
        ]
        selected = st.selectbox("Select card to analyze", opts)
        sel = results[opts.index(selected)]
        gem = sel.get("gem_rate")
        desc = f"{sel.get('year','')} {sel.get('set_name','')} {sel.get('name','')} {sel.get('parallel') or ''}".strip()

        st.markdown("---")
        st.text_input("📋 Card name (tap → select all → copy)", value=selected, key="card_name_copy")

        m1, m2, m3 = st.columns(3)
        m1.metric("Gem Rate", fmt_gem(gem))
        m2.metric("Total Pop", f"{sel.get('total_population', 0):,}")
        m3.metric("Gem Copies", f"{sel.get('gems', 0):,}")
        st.markdown(f"[📊 Full pop report on GemRate]({gemrate_url(sel.get('gemrate_id',''))})")

        st.markdown("#### ROI Analysis")

        # ── CardHedger: live sold comps + trend ───────────────────────────────
        ch_raw_avg = None
        ch_psa10_avg = None
        ch_trend_dir = None
        ch_trend_pct = 0.0
        ch_raw_sales = []
        ch_psa10_sales = []
        ch_card_name = ""

        if CARDHEDGER_KEY:
            with st.spinner("Fetching live sold comps & trend data..."):
                ch_matches = ch_search(desc)
                if ch_matches:
                    ch_card = ch_matches[0]
                    ch_id = ch_card.get("card_id") or ch_card.get("id")
                    ch_card_name = ch_card.get("name") or ch_card.get("title") or ""
                    if ch_id:
                        raw_data  = ch_comps(ch_id, "Raw")
                        psa_data  = ch_comps(ch_id, "PSA 10")
                        ch_raw_avg   = raw_data.get("comp_price") or raw_data.get("average") or raw_data.get("mean")
                        ch_psa10_avg = psa_data.get("comp_price") or psa_data.get("average") or psa_data.get("mean")
                        for k in ("raw_prices", "sales", "comps", "data"):
                            if k in raw_data and isinstance(raw_data[k], list):
                                ch_raw_sales = raw_data[k]; break
                        for k in ("raw_prices", "sales", "comps", "data"):
                            if k in psa_data and isinstance(psa_data[k], list):
                                ch_psa10_sales = psa_data[k]; break
                        history = ch_price_history(ch_id, "PSA 10", days=90)
                        ch_trend_dir, ch_trend_pct = calculate_trend(history)

            if ch_raw_avg or ch_psa10_avg or ch_raw_sales or ch_psa10_sales:
                fc1, fc2 = st.columns(2)
                with fc1:
                    st.markdown("**📦 Raw — recent sold comps**")
                    if ch_raw_sales:
                        rows_r = []
                        for s in ch_raw_sales[:15]:
                            p = _extract_price(s)
                            if p:
                                rows_r.append({"Price": f"${p:,.2f}", "Date": s.get("date") or s.get("sold_date","")})
                        if rows_r:
                            st.dataframe(pd.DataFrame(rows_r), use_container_width=True, hide_index=True, height=200)
                    if ch_raw_avg:
                        st.markdown(f"**Comp avg: ${ch_raw_avg:,.2f}**")
                    elif not ch_raw_sales:
                        st.info("No raw comps found")
                with fc2:
                    st.markdown("**💎 PSA 10 — recent sold comps**")
                    if ch_psa10_sales:
                        rows_g = []
                        for s in ch_psa10_sales[:15]:
                            p = _extract_price(s)
                            if p:
                                rows_g.append({"Price": f"${p:,.2f}", "Date": s.get("date") or s.get("sold_date","")})
                        if rows_g:
                            st.dataframe(pd.DataFrame(rows_g), use_container_width=True, hide_index=True, height=200)
                    if ch_psa10_avg:
                        st.markdown(f"**Comp avg: ${ch_psa10_avg:,.2f}**")
                    elif not ch_psa10_sales:
                        st.info("No PSA 10 comps found")
            if ch_raw_sales or ch_psa10_sales:
                st.caption("⚠️ eBay Best Offer accepted listings show the asking price, not the actual amount paid — real comps may be lower. Use fixed-price (BIN) sales for the most accurate picture.")
                # Temporary debug — remove after confirming date field name
                sample = (ch_raw_sales or ch_psa10_sales)[0]
                with st.expander("🔧 Debug: raw sale object keys"):
                    st.json(sample)
            elif CARDHEDGER_KEY:
                st.info("No CardHedger match found for this card — enter prices manually below.")
        else:
            st.info("📊 Live sold comps will appear here once the CardHedger API is connected.")

        raw_auto    = ch_raw_avg
        graded_auto = ch_psa10_avg

        ra1, ra2, ra3 = st.columns(3)
        with ra1:
            raw_cost = st.number_input(
                "Raw buy price ($)", min_value=0.0,
                value=float(raw_auto) if raw_auto else 50.0,
                step=5.0, key="t1_raw",
            )
        with ra2:
            tier = st.selectbox("Grading tier", list(PSA_FEES.keys()),
                                index=list(PSA_FEES.keys()).index(default_tier), key="t1_tier")
        with ra3:
            graded_price = st.number_input(
                "Gem 10 avg price ($)", min_value=0.0,
                value=float(graded_auto) if graded_auto else 0.0,
                step=10.0, key="t1_graded",
            )

        if raw_cost > 0:
            fee = PSA_FEES[tier]
            tgt = target_price(raw_cost, tier, roi_target)
            bd1, bd2, bd3, bd4 = st.columns(4)
            bd1.metric("Raw card", f"${raw_cost:,.2f}")
            bd2.metric(f"Grading fee", f"${fee}")
            bd3.metric(f"Target Gem 10 price ({roi_target:.0f}×)", f"${tgt:,.0f}")
            bd4.metric("eBay fees", f"${graded_price * EBAY_FEE:,.2f}" if graded_price else "—")

            if graded_price > 0:
                v, color, msg = verdict(raw_cost, tier, gem, graded_price, min_gem, roi_target)
                net, roi = calc_net_roi(raw_cost, tier, graded_price)
                if color == "green":
                    st.success(f"{v} — {msg}")
                else:
                    st.error(f"{v} — {msg}")
                r1, r2, r3 = st.columns(3)
                r1.metric("Est. Net Profit", f"${net:,.0f}")
                r2.metric("Est. ROI", f"{roi:.0f}%")
                if ch_trend_dir:
                    badge = trend_badge(ch_trend_dir, ch_trend_pct)
                    color_map = {"up": "normal", "down": "inverse", "flat": "off"}
                    r3.metric("90-Day Trend", badge)

                # Copy summary
                summary = f"""{query}
Gem Rate: {fmt_gem(gem)} | Raw: ${raw_cost:,.2f} | Gem 10 Avg: ${graded_price:,.2f}
Target: ${tgt:,.0f} | Net: ${net:,.0f} | ROI: {roi:.0f}%
{v}"""
                with st.expander("📋 Copy Analysis"):
                    st.code(summary, language=None)
            else:
                st.info("Enter a Gem 10 avg price above to get a GO/NO-GO decision")

        st.markdown("#### eBay Sold Comps")
        st.caption("Fixed-price completed sales only (Best Offer excluded) — use these to set your raw buy price and PSA 10 sell price above.")
        l1, l2 = st.columns(2)
        l1.markdown(f"[📦 Raw Sold Comps]({ebay_raw_url(desc)})")
        l2.markdown(f"[💎 PSA 10 Sold Comps]({ebay_graded_sold_url(desc)})")

        st.markdown("---")
        if st.button("➕ Add to Submission Tracker", type="secondary"):
            if raw_cost <= 0:
                st.warning("Enter a raw buy price first")
            else:
                fee = PSA_FEES[tier]
                tgt = target_price(raw_cost, tier, roi_target)
                net, roi = calc_net_roi(raw_cost, tier, graded_price) if graded_price > 0 else (None, None)
                v, _, _ = verdict(raw_cost, tier, gem, graded_price, min_gem, roi_target) if graded_price > 0 else ("Pending", "", "")
                sb_insert({
                    "date_added": date.today().isoformat(),
                    "card_description": selected,
                    "year": sel.get("year", ""),
                    "set_name": sel.get("set_name", ""),
                    "parallel": sel.get("parallel") or "Base",
                    "raw_buy_price": raw_cost,
                    "psa_tier": tier,
                    "psa_fee": fee,
                    "psa10_avg_price": graded_price or None,
                    "target_price": round(tgt, 2),
                    "gem_rate": round(gem, 2) if gem else None,
                    "go_no_go": v,
                    "est_net": net,
                    "est_roi": f"{roi:.0f}%" if roi is not None else None,
                    "status": "Queued",
                })
                st.success("Added to Submission Tracker ✓")

    elif query:
        gr_search_url = f"https://www.gemrate.com/search?q={urllib.parse.quote_plus(query)}"
        st.warning(f"No results found — GemRate may not have this set indexed yet. Try a different search term or [search directly on GemRate ↗]({gr_search_url})")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Inventory Check
# ══════════════════════════════════════════════════════════════════════════════

TEMPLATE_COLS = [
    "Card Description", "Player", "Year", "Set", "Parallel",
    "Card Number", "Category", "Cost Basis ($)", "Listed Price ($)",
    "Source", "Notes"
]

TEMPLATE_EXAMPLE = [
    ["2021 Topps Chrome Julio Rodriguez Auto RC", "Julio Rodriguez", "2021", "Topps Chrome", "Base", "RA-JR", "Baseball", 68, 155, "Whatnot", ""],
    ["2024 Panini Prizm Luka Doncic Silver", "Luka Doncic", "2024", "Panini Prizm", "Silver", "10", "Basketball", 120, 280, "eBay Lot", ""],
    ["2023 Bowman Chrome Patrick Bailey Auto", "Patrick Bailey", "2023", "Bowman Chrome", "Base", "CDA-PB", "Baseball", 25, 55, "Card Show", ""],
]

def make_template_csv():
    import io
    buf = io.StringIO()
    df = pd.DataFrame(TEMPLATE_EXAMPLE, columns=TEMPLATE_COLS)
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()

def load_inventory(uploaded_file):
    """Load inventory from either the DFS workbook or the standard template CSV/XLSX."""
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
            df.columns = [c.strip() for c in df.columns]
            return df, "template"
        else:
            xl = pd.ExcelFile(uploaded_file)
            # Detect file type by sheet names
            if "Inventory & Aging" in xl.sheet_names:
                # DFS Operations Workbook
                df = pd.read_excel(uploaded_file, sheet_name="Inventory & Aging", header=2)
                df.columns = [str(c).strip() for c in df.columns]
                if "Card Description" not in df.columns:
                    df.columns = ["Acquired", "Listed Date", "Source", "Card Description",
                                  "Category", "Cost Basis ($)", "Listed Price ($)",
                                  "Status", "Days Listed", "Aging Flag", "Next Action"]
                df = df[df["Card Description"].notna()]
                df = df[~df["Card Description"].astype(str).str.startswith("💡")]
                df = df[~df["Acquired"].astype(str).str.startswith("SUMMARY", na=True)]
                return df.reset_index(drop=True), "workbook"
            else:
                # Standard template XLSX (first sheet)
                df = pd.read_excel(uploaded_file, sheet_name=0)
                df.columns = [str(c).strip() for c in df.columns]
                return df.reset_index(drop=True), "template"
    except Exception as e:
        return None, str(e)

with tab2:
    st.markdown("## 📦 Inventory Check")

    # Two-column header: description + template download
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown("Upload your inventory to find grading candidates. Use the template below or upload your DFS Operations Workbook directly.")
    with h2:
        st.download_button(
            label="⬇️ Download Template",
            data=make_template_csv(),
            file_name="dfs_card_inventory_template.csv",
            mime="text/csv",
            help="Fill this out and upload it below",
            use_container_width=True,
        )

    st.markdown("""
**How it works:**
1. Download the template → fill in your cards → save
2. Upload it below → select a card → search GemRate → get GO/NO-GO
3. Add grading candidates directly to the Submission Tracker
""")

    uploaded = st.file_uploader(
        "Upload inventory (CSV template or DFS Workbook .xlsx)",
        type=["csv", "xlsx"],
        label_visibility="visible",
    )

    if uploaded:
        inv, source = load_inventory(uploaded)

        if inv is None:
            st.error(f"Could not read file: {source}")
        else:
            st.success(f"Loaded **{len(inv)} cards** {'from DFS Workbook' if source == 'workbook' else 'from inventory template'}")

            show_cols = [c for c in ["Card Description", "Player", "Year", "Set", "Parallel",
                                     "Category", "Cost Basis ($)", "Listed Price ($)", "Source"] if c in inv.columns]
            st.dataframe(inv[show_cols], use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("### Analyze a card for grading")

            descs = inv["Card Description"].dropna().tolist()
            sel_card = st.selectbox("Select card from your inventory", descs)
            sel_row = inv[inv["Card Description"] == sel_card].iloc[0]

            try:
                cost_basis = float(sel_row.get("Cost Basis ($)", 0) or 0)
            except Exception:
                cost_basis = 0.0

            ic1, ic2 = st.columns(2)
            inv_raw  = ic1.number_input("Cost basis / buy price ($)", value=cost_basis, min_value=0.0, step=5.0, key="inv_raw")
            inv_tier = ic2.selectbox("Grading tier", list(PSA_FEES.keys()), key="inv_tier")

            if st.button("🔎 Search GemRate for this card", key="inv_search"):
                with st.spinner("Searching GemRate..."):
                    st.session_state.inv_results = search_gemrate(sel_card)
                    st.session_state.inv_card = sel_card

            inv_results = st.session_state.get("inv_results", [])
            if inv_results and st.session_state.get("inv_card") == sel_card:
                inv_opts = [
                    f"{r.get('year','')} {r.get('set_name','')} {r.get('name','')} {r.get('parallel') or 'Base'} #{r.get('card_number','')}"
                    for r in inv_results
                ]
                inv_match = st.selectbox("Best GemRate match", inv_opts, key="inv_match")
                inv_sel = inv_results[inv_opts.index(inv_match)]
                gem_i = inv_sel.get("gem_rate")
                desc_i = f"{inv_sel.get('year','')} {inv_sel.get('set_name','')} {inv_sel.get('name','')} {inv_sel.get('parallel') or ''}".strip()

                g1, g2, g3 = st.columns(3)
                g1.metric("Gem Rate", fmt_gem(gem_i))
                g2.metric("Total Pop", f"{inv_sel.get('total_population', 0):,}")
                g3.metric("Gem Copies", f"{inv_sel.get('gems', 0):,}")
                st.markdown(f"[📊 GemRate pop report]({gemrate_url(inv_sel.get('gemrate_id',''))})")

                inv_graded_auto = None

                inv_graded = st.number_input(
                    "Gem 10 avg price ($)", min_value=0.0,
                    value=float(inv_graded_auto) if inv_graded_auto else 0.0,
                    step=10.0, key="inv_graded",
                )
                st.markdown(f"[📈 eBay Gem 10 sold comps]({ebay_graded_sold_url(desc_i)})")

                if inv_graded > 0 and inv_raw > 0:
                    v_i, color_i, msg_i = verdict(inv_raw, inv_tier, gem_i, inv_graded, min_gem, roi_target)
                    net_i, roi_i = calc_net_roi(inv_raw, inv_tier, inv_graded)
                    if color_i == "green":
                        st.success(f"{v_i} — {msg_i}")
                    else:
                        st.error(f"{v_i} — {msg_i}")

                    if st.button("➕ Add to Submission Tracker", key="inv_add"):
                        fee_i = PSA_FEES[inv_tier]
                        tgt_i = target_price(inv_raw, inv_tier, roi_target)
                        sb_insert({
                            "date_added": date.today().isoformat(),
                            "card_description": sel_card,
                            "year": inv_sel.get("year", ""),
                            "set_name": inv_sel.get("set_name", ""),
                            "parallel": inv_sel.get("parallel") or "Base",
                            "raw_buy_price": inv_raw,
                            "psa_tier": inv_tier,
                            "psa_fee": fee_i,
                            "psa10_avg_price": inv_graded,
                            "target_price": round(tgt_i, 2),
                            "gem_rate": round(gem_i, 2) if gem_i else None,
                            "go_no_go": v_i,
                            "est_net": net_i,
                            "est_roi": f"{roi_i:.0f}%",
                            "status": "Queued",
                        })
                        st.success("Added to Tracker ✓")
    else:
        st.info("👆 Upload your inventory file above to get started, or download the template first.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Submission Tracker
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## 📬 Submission Tracker")

    if not SUPABASE_URL:
        st.warning("Supabase not configured — tracker unavailable in this environment")
    else:
        rows = sb_get()
        if not rows:
            st.info("No submissions yet. Add cards from the Card Research or Inventory Check tabs.")
        else:
            df = pd.DataFrame(rows)

            # Summary
            total  = len(df)
            queued = len(df[df["status"] == "Queued"])
            sent   = len(df[df["status"] == "Submitted"])
            rcvd   = len(df[df["status"] == "Received"])
            goes   = len(df[df["go_no_go"].str.startswith("✅", na=False)])
            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("Total", total)
            s2.metric("Queued", queued)
            s3.metric("Submitted", sent)
            s4.metric("Received", rcvd)
            s5.metric("GO Decisions", goes)

            st.markdown("---")
            display_cols = [c for c in [
                "id", "date_added", "card_description", "raw_buy_price", "psa_tier",
                "gem_rate", "go_no_go", "est_net", "est_roi",
                "status", "date_submitted", "grade_returned",
                "actual_sell_price", "actual_net", "actual_roi", "notes"
            ] if c in df.columns]

            edited = st.data_editor(
                df[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "status": st.column_config.SelectboxColumn("Status", options=["Queued", "Submitted", "Received", "Sold"]),
                    "date_added": st.column_config.DateColumn("Added"),
                    "date_submitted": st.column_config.DateColumn("Submitted"),
                    "raw_buy_price": st.column_config.NumberColumn("Raw $", format="$%.2f"),
                    "psa10_avg_price": st.column_config.NumberColumn("Gem 10 Avg $", format="$%.2f"),
                    "target_price": st.column_config.NumberColumn("Target $", format="$%.2f"),
                    "est_net": st.column_config.NumberColumn("Est Net $", format="$%.2f"),
                    "actual_sell_price": st.column_config.NumberColumn("Actual Sell $", format="$%.2f"),
                    "actual_net": st.column_config.NumberColumn("Actual Net $", format="$%.2f"),
                    "go_no_go": st.column_config.TextColumn("Decision", disabled=True),
                },
                num_rows="dynamic",
            )

            if st.button("💾 Save changes", type="primary"):
                for _, row in edited.iterrows():
                    row_id = int(row.get("id", 0))
                    if row_id:
                        updates = {k: (None if pd.isna(v) else v) for k, v in row.items() if k != "id"}
                        sb_update(row_id, updates)
                st.success("Saved ✓")
                st.rerun()

            # ROI summary for received cards
            rcvd_df = df[df["status"].isin(["Received", "Sold"])].copy()
            if len(rcvd_df) > 0:
                st.markdown("---")
                st.markdown("### 📊 Actual returns")
                try:
                    invested = pd.to_numeric(rcvd_df["raw_buy_price"], errors="coerce").sum()
                    net_total = pd.to_numeric(rcvd_df["actual_net"], errors="coerce").sum()
                    avg_roi = (net_total / invested * 100) if invested > 0 else 0
                    r1, r2, r3 = st.columns(3)
                    r1.metric("Total Invested", f"${invested:,.0f}")
                    r2.metric("Total Net", f"${net_total:,.0f}")
                    r3.metric("Avg ROI", f"{avg_roi:.0f}%")
                except Exception:
                    pass

        # Manual add
        st.markdown("---")
        st.markdown("### ➕ Add manually")
        with st.expander("Add a card"):
            a1, a2 = st.columns(2)
            m_desc = a1.text_input("Card description", key="m_desc")
            m_raw  = a2.number_input("Raw buy price ($)", min_value=0.0, step=5.0, key="m_raw")
            a3, a4 = st.columns(2)
            m_tier = a3.selectbox("Grading tier", list(PSA_FEES.keys()), key="m_tier")
            m_gem  = a4.number_input("Gem rate (%)", min_value=0.0, max_value=100.0, key="m_gem")
            a5, a6 = st.columns(2)
            m_g10  = a5.number_input("Gem 10 avg price ($)", min_value=0.0, step=5.0, key="m_g10")
            m_notes = a6.text_input("Notes", key="m_notes")

            if st.button("Add", key="m_add"):
                if m_desc and m_raw > 0:
                    fee_m = PSA_FEES[m_tier]
                    tgt_m = target_price(m_raw, m_tier, roi_target)
                    net_m, roi_m = calc_net_roi(m_raw, m_tier, m_g10) if m_g10 > 0 else (None, None)
                    v_m, _, _ = verdict(m_raw, m_tier, m_gem or None, m_g10, min_gem, roi_target) if m_g10 > 0 else ("Pending", "", "")
                    sb_insert({
                        "date_added": date.today().isoformat(),
                        "card_description": m_desc,
                        "raw_buy_price": m_raw,
                        "psa_tier": m_tier,
                        "psa_fee": fee_m,
                        "psa10_avg_price": m_g10 or None,
                        "target_price": round(tgt_m, 2),
                        "gem_rate": m_gem or None,
                        "go_no_go": v_m,
                        "est_net": net_m,
                        "est_roi": f"{roi_m:.0f}%" if roi_m is not None else None,
                        "status": "Queued",
                        "notes": m_notes,
                    })
                    st.success("Added ✓")
                    st.rerun()
                else:
                    st.warning("Need a description and buy price")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Downloads
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("## 📥 Downloads")
    st.markdown("Tools to run your grading operation — built to work alongside the app.")
    st.markdown("---")

    # ── Operations Kit ──
    kit_path = Path(__file__).parent / "DFS_Card_Grader_Kit.xlsx"
    current_user = st.session_state.get("access_name", "")
    kit_unlocked = current_user == "Robert Bass"

    if kit_path.exists():
        with open(kit_path, "rb") as f:
            kit_bytes = f.read()

        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("### 📊 DFS Card Grader — Operations Kit")
            st.markdown("""
A comprehensive Excel workbook built to run alongside this app. Includes:

- **PSA Fee Schedule** — all 7 tiers with eBay fee calculations
- **Grading ROI Calculator** — input a card, get instant GO/NO-GO with target price and net profit
- **Grading Tracker** — full 21-column submission log matching your tracker in this app
- **Grading Candidates** — shortlist cards from your inventory for PSA consideration
- **Inventory & Aging** — track every card with cost basis, days listed, and aging flags
- **Sales Log** — log every sale with fees, shipping, and net margin
- **Target Card List** — your buy list with max buy price and sell targets
- **Channel Fees Calculator** — live fee routing across all your sales channels
- **Consignment Tracker** — log DcSports, PWCC, Probstein submissions
- **Path to $40k** — monthly revenue projection model
- **+ 14 more sheets** covering capital velocity, lot evaluation, HeyStack priority scoring, and more
""")
        with c2:
            st.markdown("<div style='padding-top:48px'></div>", unsafe_allow_html=True)
            if kit_unlocked:
                st.download_button(
                    label="⬇️ Download Operations Kit",
                    data=kit_bytes,
                    file_name="DFS_Card_Grader_Operations_Kit.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary",
                )
                st.caption("Excel (.xlsx) · Works with Excel, Google Sheets, and Numbers")
            else:
                st.button("🔒 Operations Kit", use_container_width=True, disabled=True)
                st.caption("Coming soon — available as a premium add-on")

    st.markdown("---")

    # ── Inventory Template ──
    i1, i2 = st.columns([2, 1])
    with i1:
        st.markdown("### 📋 Inventory Template")
        st.markdown("""
A simple CSV template to get started tracking your inventory.
Upload it in the **Inventory Check** tab to search GemRate and get GO/NO-GO decisions on your cards.

- 11 columns: Card Description, Player, Year, Set, Parallel, Card Number, Category, Cost Basis, Listed Price, Source, Notes
- 3 example rows included to show the format
""")
    with i2:
        st.markdown("<div style='padding-top:48px'></div>", unsafe_allow_html=True)

        st.download_button(
            label="⬇️ Download Template",
            data=make_template_csv(),
            file_name="dfs_card_inventory_template.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("CSV · Opens in Excel, Google Sheets, or Numbers")

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    """
    <div style="text-align:center; color:#666; font-size:0.78rem; line-height:1.9; padding-bottom:1rem;">
        <strong style="color:#aaa;">Disclaimer</strong><br>
        DFS Card Grader is a research and decision-support tool only. All pricing data (GemRate, eBay)
        is pulled from third-party sources and may be incomplete, delayed, or inaccurate.
        Gem rates and market values fluctuate — always verify data independently before submitting cards for grading.
        All grading decisions and associated costs are solely your responsibility.
        DFS Cards LLC assumes no liability for financial outcomes resulting from use of this tool.<br><br>
        <strong style="color:#aaa;">DFS Cards LLC</strong><br>
        8601 E Palo Verde Dr · Scottsdale, AZ 85250<br><br>
        ©️ 2025 DFS Cards LLC. All rights reserved.
    </div>
    """,
    unsafe_allow_html=True,
)
