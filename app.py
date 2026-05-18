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
APP_VERSION = "1.2.5"

RELEASE_NOTES = {
    "1.2.5": {
        "emoji": "📦",
        "title": "Shipping costs + true total ROI",
        "items": [
            ("📦", "Shipping costs added — enter your true per-card cost (including insurance) in Settings. Baked into every ROI and net profit calculation."),
            ("⏳", "Time cost of capital — see the hidden fee of slow grading tiers. A $500 card at Value tier for 154 days costs you ~$27 you can't deploy elsewhere."),
            ("🔄", "Auto-fallback to CardHedger — when GemRate is offline, live PSA 10 / Raw prices load automatically from CardHedger."),
            ("💎", "Card images now show in search results."),
            ("📋", "PSA fees & turnaround times updated to May 2025 pricing (Super Express $349, all times extended)."),
        ],
    },
}

# PSA current pricing & turnaround (updated May 2025)
# days = midpoint of business-day range; calendar days ≈ days × 1.4
PSA_FEES_ALL = {
    "Value (100-120 days)":      {"fee": 32.99,  "days": 110, "max_insured":  500},
    "Value Plus (60-80 days)":   {"fee": 49.99,  "days":  70, "max_insured":  500},
    "Value Max (40-50 days)":    {"fee": 64.99,  "days":  45, "max_insured": 1000},
    "Regular (30-40 days)":      {"fee": 79.99,  "days":  35, "max_insured": 1500},
    "Express (20-30 days)":      {"fee": 149.00, "days":  25, "max_insured": 2500},
    "Super Express (7-10 days)": {"fee": 349.00, "days":   9, "max_insured": 5000},
    "Walk-Through (5-7 days)":   {"fee": 599.00, "days":   6, "max_insured": 10000},
}
PSA_FEES = {k: v["fee"]  for k, v in PSA_FEES_ALL.items()}
PSA_DAYS = {k: v["days"] for k, v in PSA_FEES_ALL.items()}
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

def admin_insert_code(code, name, trial_days=None):
    import datetime as _dt
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    payload = {"code": code, "name": name}
    if trial_days and trial_days > 0:
        exp = _dt.datetime.utcnow() + _dt.timedelta(days=trial_days)
        payload["expires_at"] = exp.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = json.dumps(payload).encode()
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

    import datetime as _dt
    now_utc = _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)

    for row in codes:
        c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 1, 1, 1, 2])
        c1.markdown(f"**{row['name']}**")
        c2.code(row["code"])
        c3.markdown("🟢 Active" if row["active"] else "🔴 Inactive")
        c4.markdown(f"Uses: **{row['usage_count']}**")
        last = (row.get("last_used") or "Never")[:10]
        c5.markdown(f"Last: {last}")
        # Expiry display
        exp_raw = row.get("expires_at")
        if exp_raw:
            try:
                exp_dt = _dt.datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
                days_left = (exp_dt - now_utc).days
                if days_left < 0:
                    c6.markdown("🔴 **Expired**")
                elif days_left == 0:
                    c6.markdown("🟡 **Expires today**")
                else:
                    c6.markdown(f"⏳ {days_left}d left ({exp_dt.strftime('%b %d')})")
            except Exception:
                c6.markdown(f"Expires: {exp_raw[:10]}")
        else:
            c6.markdown("♾️ No expiry")

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
    n1, n2, n3, n4 = st.columns([2, 2, 1, 1])
    new_name = n1.text_input("Name", placeholder="e.g. John Smith")
    _default_code = "BETA-" + gen_code()[4:] if True else gen_code()  # start with BETA- suggested
    new_code = n2.text_input("Code (auto-generated, editable)", value=gen_code())
    trial_days = n3.number_input("Trial days", min_value=0, max_value=365, value=7,
                                  help="0 = no expiry (full member). 7 = 7-day beta trial.")
    if n4.button("Create", type="primary", use_container_width=True):
        if new_name and new_code:
            days = int(trial_days) if trial_days > 0 else None
            if admin_insert_code(new_code.strip().upper(), new_name.strip(), trial_days=days):
                exp_note = f" · expires in {days} days" if days else " · no expiry"
                st.success(f"✅ Created code for **{new_name}**: `{new_code.upper()}`{exp_note}")
                st.rerun()
            else:
                st.error("Failed — code may already exist.")
        else:
            st.warning("Enter a name and code.")

    st.stop()

# ─── Access code gate ─────────────────────────────────────────────────────────
def validate_code(code: str):
    """Returns (name, code_id, error_key) — error_key is None on success, 'expired' or 'invalid' otherwise."""
    if not SUPABASE_URL:
        return None, False, "invalid"
    import datetime as _dt
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = (f"{SUPABASE_URL}/rest/v1/access_codes"
           f"?code=eq.{urllib.parse.quote(code.strip().upper())}&active=eq.true&select=id,name,usage_count,expires_at")
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            rows = json.loads(r.read().decode())
        if rows:
            row = rows[0]
            # Check expiry if set
            expires_at = row.get("expires_at")
            if expires_at:
                try:
                    exp = _dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if _dt.datetime.now(_dt.timezone.utc) > exp:
                        return None, False, "expired"
                except Exception:
                    pass
            return row["name"], row["id"], None
        return None, False, "invalid"
    except Exception:
        return None, False, "invalid"

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
                st.session_state.is_beta = False
                st.rerun()
            else:
                name, code_id, err = validate_code(entered_code)
                if name and code_id:
                    st.session_state.access_granted = True
                    st.session_state.access_name = name
                    st.session_state.access_code_id = code_id
                    # BETA- prefix = limited preview access
                    st.session_state.is_beta = clean_code.startswith("BETA-")
                    # Store expiry label for sidebar display
                    if st.session_state.get("_login_expires_at"):
                        import datetime as _dt2
                        try:
                            exp2 = _dt2.datetime.fromisoformat(
                                st.session_state["_login_expires_at"].replace("Z", "+00:00"))
                            dl = (exp2 - _dt2.datetime.now(_dt2.timezone.utc)).days
                            st.session_state.trial_expires_label = f"Trial ends in {dl} day{'s' if dl != 1 else ''}."
                        except Exception:
                            pass
                    record_code_use(code_id)
                    st.rerun()
                elif err == "expired":
                    st.error("⏰ Your trial has ended. Contact DFS Cards to upgrade to full access.")
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
    data = json.dumps({"query": query, "limit": 10}).encode()
    headers_list = [
        # Try multiple User-Agent strings — GemRate may block common bot UAs
        {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "Content-Type": "application/json", "Accept": "application/json"},
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "Content-Type": "application/json", "Accept": "application/json"},
    ]
    for hdrs in headers_list:
        req = urllib.request.Request(
            "https://www.gemrate.com/universal-search-query",
            data=data, headers=hdrs, method="POST",
        )
        try:
            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as r:
                result = json.loads(r.read().decode())
                if result:  # got real data — stop trying
                    return result
        except Exception:
            continue
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

    # Prizm → Panini Prizm (GemRate indexes with manufacturer name)
    if "prizm" in ql and "panini" not in ql:
        queries.append(q.replace("Prizm", "Panini Prizm").replace("prizm", "Panini Prizm"))

    # Optic → Panini Optic
    if "optic" in ql and "panini" not in ql:
        queries.append(q.replace("Optic", "Panini Optic").replace("optic", "Panini Optic"))

    # Chrome → Topps Chrome (if not Bowman Chrome already)
    if "chrome" in ql and "topps" not in ql and "bowman" not in ql:
        queries.append(q.replace("Chrome", "Topps Chrome").replace("chrome", "Topps Chrome"))

    # Bowman Chrome prospect autograph variant
    if "bowman" in ql and "chrome" in ql and "autograph" not in ql:
        queries.append(q + " autograph")

    # Draft Picks → Prizm Draft Picks (Panini)
    if "draft picks" in ql and "panini" not in ql:
        queries.append("Panini " + q)

    return list(dict.fromkeys(queries))  # dedupe while preserving order

@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=600, show_spinner=False)
def ch_card_match(query: str):
    """AI-powered best-match search — returns card with prices by grade."""
    result = _ch_post("/v1/cards/card-match", {"query": query, "page": 1, "page_size": 5})
    if not result or "match" not in result:
        return None
    return result["match"]

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

@st.cache_data(ttl=3600, show_spinner=False)
def ch_card_image(card_id: str) -> str:
    """Fetch the card image URL from CardHedger card-details."""
    result = _ch_post("/v1/cards/card-details", {"card_id": card_id})
    if not result:
        return ""
    cards = result.get("cards") or []
    if cards and isinstance(cards, list):
        return cards[0].get("image", "") or ""
    return result.get("image", "") or ""

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

# ─── Quick search target list ─────────────────────────────────────────────────
QUICK_SEARCHES = [
    ("🏀", "Cooper Flagg Topps Chrome Rookie"),
    ("🏀", "Steph Curry Topps Chrome Paradox Refractor"),
    ("🏀", "Caitlin Clark Panini Prizm WNBA Rookie"),
    ("🏀", "Luka Doncic Panini Prizm Silver Rookie"),
    ("🏀", "Zion Williamson Panini Prizm Rookie"),
    ("🏈", "Cam Ward Panini Prizm Draft Picks Rookie"),
    ("🏈", "Ashton Jeanty Panini Prizm Draft Picks Rookie"),
    ("🏈", "Travis Hunter Panini Prizm Draft Picks Rookie"),
    ("🏈", "Drake Maye Panini Prizm Rookie"),
    ("🏈", "Shedeur Sanders Panini Prizm Draft Picks Rookie"),
    ("⚾", "Paul Skenes Topps Chrome Rookie"),
    ("⚾", "Aaron Judge Topps"),
    ("⚾", "Elly De La Cruz Bowman Chrome Rookie"),
]

# ─── Gem rate visual helpers ──────────────────────────────────────────────────
def gem_color_hex(g):
    """Return a hex color for a gem rate percentage."""
    if g is None:
        return "#94a3b8"
    if g >= 60:
        return "#22c55e"   # green
    if g >= 35:
        return "#f59e0b"   # yellow
    return "#ef4444"       # red

def gem_bar_html(g):
    """Return an HTML progress bar for embedding in st.markdown."""
    if g is None:
        return "—"
    color = gem_color_hex(g)
    pct = min(g, 100)
    return (
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<span style="color:{color};font-weight:700;font-size:15px;min-width:42px">{g:.1f}%</span>'
        f'<div style="flex:1;background:#22263a;border-radius:4px;height:8px;min-width:80px">'
        f'<div style="width:{pct}%;height:8px;border-radius:4px;background:{color}"></div>'
        f'</div></div>'
    )

# ─── URL builders ─────────────────────────────────────────────────────────────
def gemrate_url(gid):
    return f"https://www.gemrate.com/card/{gid}"

def ebay_raw_url(desc):
    q = urllib.parse.quote_plus(desc + " raw")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1&LH_BIN=1&_sop=13"

def ebay_raw_sold_all_url(desc):
    """Raw sold comps — all sale types (BIN + auction + offers)."""
    q = urllib.parse.quote_plus(desc)
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1&_sop=13&_sacat=212"

def ebay_buy_bin_url(desc):
    """Buy raw — BIN listings, cheapest first."""
    q = urllib.parse.quote_plus(desc)
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_BIN=1&_sop=15&_sacat=212"

def ebay_buy_auction_url(desc):
    """Buy raw — auctions ending soonest."""
    q = urllib.parse.quote_plus(desc)
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Auction=1&_sop=1&_sacat=212"

def ebay_graded_sold_url(desc):
    q = urllib.parse.quote_plus(desc + " PSA 10")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1&LH_BIN=1&_sop=13"

def ebay_psa9_sold_url(desc):
    q = urllib.parse.quote_plus(desc + " PSA 9")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1&_sop=13&_sacat=212"

def ebay_graded_buy_url(desc):
    q = urllib.parse.quote_plus(desc + " PSA 10")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_BIN=1&_sop=15"

def psa_pop_url(desc):
    q = urllib.parse.quote_plus(desc)
    return f"https://www.psacertify.com/s/search?q={q}"

# ─── ROI logic ────────────────────────────────────────────────────────────────
def calc_opp_cost(raw_cost, psa_tier, opp_rate: float, ship_cost: float = 0.0) -> float:
    """Return the opportunity cost of having money locked up at PSA.

    All upfront cash (card + grading fee + shipping) is locked up during the wait,
    so all of it earns zero return for that period.
    opp_rate: annual return % you expect elsewhere (e.g. 12.0 = 12%/yr)
    """
    if opp_rate <= 0:
        return 0.0
    fee = PSA_FEES.get(psa_tier, 50)
    biz_days = PSA_DAYS.get(psa_tier, 60)
    cal_days = biz_days * 1.4
    capital_at_risk = raw_cost + fee + ship_cost   # everything paid upfront is locked
    return round(capital_at_risk * (opp_rate / 100) * (cal_days / 365), 2)

def target_price(raw_cost, psa_tier, roi=4.0, opp_rate=0.0, ship_cost=0.0):
    fee = PSA_FEES.get(psa_tier, 50)
    opp = calc_opp_cost(raw_cost, psa_tier, opp_rate, ship_cost)
    total_cost = raw_cost + fee + ship_cost + opp
    return (total_cost * roi) / (1 - EBAY_FEE)

def calc_net_roi(raw_cost, psa_tier, graded_price, opp_rate=0.0, ship_cost=0.0):
    fee = PSA_FEES.get(psa_tier, 50)
    opp = calc_opp_cost(raw_cost, psa_tier, opp_rate, ship_cost)
    total_cost = raw_cost + fee + ship_cost + opp
    net = graded_price * (1 - EBAY_FEE) - total_cost
    roi = (net / total_cost * 100) if total_cost > 0 else 0
    return round(net, 2), round(roi, 1)

def verdict(raw_cost, psa_tier, gem_rate, graded_price, min_gem, roi_target, opp_rate=0.0, ship_cost=0.0):
    if gem_rate is None or gem_rate < min_gem:
        return "❌ NO-GO", "red", f"Gem rate {gem_rate or 0:.1f}% below {min_gem:.0f}% floor"
    tgt = target_price(raw_cost, psa_tier, roi_target, opp_rate, ship_cost)
    net, roi = calc_net_roi(raw_cost, psa_tier, graded_price, opp_rate, ship_cost)
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
is_beta = st.session_state.get("is_beta", False)

with st.sidebar:
    st.markdown("## 💎 DFS Card Grader")
    st.caption(f"Gem rate research + grading ROI calculator · v{APP_VERSION}")
    access_name = st.session_state.get("access_name", "")
    if access_name:
        if is_beta:
            st.markdown(f"👤 **{access_name}** &nbsp; `BETA`")
            _exp = st.session_state.get("trial_expires_label", "")
            st.info(f"🔓 Beta Preview — Card Research & Inventory Check unlocked.{' ' + _exp if _exp else ''}", icon="ℹ️")
        else:
            st.markdown(f"👤 **{access_name}**")
    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    roi_target = st.number_input("ROI target (×)", min_value=1.0, max_value=20.0, value=4.0, step=0.5)
    min_gem = st.number_input("Min gem rate (%)", min_value=0.0, max_value=100.0, value=40.0, step=5.0)
    default_tier = st.selectbox("Default grading tier", list(PSA_FEES.keys()), index=0)

    st.markdown("---")
    st.markdown("**📦 Shipping Costs**")
    st.caption("Split your total shipping cost across the cards in the submission.")
    _sc1, _sc2 = st.columns(2)
    with _sc1:
        ship_to = st.number_input(
            "To PSA ($/card)", min_value=0.0, value=0.0, step=0.50,
            help="Your actual cost to ship to PSA including insurance, divided by number of cards in the submission"
        )
    with _sc2:
        ship_return = st.number_input(
            "Return ($/card)", min_value=0.0, value=0.0, step=0.50,
            help="PSA return shipping cost including insurance, divided by cards in order"
        )
    ship_cost = round(ship_to + ship_return, 2)
    if ship_cost > 0:
        st.caption(f"Total shipping per card: **${ship_cost:.2f}**")
    else:
        st.caption("Enter your actual shipping + insurance costs above.")

    st.markdown("---")
    st.markdown("**⏳ Time Cost of Capital**")
    st.caption(
        "While your card sits at PSA, that cash earns nothing. "
        "Set your expected annual return to reveal the true hidden cost."
    )
    opp_rate = st.slider(
        "Opportunity cost rate (% / year)",
        min_value=0.0, max_value=50.0, value=12.0, step=1.0,
        help="e.g. 12%/yr: $649 locked at Express (~35 days) = $7.47 hidden cost",
    )
    if opp_rate > 0:
        _ex_raw, _ex_tier = 200.0, default_tier
        _ex_opp = calc_opp_cost(_ex_raw, _ex_tier, opp_rate, ship_cost)
        _ex_days = int(PSA_DAYS.get(_ex_tier, 60) * 1.4)
        st.caption(f"→ $200 card · {_ex_days} cal. days · **${_ex_opp:.2f} hidden cost**")

    st.markdown("---")
    st.markdown("**Grading fees (updated May 2025)**")
    for tier, info in PSA_FEES_ALL.items():
        biz = info['days']
        st.caption(f"${info['fee']:.2f} · ~{biz} biz days · insured to ${info['max_insured']:,} — {tier.split('(')[0].strip()}")
    st.caption(f"eBay sell fee: {EBAY_FEE*100:.2f}%")

# ─── What's New dialog ────────────────────────────────────────────────────────
_WN_KEY = f"wn_seen_{APP_VERSION}"

@st.dialog("🎉 What's New in DFS Card Grader", width="large")
def _show_whats_new():
    notes = RELEASE_NOTES.get(APP_VERSION, {})
    st.markdown(
        f'<div style="display:inline-block;background:#1e2130;border:1px solid #2e3250;'
        f'border-radius:8px;padding:4px 12px;font-size:0.75rem;color:#7c8db5;'
        f'margin-bottom:12px">v{APP_VERSION}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"### {notes.get('emoji','🎉')} {notes.get('title','Updates')}")
    st.markdown("")
    for icon, text in notes.get("items", []):
        st.markdown(
            f'<div style="display:flex;gap:10px;align-items:flex-start;'
            f'margin-bottom:10px;padding:10px 14px;background:#1e2130;'
            f'border-radius:8px;border:1px solid #2e3250">'
            f'<span style="font-size:1.2rem;line-height:1.4">{icon}</span>'
            f'<span style="font-size:0.9rem;color:#c8d3e8;line-height:1.5">{text}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown("")
    if st.button("Got it, let's go →", type="primary", use_container_width=True):
        st.session_state[_WN_KEY] = True
        st.rerun()

if not st.session_state.get(_WN_KEY) and APP_VERSION in RELEASE_NOTES:
    _show_whats_new()

# ─── Dashboard KPI tiles ──────────────────────────────────────────────────────
if not is_beta and SUPABASE_URL:
    _dash_rows = sb_get()
    _df_d = pd.DataFrame(_dash_rows) if _dash_rows else pd.DataFrame()
    _total   = len(_df_d)
    _go      = len(_df_d[_df_d["go_no_go"].str.startswith("✅", na=False)]) if not _df_d.empty else 0
    _pending = len(_df_d[_df_d["status"] == "Submitted"]) if not _df_d.empty else 0
    _returned= len(_df_d[_df_d["status"].isin(["Received","Sold"])]) if not _df_d.empty else 0
    try:
        _go_mask  = _df_d["go_no_go"].str.startswith("✅", na=False)
        _sub_cost = pd.to_numeric(_df_d.loc[_go_mask, "psa_fee"], errors="coerce").sum()
        _est_net  = pd.to_numeric(_df_d.loc[_go_mask, "est_net"], errors="coerce").sum()
    except Exception:
        _sub_cost = _est_net = 0

    def _kpi(label, value, sub, color):
        return (
            f'<div style="background:#1e2130;border:1px solid #2e3250;border-radius:10px;padding:16px 18px">'
            f'<div style="font-size:0.68rem;color:#7c8db5;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">{label}</div>'
            f'<div style="font-size:1.9rem;font-weight:700;color:{color};line-height:1.1">{value}</div>'
            f'<div style="font-size:0.7rem;color:#556;margin-top:5px">{sub}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px;margin-bottom:20px">'
        + _kpi("Cards in Tracker",    _total,              "in submission tracker",   "#4f8ef7")
        + _kpi("Flagged: Submit",     _go,                 "pass your ROI threshold", "#22c55e")
        + _kpi("Est. Submission Cost",f"${_sub_cost:,.0f}","for GO cards",            "#f59e0b")
        + _kpi("Est. Net Profit",     f"${_est_net:,.0f}", "if all grade PSA 10",     "#22c55e")
        + _kpi("Pending at PSA",      _pending,            "cards submitted",         "#4f8ef7")
        + _kpi("Grades Returned",     _returned,           "received back",           "#22c55e")
        + _kpi("ROI Threshold",       f"{roi_target:.0f}×","minimum to flag submit",  "#f59e0b")
        + '</div>',
        unsafe_allow_html=True,
    )

# ─── Tabs ─────────────────────────────────────────────────────────────────────
if is_beta:
    st.info("🔓 **Beta Preview** — You have access to Card Research and Inventory Check. Submission Tracker and Downloads unlock with a full membership.", icon="💎")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 Card Research", "📦 Inventory Check", "📬 Submission Tracker", "📥 Downloads"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Card Research
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## 🔍 Card Research")
    st.markdown("Search any card — owned or not. Get gem rate, graded value comps, and eBay links.")
    st.caption("Tip: include the full set name for best results — e.g. *Steph Curry Topps Chrome Paradox* not just *Steph Curry Paradox*")

    col_q, col_btn, col_clr = st.columns([5, 1, 1])
    with col_q:
        query = st.text_input("Search", placeholder="e.g.  Curry Topps Chrome Paradox  |  Luka Prizm RC auto  |  Wemby Optic", label_visibility="collapsed")
    with col_btn:
        do_search = st.button("Search", use_container_width=True, type="primary")
    with col_clr:
        if st.button("🔄 Clear", use_container_width=True, help="Clear cached results and retry"):
            st.cache_data.clear()
            st.session_state.pop("gr_results", None)
            st.session_state.pop("ch_match_result", None)
            st.session_state.pop("last_q", None)
            st.rerun()

    # ── Quick search buttons ──────────────────────────────────────────────────
    with st.expander("⚡ Quick Search — Target Card List", expanded=False):
        st.caption("One-click searches for your buy targets. Click any card to auto-search.")
        sports = ["🏀", "🏈", "⚾"]
        sport_names = {"🏀": "Basketball", "🏈": "Football", "⚾": "Baseball"}
        for sport_emoji in sports:
            sport_cards = [(e, q) for e, q in QUICK_SEARCHES if e == sport_emoji]
            if sport_cards:
                st.markdown(f"**{sport_emoji} {sport_names[sport_emoji]}**")
                cols = st.columns(min(len(sport_cards), 4))
                for idx, (_, qs) in enumerate(sport_cards):
                    short = qs[:35] + ("…" if len(qs) > 35 else "")
                    if cols[idx % 4].button(short, key=f"qs_{qs}", use_container_width=True):
                        st.session_state.quick_search_query = qs
                        st.rerun()

    # Pick up quick-search selection — always overrides whatever is in the text box
    if st.session_state.get("quick_search_query"):
        query = st.session_state.pop("quick_search_query")
        do_search = True

    if query and (do_search or st.session_state.get("last_q") != query):
        st.session_state.last_q = query
        with st.spinner("Searching GemRate..."):
            st.session_state.gr_results = search_gemrate(query)
        # If GemRate returned nothing, fall back to CardHedger AI match
        if not st.session_state.gr_results and CARDHEDGER_KEY:
            with st.spinner("GemRate unavailable — fetching prices from CardHedger..."):
                st.session_state.ch_match_result = ch_card_match(query)
        else:
            st.session_state.pop("ch_match_result", None)

    results = st.session_state.get("gr_results", [])
    ch_match_data = st.session_state.get("ch_match_result")

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

        # ── Card image via CardHedger ────────────────────────────────────────
        gr_image_url = ""
        if CARDHEDGER_KEY:
            gr_ch_match = ch_card_match(desc)
            if gr_ch_match:
                gr_image_url = gr_ch_match.get("image", "") or ""
                if not gr_image_url and gr_ch_match.get("card_id"):
                    gr_image_url = ch_card_image(gr_ch_match["card_id"])

        if gr_image_url:
            img_c, stats_c = st.columns([1, 3])
            with img_c:
                st.image(gr_image_url, use_container_width=True)
            with stats_c:
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.markdown("**Gem Rate (PSA 10)**")
                    st.markdown(gem_bar_html(gem), unsafe_allow_html=True)
                m2.metric("Total Pop", f"{sel.get('total_population', 0):,}")
                m3.metric("Gem Copies", f"{sel.get('gems', 0):,}")
                st.markdown(f"[📊 Full pop report on GemRate]({gemrate_url(sel.get('gemrate_id',''))})")
        else:
            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown("**Gem Rate (PSA 10)**")
                st.markdown(gem_bar_html(gem), unsafe_allow_html=True)
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
                def _fmt_sale_row(s):
                    p = _extract_price(s)
                    if not p:
                        return None
                    raw_date = s.get("sale_date", "")
                    try:
                        import datetime as _dt
                        d = _dt.datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                        date_str = d.strftime("%-m/%-d/%y")
                    except Exception:
                        date_str = raw_date[:10] if raw_date else ""
                    sale_type = s.get("sale_type", "") or ""
                    type_label = "🏷 BIN" if "bin" in sale_type.lower() or sale_type == "" else \
                                 "🔨 Auction" if "auction" in sale_type.lower() else \
                                 "💬 Offer" if "offer" in sale_type.lower() else sale_type
                    return {"Price": f"${p:,.2f}", "Date": date_str, "Type": type_label}

                fc1, fc2 = st.columns(2)
                with fc1:
                    st.markdown("**📦 Raw — recent sold comps**")
                    if ch_raw_sales:
                        rows_r = [r for s in ch_raw_sales[:15] if (r := _fmt_sale_row(s))]
                        if rows_r:
                            st.dataframe(pd.DataFrame(rows_r), use_container_width=True, hide_index=True, height=200)
                    if ch_raw_avg:
                        st.markdown(f"**Comp avg: ${ch_raw_avg:,.2f}**")
                    elif not ch_raw_sales:
                        st.info("No raw comps found")
                with fc2:
                    st.markdown("**💎 PSA 10 — recent sold comps**")
                    if ch_psa10_sales:
                        rows_g = [r for s in ch_psa10_sales[:15] if (r := _fmt_sale_row(s))]
                        if rows_g:
                            st.dataframe(pd.DataFrame(rows_g), use_container_width=True, hide_index=True, height=200)
                    if ch_psa10_avg:
                        st.markdown(f"**Comp avg: ${ch_psa10_avg:,.2f}**")
                    elif not ch_psa10_sales:
                        st.info("No PSA 10 comps found")
            if ch_raw_sales or ch_psa10_sales:
                st.caption("⚠️ Comp avg includes all sale types. 🏷 BIN = fixed price (most reliable). 💬 Offer = accepted below ask. 🔨 Auction = bidding (use with caution).")
            elif CARDHEDGER_KEY:
                st.info("No CardHedger match found for this card — enter prices manually below.")
        else:
            st.info("📊 Live sold comps will appear here once the CardHedger API is connected.")

        raw_auto    = ch_raw_avg
        graded_auto = ch_psa10_avg

        ra1, ra2, ra3 = st.columns(3)
        with ra1:
            raw_cost = st.number_input(
                "Your cost for the raw card ($)", min_value=0.0,
                value=float(raw_auto) if raw_auto else 50.0,
                step=5.0, key="t1_raw",
            )
            st.caption("What you paid (or plan to pay) for the ungraded card. Pre-filled from live comps — update to your actual price.")
        with ra2:
            tier = st.selectbox("Grading tier", list(PSA_FEES.keys()),
                                index=list(PSA_FEES.keys()).index(default_tier), key="t1_tier")
            st.caption("PSA service level you'll submit under. Sets the grading fee used in the ROI calculation.")
        with ra3:
            graded_price = st.number_input(
                "Expected PSA 10 sell price ($)", min_value=0.0,
                value=float(graded_auto) if graded_auto else 0.0,
                step=10.0, key="t1_graded",
            )
            st.caption("The price you expect to sell a PSA 10 for on eBay. Pre-filled from live comps — adjust up or down based on your read of the market.")

        if raw_cost > 0:
            fee      = PSA_FEES[tier]
            opp      = calc_opp_cost(raw_cost, tier, opp_rate, ship_cost)
            tgt      = target_price(raw_cost, tier, roi_target, opp_rate, ship_cost)
            cal_days = int(PSA_DAYS.get(tier, 60) * 1.4)
            total_in = raw_cost + fee + ship_cost + opp
            bd1, bd2, bd3, bd4, bd5, bd6 = st.columns(6)
            bd1.metric("Raw card",                             f"${raw_cost:,.2f}")
            bd2.metric("Grading fee",                         f"${fee:.2f}")
            bd3.metric("Shipping (to + return)",              f"${ship_cost:.2f}",
                       help="Per-card shipping to PSA + return. Set in sidebar ⚙️")
            bd4.metric(f"⏳ Time cost ({cal_days} days)",     f"${opp:,.2f}",
                       help=f"At {opp_rate:.0f}%/yr, ${raw_cost+fee+ship_cost:,.0f} locked for {cal_days} days = ${opp:,.2f} you can't redeploy")
            bd5.metric(f"Target PSA 10 ({roi_target:.0f}×)",  f"${tgt:,.0f}")
            bd6.metric("eBay fees",                           f"${graded_price * EBAY_FEE:,.2f}" if graded_price else "—")

            st.caption(
                f"💡 **True total cost: ${total_in:,.2f}** — raw ${raw_cost:,.2f} + grading ${fee:.2f} + "
                f"shipping ${ship_cost:.2f} + time cost ${opp:,.2f}. "
                f"Most apps only count the grading fee."
            )

            if graded_price > 0:
                v, color, msg = verdict(raw_cost, tier, gem, graded_price, min_gem, roi_target, opp_rate, ship_cost)
                net, roi = calc_net_roi(raw_cost, tier, graded_price, opp_rate, ship_cost)
                if color == "green":
                    st.success(f"{v} — {msg}")
                else:
                    st.error(f"{v} — {msg}")
                r1, r2, r3 = st.columns(3)
                r1.metric("Est. Net Profit", f"${net:,.0f}", help="After ALL costs: raw, grading, shipping, time cost, and eBay fees")
                r2.metric("Est. ROI",        f"{roi:.0f}%")
                if ch_trend_dir:
                    r3.metric("90-Day Trend", trend_badge(ch_trend_dir, ch_trend_pct))

                summary = f"""{query}
Gem Rate: {fmt_gem(gem)} | Raw: ${raw_cost:,.2f} | Gem 10 Avg: ${graded_price:,.2f}
Grading fee: ${fee:.2f} | Shipping: ${ship_cost:.2f} | Time cost ({cal_days} days @ {opp_rate:.0f}%/yr): ${opp:,.2f}
True total cost: ${total_in:,.2f} | Target: ${tgt:,.0f} | Net: ${net:,.0f} | ROI: {roi:.0f}%
{v}"""
                with st.expander("📋 Copy Analysis"):
                    st.code(summary, language=None)
            else:
                st.info("Enter a Gem 10 avg price above to get a GO/NO-GO decision")

        st.markdown("#### 🔍 Card Finder Links")
        st.caption("All the links you need — buy raw, check sold comps, verify gem rate, or look up the PSA pop report.")

        _link_style = (  # noqa: F841  (also used in CardHedger fallback block below)
            "display:inline-flex;align-items:center;gap:6px;padding:8px 14px;"
            "border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;"
            "border:1px solid;margin:3px;"
        )
        st.markdown(
            f"""
            <div style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:8px">
              <a href="{ebay_buy_bin_url(desc)}" target="_blank"
                 style="{_link_style}color:#e5a310;border-color:rgba(229,163,16,.4);background:rgba(229,163,16,.08)">
                 🛒 Buy Raw (BIN)</a>
              <a href="{ebay_buy_auction_url(desc)}" target="_blank"
                 style="{_link_style}color:#e5a310;border-color:rgba(229,163,16,.4);background:rgba(229,163,16,.08)">
                 ⚡ Buy Raw (Auction)</a>
              <a href="{ebay_raw_sold_all_url(desc)}" target="_blank"
                 style="{_link_style}color:#94a3b8;border-color:rgba(148,163,184,.3);background:rgba(148,163,184,.06)">
                 📊 Raw Sold Comps</a>
              <a href="{ebay_graded_sold_url(desc)}" target="_blank"
                 style="{_link_style}color:#22c55e;border-color:rgba(34,197,94,.4);background:rgba(34,197,94,.08)">
                 🔴 PSA 10 Sold Comps</a>
              <a href="{ebay_psa9_sold_url(desc)}" target="_blank"
                 style="{_link_style}color:#f59e0b;border-color:rgba(245,158,11,.4);background:rgba(245,158,11,.08)">
                 🟡 PSA 9 Sold Comps</a>
              <a href="{gemrate_url(sel.get('gemrate_id',''))}" target="_blank"
                 style="{_link_style}color:#4f8ef7;border-color:rgba(79,142,247,.4);background:rgba(79,142,247,.08)">
                 💎 GemRate.com</a>
              <a href="{psa_pop_url(desc)}" target="_blank"
                 style="{_link_style}color:#7c5cfc;border-color:rgba(124,92,252,.4);background:rgba(124,92,252,.08)">
                 🏆 PSA Pop Report</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        if st.button("➕ Add to Submission Tracker", type="secondary"):
            if raw_cost <= 0:
                st.warning("Enter a raw buy price first")
            else:
                fee = PSA_FEES[tier]
                tgt = target_price(raw_cost, tier, roi_target, opp_rate, ship_cost)
                net, roi = calc_net_roi(raw_cost, tier, graded_price, opp_rate, ship_cost) if graded_price > 0 else (None, None)
                v, _, _ = verdict(raw_cost, tier, gem, graded_price, min_gem, roi_target, opp_rate, ship_cost) if graded_price > 0 else ("Pending", "", "")
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

    elif ch_match_data:
        # ── CardHedger AI-match fallback (GemRate unavailable) ───────────────
        confidence  = ch_match_data.get("confidence", 0)
        reasoning   = ch_match_data.get("reasoning", "")
        desc        = ch_match_data.get("description", query)
        player      = ch_match_data.get("player", "")
        set_name    = ch_match_data.get("set", "")
        variant     = ch_match_data.get("variant", "")
        prices_list = ch_match_data.get("prices", [])

        # Build price map
        price_map = {}
        for p in prices_list:
            try:
                price_map[p["grade"]] = float(p["price"])
            except Exception:
                pass
        ch_psa10 = price_map.get("PSA 10")
        ch_psa9  = price_map.get("PSA 9")
        ch_raw   = price_map.get("Raw")

        _link_style_fb = (
            "display:inline-flex;align-items:center;gap:6px;padding:8px 14px;"
            "border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;"
            "border:1px solid;margin:3px;"
        )

        st.info(
            "💎 **Showing live CardHedger prices** — GemRate is currently unavailable. "
            "Gem rate (PSA pop) cannot be checked right now; ROI calculation still works.",
            icon="ℹ️",
        )

        # ── Card image ────────────────────────────────────────────────────────
        image_url = ch_match_data.get("image", "") or ""
        if not image_url and ch_match_data.get("card_id"):
            with st.spinner("Loading card image..."):
                image_url = ch_card_image(ch_match_data["card_id"])

        img_col, info_col = st.columns([1, 3])
        with img_col:
            if image_url:
                st.image(image_url, use_container_width=True)
            else:
                st.markdown(
                    '<div style="background:#1e2130;border:1px solid #2e3250;border-radius:10px;'
                    'height:180px;display:flex;align-items:center;justify-content:center;'
                    'color:#4a5568;font-size:2rem;">🃏</div>',
                    unsafe_allow_html=True,
                )
        with info_col:
            st.markdown(f"### {desc}")
            ci1, ci2, ci3 = st.columns(3)
            ci1.markdown(f"**Set:** {set_name}")
            ci2.markdown(f"**Variant:** {variant}")
            ci3.markdown(f"**AI Match confidence:** {confidence * 100:.0f}%")

        st.markdown("#### 💰 Market Prices (CardHedger)")
        if prices_list:
            price_rows_fb = [{"Grade": p.get("grade", ""), "Avg Market Price": f"${float(p.get('price', 0)):,.2f}"} for p in prices_list]
            st.dataframe(pd.DataFrame(price_rows_fb), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.text_input("📋 Card name (tap → select all → copy)", value=desc, key="card_name_copy")

        fb1, fb2, fb3 = st.columns(3)
        with fb1:
            st.markdown("**Gem Rate (PSA 10)**")
            st.markdown('<span style="color:#94a3b8;font-size:14px">N/A — GemRate offline</span>', unsafe_allow_html=True)
        if ch_psa10:
            fb2.metric("PSA 10 Avg", f"${ch_psa10:,.2f}")
        if ch_psa9:
            fb3.metric("PSA 9 Avg", f"${ch_psa9:,.2f}")

        st.markdown("#### ROI Analysis")

        ra1, ra2, ra3 = st.columns(3)
        with ra1:
            raw_cost = st.number_input(
                "Your cost for the raw card ($)", min_value=0.0,
                value=float(ch_raw) if ch_raw else 50.0,
                step=5.0, key="t1_raw",
            )
            st.caption("Pre-filled from CardHedger live raw avg — update to your actual price.")
        with ra2:
            tier = st.selectbox("Grading tier", list(PSA_FEES.keys()),
                                index=list(PSA_FEES.keys()).index(default_tier), key="t1_tier")
            st.caption("PSA service level you'll submit under.")
        with ra3:
            graded_price = st.number_input(
                "Expected PSA 10 sell price ($)", min_value=0.0,
                value=float(ch_psa10) if ch_psa10 else 0.0,
                step=10.0, key="t1_graded",
            )
            st.caption("Pre-filled from CardHedger PSA 10 avg — adjust as needed.")

        if raw_cost > 0:
            fee      = PSA_FEES[tier]
            opp      = calc_opp_cost(raw_cost, tier, opp_rate, ship_cost)
            tgt      = target_price(raw_cost, tier, roi_target, opp_rate, ship_cost)
            cal_days = int(PSA_DAYS.get(tier, 60) * 1.4)
            total_in = raw_cost + fee + ship_cost + opp
            bd1, bd2, bd3, bd4, bd5, bd6 = st.columns(6)
            bd1.metric("Raw card",                            f"${raw_cost:,.2f}")
            bd2.metric("Grading fee",                        f"${fee:.2f}")
            bd3.metric("Shipping (to + return)",             f"${ship_cost:.2f}",
                       help="Per-card shipping to PSA + return. Set in sidebar ⚙️")
            bd4.metric(f"⏳ Time cost ({cal_days} days)",    f"${opp:,.2f}",
                       help=f"At {opp_rate:.0f}%/yr, ${raw_cost+fee+ship_cost:,.0f} locked for {cal_days} days")
            bd5.metric(f"Target PSA 10 ({roi_target:.0f}×)", f"${tgt:,.0f}")
            bd6.metric("eBay fees",                          f"${graded_price * EBAY_FEE:,.2f}" if graded_price else "—")

            st.caption(
                f"💡 **True total cost: ${total_in:,.2f}** — raw ${raw_cost:,.2f} + grading ${fee:.2f} + "
                f"shipping ${ship_cost:.2f} + time cost ${opp:,.2f}. "
                f"Most apps only count the grading fee."
            )

            if graded_price > 0:
                net, roi = calc_net_roi(raw_cost, tier, graded_price, opp_rate, ship_cost)
                if graded_price >= tgt:
                    st.success(f"✅ GO — PSA 10 avg ${graded_price:,.0f} clears ${tgt:,.0f} target | Net ~${net:,.0f} | ROI ~{roi:.0f}% *(verify gem rate on PSA pop before submitting)*")
                else:
                    st.error(f"❌ NO-GO — PSA 10 avg ${graded_price:,.0f} needs ${tgt:,.0f} for {roi_target:.0f}× | ROI only ~{roi:.0f}%")
                r1, r2 = st.columns(2)
                r1.metric("Est. Net Profit", f"${net:,.0f}", help="After ALL costs: raw, grading, shipping, time cost, and eBay fees")
                r2.metric("Est. ROI",        f"{roi:.0f}%")

                summary_fb = f"""{desc}
Source: CardHedger | Gem Rate: N/A (GemRate offline)
Raw: ${raw_cost:,.2f} | PSA 10 Avg: ${graded_price:,.2f}
Grading fee: ${fee:.2f} | Shipping: ${ship_cost:.2f} | Time cost ({cal_days} days @ {opp_rate:.0f}%/yr): ${opp:,.2f}
True total cost: ${total_in:,.2f} | Target: ${tgt:,.0f} | Net: ${net:,.0f} | ROI: {roi:.0f}%"""
                with st.expander("📋 Copy Analysis"):
                    st.code(summary_fb, language=None)
            else:
                st.info("Enter a PSA 10 price above to get a GO/NO-GO decision")

        st.markdown("#### 🔍 Card Finder Links")
        st.markdown(
            f"""<div style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:8px">
              <a href="{ebay_buy_bin_url(desc)}" target="_blank"
                 style="{_link_style_fb}color:#e5a310;border-color:rgba(229,163,16,.4);background:rgba(229,163,16,.08)">
                 🛒 Buy Raw (BIN)</a>
              <a href="{ebay_buy_auction_url(desc)}" target="_blank"
                 style="{_link_style_fb}color:#e5a310;border-color:rgba(229,163,16,.4);background:rgba(229,163,16,.08)">
                 ⚡ Buy Raw (Auction)</a>
              <a href="{ebay_raw_sold_all_url(desc)}" target="_blank"
                 style="{_link_style_fb}color:#94a3b8;border-color:rgba(148,163,184,.3);background:rgba(148,163,184,.06)">
                 📊 Raw Sold Comps</a>
              <a href="{ebay_graded_sold_url(desc)}" target="_blank"
                 style="{_link_style_fb}color:#22c55e;border-color:rgba(34,197,94,.4);background:rgba(34,197,94,.08)">
                 🔴 PSA 10 Sold Comps</a>
              <a href="{ebay_psa9_sold_url(desc)}" target="_blank"
                 style="{_link_style_fb}color:#f59e0b;border-color:rgba(245,158,11,.4);background:rgba(245,158,11,.08)">
                 🟡 PSA 9 Sold Comps</a>
              <a href="{psa_pop_url(desc)}" target="_blank"
                 style="{_link_style_fb}color:#7c5cfc;border-color:rgba(124,92,252,.4);background:rgba(124,92,252,.08)">
                 🏆 PSA Pop Report</a>
            </div>""",
            unsafe_allow_html=True,
        )

        if reasoning:
            with st.expander("🤖 AI Match Reasoning"):
                st.caption(reasoning)

        st.markdown("---")
        if st.button("➕ Add to Submission Tracker", type="secondary"):
            if raw_cost <= 0:
                st.warning("Enter a raw buy price first")
            else:
                fee = PSA_FEES[tier]
                tgt = target_price(raw_cost, tier, roi_target, opp_rate, ship_cost)
                net, roi_val = calc_net_roi(raw_cost, tier, graded_price, opp_rate, ship_cost) if graded_price > 0 else (None, None)
                v_fb = "✅ GO" if graded_price > 0 and graded_price >= tgt else "❌ NO-GO"
                sb_insert({
                    "date_added":       date.today().isoformat(),
                    "card_description": desc,
                    "year":             "",
                    "set_name":         set_name or "",
                    "parallel":         variant or "Base",
                    "raw_buy_price":    raw_cost,
                    "psa_tier":         tier,
                    "psa_fee":          fee,
                    "psa10_avg_price":  graded_price or None,
                    "target_price":     round(tgt, 2),
                    "gem_rate":         None,
                    "go_no_go":         v_fb,
                    "est_net":          net,
                    "est_roi":          f"{roi_val:.0f}%" if roi_val is not None else None,
                    "status":           "Queued",
                })
                st.success("Added to Submission Tracker ✓")

    elif query:
        gr_search_url = f"https://www.gemrate.com/search?q={urllib.parse.quote_plus(query)}"
        if CARDHEDGER_KEY:
            st.warning(
                f"No results found on GemRate or CardHedger for **{query}**. "
                "Try adjusting the search — include player name, set, year, and parallel "
                "*(e.g. Cooper Flagg 2025 Topps Chrome Rookie)*."
            )
        else:
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
    _is_owner = st.session_state.get("access_name", "") == "Duane"
    _wb_label = "DFS Operations Workbook" if _is_owner else "your Operations Workbook"

    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown(f"Upload your inventory to find grading candidates. Use the template below or upload {_wb_label} (.xlsx) directly.")
    with h2:
        st.download_button(
            label="⬇️ Download Template",
            data=make_template_csv(),
            file_name="card_inventory_template.csv",
            mime="text/csv",
            help="Fill this out and upload it below",
            use_container_width=True,
        )

    st.markdown("""
**How it works:**
1. Download the template → fill in your cards → save as CSV, or upload your Operations Workbook (.xlsx) directly
2. Upload it below → select a card → search GemRate → get GO/NO-GO
3. Add grading candidates directly to the Submission Tracker
""")

    uploaded = st.file_uploader(
        "Upload inventory (CSV template or Operations Workbook .xlsx)",
        type=["csv", "xlsx"],
        label_visibility="visible",
    )

    if uploaded:
        inv, source = load_inventory(uploaded)

        if inv is None:
            st.error(f"Could not read file: {source}")
        else:
            _source_label = (_wb_label if source == "workbook" else "inventory template")
            st.success(f"Loaded **{len(inv)} cards** from {_source_label}")

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
                with g1:
                    st.markdown("**Gem Rate (PSA 10)**")
                    st.markdown(gem_bar_html(gem_i), unsafe_allow_html=True)
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
    if is_beta:
        st.warning("🔒 Submission Tracker is available with full membership. Your beta preview includes Card Research and Inventory Check.")
    elif not SUPABASE_URL:
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
    if is_beta:
        st.warning("🔒 Downloads are available with full membership. Your beta preview includes Card Research and Inventory Check.")
    else:
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
                file_name="card_inventory_template.csv",
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
