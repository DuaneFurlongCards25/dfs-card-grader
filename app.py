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
APP_VERSION = "1.1.2"

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

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DFS Card Grader",
    page_icon="💎",
    layout="wide",
    menu_items={"About": "DFS Card Grader — built for DFS Cards LLC"},
)

# ─── Mobile CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Reduce desktop padding on wide layout ── */
.block-container { padding-top: 1.5rem !important; }

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
                for financial outcomes resulting from use of this tool.
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
@st.cache_data(ttl=3600, show_spinner=False)
def search_gemrate(query: str):
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

# ─── eBay Finding API ─────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ebay_sold(query: str, app_id: str, max_results: int = 15):
    if not app_id:
        return []
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
            results.append({"title": title, "price": price, "date": end_time[:10]})
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

# ─── URL builders ─────────────────────────────────────────────────────────────
def gemrate_url(gid):
    return f"https://www.gemrate.com/card/{gid}"

def ebay_raw_url(desc):
    q = urllib.parse.quote_plus(desc + " raw")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_BIN=1&_sop=15"

def ebay_graded_sold_url(desc):
    q = urllib.parse.quote_plus(desc + " PSA 10")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1"

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
    st.markdown("### eBay API Key")
    st.caption("Get a free App ID at [developer.ebay.com](https://developer.ebay.com) to enable automatic price lookup.")
    ebay_key = st.text_input("eBay App ID", value=DEFAULT_EBAY_KEY, type="password", placeholder="YourApp-PRD-...")
    if ebay_key:
        st.success("eBay API connected ✓")
    else:
        st.warning("No key — prices entered manually")

    st.markdown("---")
    st.markdown("**Grading fees**")
    for tier, info in PSA_FEES_ALL.items():
        st.caption(f"${info['fee']:.2f} — {tier.split('(')[0].strip()}")
    st.caption(f"eBay sell fee: {EBAY_FEE*100:.2f}%")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🔍 Card Research", "📦 Inventory Check", "📬 Submission Tracker"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Card Research
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## 🔍 Card Research")
    st.markdown("Search any card — owned or not. Get gem rate, graded value comps, and eBay links.")

    col_q, col_btn = st.columns([5, 1])
    with col_q:
        query = st.text_input("Search", placeholder="e.g.  Steph Curry Paradox  |  Luka Doncic Prizm RC  |  Wemby Optic", label_visibility="collapsed")
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
        st.markdown(f"### {selected}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Gem Rate", fmt_gem(gem))
        m2.metric("Total Pop", f"{sel.get('total_population', 0):,}")
        m3.metric("Gem Copies", f"{sel.get('gems', 0):,}")
        st.markdown(f"[📊 Full pop report on GemRate]({gemrate_url(sel.get('gemrate_id',''))})")

        st.markdown("#### ROI Analysis")

        # Auto-fetch eBay prices
        raw_sold, graded_sold = [], []
        raw_auto, graded_auto = None, None
        if ebay_key:
            with st.spinner("Fetching eBay sold prices..."):
                raw_sold    = fetch_ebay_sold(desc + " raw", ebay_key)
                graded_sold = fetch_ebay_sold(desc + " PSA 10", ebay_key)
            raw_auto    = ebay_avg(raw_sold)
            graded_auto = ebay_avg(graded_sold)

            fc1, fc2 = st.columns(2)
            with fc1:
                st.markdown("**Raw — recent eBay solds**")
                if raw_sold:
                    df_r = pd.DataFrame(raw_sold)[["date", "price", "title"]]
                    df_r["price"] = df_r["price"].map("${:,.2f}".format)
                    df_r.columns = ["Date", "Price", "Title"]
                    st.dataframe(df_r, use_container_width=True, hide_index=True, height=180)
                    if raw_auto:
                        st.markdown(f"**Avg (trimmed): ${raw_auto:,.2f}**")
                else:
                    st.info("No raw solds found — try a broader search")
            with fc2:
                st.markdown("**Gem 10 — recent eBay solds**")
                if graded_sold:
                    df_g = pd.DataFrame(graded_sold)[["date", "price", "title"]]
                    df_g["price"] = df_g["price"].map("${:,.2f}".format)
                    df_g.columns = ["Date", "Price", "Title"]
                    st.dataframe(df_g, use_container_width=True, hide_index=True, height=180)
                    if graded_auto:
                        st.markdown(f"**Avg (trimmed): ${graded_auto:,.2f}**")
                else:
                    st.info("No graded 10 solds found")

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
                r1, r2 = st.columns(2)
                r1.metric("Est. Net Profit", f"${net:,.0f}")
                r2.metric("Est. ROI", f"{roi:.0f}%")
            else:
                st.info("Enter a Gem 10 avg price above to get a GO/NO-GO decision")

        st.markdown("#### eBay Links")
        l1, l2, l3 = st.columns(3)
        l1.markdown(f"[🛒 Buy Raw on eBay]({ebay_raw_url(desc)})")
        l2.markdown(f"[📈 Gem 10 Sold Comps]({ebay_graded_sold_url(desc)})")
        l3.markdown(f"[💎 Buy Gem 10 on eBay]({ebay_graded_buy_url(desc)})")

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
        st.warning("No results found — try player name + set name (e.g. 'Curry Prizm')")

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
                if ebay_key:
                    with st.spinner("Fetching eBay comps..."):
                        inv_g10 = fetch_ebay_sold(desc_i + " PSA 10", ebay_key)
                    inv_graded_auto = ebay_avg(inv_g10)
                    if inv_graded_auto:
                        st.metric("Gem 10 eBay avg", f"${inv_graded_auto:,.2f}")

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

# ─── Footer disclaimer ────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "**Disclaimer:** DFS Card Grader is a research and decision-support tool only. "
    "All pricing data (GemRate, eBay) is pulled from third-party sources and may be incomplete, "
    "delayed, or inaccurate. Gem rates and market values fluctuate — always verify data independently "
    "before submitting cards for grading. All grading decisions and associated costs are solely your "
    "responsibility. DFS Cards LLC assumes no liability for financial outcomes resulting from use of this tool."
)
