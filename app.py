import streamlit as st
import pandas as pd
import json
import urllib.request
import urllib.parse
import ssl
import random
import string
from datetime import date, datetime
from pathlib import Path
import io
import base64
import csv
import re
import collections

# ─── Constants ────────────────────────────────────────────────────────────────
APP_VERSION = "1.5.1"

# Product branding — change APP_NAME on this one line to rebrand the whole app.
APP_NAME = "Card Grader Pro"
APP_TAGLINE = "Gem rate research + grading ROI calculator"

# Daily cap on live CardHedger look-ups per member (protects the API budget).
DAILY_PRICING_CAP = 50

RELEASE_NOTES = {
    "1.5.1": {
        "emoji": "📊",
        "title": "Full multi-channel import: Whatnot, DC Sports & manual sales",
        "items": [
            ("🎥", "Whatnot importer — upload WhatNot_Seller_Earnings XLSX. Net earnings are already after their fee, imported directly."),
            ("🏷️", "DC Sports importer — upload their CSV export directly to Sales & P&L. Only Paid rows imported; fees and net broken out per card."),
            ("✏️", "Manual sale entry — log social media, show sales, or any off-platform sale with a quick form. Platform, date, gross, fee, net."),
            ("🔒", "All importers deduplicate on re-import — safe to upload the same file multiple times."),
        ],
    },
    "1.5.0": {
        "emoji": "💰",
        "title": "Sales & P&L + DC Sports Consignment tracking",
        "items": [
            ("💰", "New 💰 Sales & P&L tab — import eBay and CollX sales exports. P&L by month, channel mix (eBay vs CollX vs DC Sports), and full sales log."),
            ("🏷️", "New 🏷️ Consignments tab — track DC Sports auction consignments. Import their CSV export, assign lot cost basis by SKU, and see net P&L per shipment and card."),
            ("📦", "7 DC Sports shipments ready to import — 151 cards, $3,479 net across batches 221184–245869."),
            ("📊", "1,536 eBay sales (Jul 2025–Jul 2026) ready to import into Sales & P&L — $24k gross revenue."),
        ],
    },
    "1.4.0": {
        "emoji": "🚀",
        "title": "CardHedger, maximized — Hot Movers, Scan, Player Demand",
        "items": [
            ("🔥", "New 🔥 Hot Movers tab — the week's biggest price gainers by sport. A buy-radar for what's heating up."),
            ("📷", "New 📷 Scan tab — snap a raw card to ID + price it (AI image match), or look up a graded slab by its cert number."),
            ("📊", "Player Demand on Card Research — weekly sold-volume trend across ALL of a player's cards (rising = growing demand)."),
            ("⚡", "Behind the scenes: Reprice/Operations now use one all-grades price call instead of many — fewer API calls, faster."),
        ],
    },
    "1.3.5": {
        "emoji": "📰",
        "title": "Player Watch — live news & injury alerts (free)",
        "items": [
            ("🔴", "Injury status on the card's player — pulls the live ESPN injury report (MLB/NBA/NFL/NHL) with the actual injury + comment."),
            ("📰", "Recent ESPN headlines for that player, so hot news (or bad news) shows up right next to the price — news moves cards before comps do."),
            ("💸", "Free — uses ESPN's public feeds, no extra subscription on top of CardHedger."),
            ("🌱", "Note: deep prospects may show 'no ESPN match' — coverage is best for established pros."),
        ],
    },
    "1.3.4": {
        "emoji": "📈",
        "title": "Sold Price Trend chart + sales volume",
        "items": [
            ("📈", "New Sold Price Trend chart on Card Research — pick a grade and view the sold-price line over 7 / 30 / 60 / 90 days."),
            ("🔀", "Δ 7d / 30d / 60d / 90d change tiles side by side — see momentum (short term) vs the longer-term trend at a glance."),
            ("🔁", "Sales-volume tiles (7-day & 30-day counts) show how liquid a card is — how easy it'll be to sell."),
            ("🛒", "Note: 'active for sale' shows n/a — CardHedger tracks sold sales only, not live listings."),
        ],
    },
    "1.3.3": {
        "emoji": "⚖️",
        "title": "FMV + Grade vs Flip now work while GemRate is offline",
        "items": [
            ("⚖️", "Grade vs Flip + PASS verdict now appear on the CardHedger screen too (the one you see when GemRate is down) — no longer hidden."),
            ("🎯", "FMV (cleaned value) + confidence grade now show on that screen and pre-fill your cost/sell prices."),
            ("📊", "Set your own gem-rate estimate there to weight the PSA 10 vs PSA 9 outcome while PSA pop data is unavailable."),
        ],
    },
    "1.3.2": {
        "emoji": "❌",
        "title": "Grade vs Flip now warns when to just PASS",
        "items": [
            ("❌", "New PASS verdict — when flipping raw AND grading both lose money at your buy price, the tool tells you to skip the card (or pay less) instead of flipping at a loss."),
            ("🎯", "Grade vs Flip runs on cleaned FMV numbers (not raw averages) for a truer call."),
        ],
    },
    "1.3.1": {
        "emoji": "🎯",
        "title": "Fair Market Value — true numbers, not just averages",
        "items": [
            ("🎯", "New FMV shown beside every comp average (Raw + PSA 10) — a statistically cleaned price that throws out fluke sales the plain average gets fooled by."),
            ("🔤", "Confidence grade (A/B/C) + a low–high price band on each FMV, so you know how much to trust it at a card show."),
            ("✅", "Your cost, sell price, ROI, and Grade-vs-Flip now run on FMV — falls back to the comp average automatically when FMV data is thin."),
        ],
    },
    "1.3.0": {
        "emoji": "🧰",
        "title": "Operations & Inventory — live pricing on your whole list",
        "items": [
            ("🧰", "New Operations tab (full membership) — maintain your inventory, edit costs inline, and pull live market prices across the list."),
            ("✏️", "Editable cost basis + listed price — every margin, reprice, and profit number recalculates the instant you change a cost."),
            ("⚡", "Live pricing is metered — a daily look-up budget keeps pricing fast and protects against runaway API costs. Cached cards re-price free."),
            ("🏷️", "Cleaner brand — the app is now white-labelable; set the name in one place."),
        ],
    },
    "1.2.7": {
        "emoji": "⚖️",
        "title": "Grade vs Flip — the holding-cost decision",
        "items": [
            ("⚖️", "New Grade vs Flip panel in Card Research — see what flipping raw nets you NOW vs grading and waiting ~5 months, side by side."),
            ("🎯", "Probability-weighted: blends the PSA 10 and PSA 9 outcomes by the card's gem rate into one expected-profit number, with the downside spelled out."),
            ("💸", "Holding cost made the headline — exactly how much of your cash gets locked up, for how long, and what that time costs you."),
            ("📐", "Submission Planner in Inventory Check — model a whole batch (e.g. 20 cards): total capital locked, total holding cost, grade-vs-flip totals."),
        ],
    },
    "1.2.6": {
        "emoji": "💰",
        "title": "Reprice Assistant for your inventory",
        "items": [
            ("💰", "New Reprice Assistant in Inventory Check — pulls live sold comps + 90-day trend for every card at once."),
            ("📈", "Trend-following suggested prices: leans the suggestion up when a card is rising, down when it's falling. Strategy and sensitivity are adjustable."),
            ("🚩", "Over/underpriced flags — instantly see which listings are above or below market so you reprice the ones that matter."),
            ("📥", "Download a reprice CSV to update eBay in bulk instead of editing listings one at a time."),
        ],
    },
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

# PSA current pricing & turnaround (updated May 18, 2026)
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
WP_PROXY_URL   = "https://duanefurlongstudios.com/wp-admin/admin-ajax.php?action=dfs_gemrate"

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=APP_NAME,
    page_icon="💎",
    layout="wide",
    menu_items={"About": f"{APP_NAME} — research & decision-support tool"},
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
    st.markdown(f"## 🔐 {APP_NAME} — Admin")
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
        f"""
        <div style="max-width:420px; margin:60px auto; padding:36px 28px;
                    background:#1e2130; border-radius:12px;
                    border:1px solid #2e3250; text-align:center;">
            <div style="font-size:2.2rem; margin-bottom:8px;">💎</div>
            <h2 style="margin-bottom:4px;">{APP_NAME}</h2>
            <p style="color:#aaa; font-size:0.85rem; margin-bottom:24px;">
                Enter your access code to continue.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    gc1, gc2, gc3 = st.columns([1, 2, 1])
    with gc2:
        entered_code = st.text_input("Access Code", placeholder="XXXX-XXXX", label_visibility="collapsed")
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
                    st.error("⏰ Your trial has ended. Contact us to upgrade to full access.")
                else:
                    st.error("Invalid or inactive access code.")
    st.stop()

# ─── Disclaimer gate ──────────────────────────────────────────────────────────
if not st.session_state.get("agreed"):
    st.markdown(
        f"""
        <div style="max-width:680px; margin:40px auto; padding:32px 24px;
                    background:#1e2130; border-radius:12px;
                    border:1px solid #2e3250; text-align:center;">
            <div style="font-size:2.5rem; margin-bottom:8px;">💎</div>
            <h2 style="margin-bottom:4px;">{APP_NAME}</h2>
            <p style="color:#aaa; font-size:0.85rem; margin-bottom:24px;">
                Please read and accept the disclaimer before continuing.
            </p>
            <div style="text-align:left; background:#0f1117; border-radius:8px;
                        padding:20px; margin-bottom:24px;
                        font-size:0.88rem; color:#ccc; line-height:1.7;">
                <strong style="color:#fafafa;">Disclaimer</strong><br><br>
                {APP_NAME} is a research and decision-support tool only.
                All pricing data (GemRate, eBay) is pulled from third-party sources
                and may be incomplete, delayed, or inaccurate. Gem rates and market
                values fluctuate — always verify data independently before submitting
                cards for grading.<br><br>
                All grading decisions and associated costs are <strong style="color:#fafafa;">
                solely your responsibility</strong>. {APP_NAME} assumes no liability
                for financial outcomes resulting from use of this tool.<br><br>
                <span style="font-size:0.8rem; color:#888;">
                ©️ 2026 {APP_NAME}. All rights reserved.
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

# ─── Shipment Intake Supabase helpers ─────────────────────────────────────────
def sb_intake_get():
    """Fetch all shipment intake records, newest first. Returns (rows, error_str)."""
    if not SUPABASE_URL:
        return [], "Supabase not configured"
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/shipment_intake?order=id.desc",
        headers=sb_headers(),
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return [], f"HTTP {e.code}: {body}"
    except Exception as e:
        return [], str(e)

def sb_intake_insert(row: dict):
    """Insert a new shipment intake record. Returns (result, error_str)."""
    if not SUPABASE_URL:
        return None, "Supabase not configured"
    data = json.dumps(row).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/shipment_intake",
        data=data,
        headers=sb_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return None, f"HTTP {e.code}: {body}"
    except Exception as e:
        return None, str(e)

def _json_safe(obj):
    """Recursively convert non-JSON-serializable types (date, numpy, NaT) to safe values."""
    import datetime, math
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    try:
        import numpy as np
        if isinstance(obj, (np.integer,)):  return int(obj)
        if isinstance(obj, (np.floating,)): return None if math.isnan(float(obj)) else float(obj)
        if isinstance(obj, np.bool_):       return bool(obj)
    except ImportError:
        pass
    if obj is pd.NaT:
        return None
    try:
        if isinstance(obj, float) and math.isnan(obj):
            return None
    except Exception:
        pass
    return obj

def sb_intake_update(row_id: int, updates: dict):
    """Update a shipment intake record by ID."""
    if not SUPABASE_URL:
        return
    data = json.dumps(_json_safe(updates)).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/shipment_intake?id=eq.{row_id}",
        data=data,
        headers={**sb_headers(), "Prefer": "return=minimal"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10):
            pass
    except Exception:
        pass

def sb_intake_delete(row_id: int):
    """Delete a shipment intake record by ID."""
    if not SUPABASE_URL:
        return
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/shipment_intake?id=eq.{row_id}",
        headers=sb_headers(),
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10):
            pass
    except Exception:
        pass

# ─── Live-pricing daily usage cap (protects the CardHedger API budget) ────────
# Supabase table `pricing_usage` (code text, day date, used int) persists the
# count across sessions/refreshes; falls back to session_state if it's missing.
def _today_iso():
    return date.today().isoformat()

def _pricing_key():
    return str(st.session_state.get("access_code_id") or st.session_state.get("access_name") or "anon")

def pricing_unlimited():
    """Owner + Robert (marketing partner) are never capped."""
    return st.session_state.get("access_name", "") in ("Duane", "Robert Bass")

def pricing_used_today():
    """Live look-ups already used today (max of Supabase + this session)."""
    day = _today_iso()
    sess_n = st.session_state.get("_pricing_used", {}).get(day, 0)
    if not SUPABASE_URL:
        return sess_n
    try:
        code = urllib.parse.quote(_pricing_key())
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/pricing_usage?code=eq.{code}&day=eq.{day}&select=used",
            headers=sb_headers())
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=8) as r:
            rows = json.loads(r.read().decode())
        return max(sess_n, rows[0]["used"] if rows else 0)
    except Exception:
        return sess_n

def pricing_remaining():
    if pricing_unlimited():
        return 10 ** 9
    return max(0, DAILY_PRICING_CAP - pricing_used_today())

def pricing_bump(n):
    """Record n live look-ups against today's budget (session + Supabase)."""
    if n <= 0 or pricing_unlimited():
        return
    day = _today_iso()
    sess = st.session_state.setdefault("_pricing_used", {})
    sess[day] = sess.get(day, 0) + n
    if not SUPABASE_URL:
        return
    try:
        code = _pricing_key()
        q = urllib.parse.quote(code)
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/pricing_usage?code=eq.{q}&day=eq.{day}&select=id,used",
            headers=sb_headers())
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=8) as r:
            rows = json.loads(r.read().decode())
        if rows:
            req2 = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/pricing_usage?id=eq.{rows[0]['id']}",
                data=json.dumps({"used": rows[0]["used"] + n}).encode(),
                headers={**sb_headers(), "Prefer": "return=minimal"}, method="PATCH")
        else:
            req2 = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/pricing_usage",
                data=json.dumps({"code": code, "day": day, "used": n}).encode(),
                headers={**sb_headers(), "Prefer": "return=minimal"}, method="POST")
        urllib.request.urlopen(req2, context=ssl_ctx(), timeout=8)
    except Exception:
        pass

# ─── GemRate API ──────────────────────────────────────────────────────────────
def _gemrate_single(query: str):
    payload = json.dumps({"query": query, "limit": 10}).encode()
    browser_hdrs = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }

    # Route through WordPress proxy first (avoids Cloudflare IP block on Streamlit Cloud)
    try:
        req = urllib.request.Request(WP_PROXY_URL, data=payload, headers=browser_hdrs, method="POST")
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as r:
            result = json.loads(r.read().decode())
            if isinstance(result, list) and result:
                return result
    except Exception:
        pass

    # Direct fallback (works locally, may be blocked on cloud)
    try:
        req = urllib.request.Request(
            "https://www.gemrate.com/universal-search-query",
            data=payload, headers=browser_hdrs, method="POST",
        )
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as r:
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

@st.cache_data(ttl=1800, show_spinner=False)
def ch_fmv(card_id, grade: str):
    """Fair Market Value — statistically cleaned price (Winsorized median) with a
    confidence grade and a low–high band. More reliable than the raw comp average.
    Returns {} if unavailable."""
    return _ch_post("/v1/cards/card-fmv", {
        "card_id": card_id, "grade": grade,
    }) or {}

def fmv_price(d):
    """Pull a usable price out of an FMV dict, else None."""
    try:
        v = float(d.get("price"))
        return v if v > 0 else None
    except Exception:
        return None

def fmv_caption(d):
    """One-line FMV display: '🎯 FMV $X  ($low–$high, conf A)' or '' if no price."""
    p = fmv_price(d)
    if not p:
        return ""
    lo, hi = d.get("price_low"), d.get("price_high")
    grade = d.get("confidence_grade") or ""
    band = ""
    try:
        if lo and hi:
            band = f" (${float(lo):,.0f}–${float(hi):,.0f}"
            band += f", conf {grade})" if grade else ")"
    except Exception:
        band = f" (conf {grade})" if grade else ""
    return f"🎯 **FMV ${p:,.2f}**{band}"

def fmv_band_conf(d):
    """'🎯 FMV · $lo–$hi · conf A' for use under a metric already showing the FMV price."""
    if not fmv_price(d):
        return ""
    lo, hi = d.get("price_low"), d.get("price_high")
    grade = d.get("confidence_grade") or ""
    parts = []
    try:
        if lo and hi:
            parts.append(f"${float(lo):,.0f}–${float(hi):,.0f}")
    except Exception:
        pass
    if grade:
        parts.append(f"conf {grade}")
    return "🎯 FMV · " + " · ".join(parts) if parts else "🎯 FMV"

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

@st.cache_data(ttl=1800, show_spinner=False)
def ch_card_meta(card_id):
    """card-details for one card — includes '7 Day Sales' / '30 Day Sales' volume."""
    result = _ch_post("/v1/cards/card-details", {"card_id": card_id})
    cards = (result or {}).get("cards") or []
    return cards[0] if cards else (result or {})

def _ch_get(endpoint: str):
    """GET against CardHedger (top-movers is GET, not POST)."""
    if not CARDHEDGER_KEY:
        return None
    req = urllib.request.Request(f"{CARDHEDGER_BASE}{endpoint}",
                                 headers={"X-API-Key": CARDHEDGER_KEY})
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

@st.cache_data(ttl=900, show_spinner=False)
def ch_top_movers(category=None, count=25):
    """Weekly biggest price gainers (optionally filtered to a sport category)."""
    q = f"/v1/cards/top-movers?count={int(count)}"
    if category:
        q += f"&category={urllib.parse.quote(category)}"
    d = _ch_get(q) or {}
    return d.get("cards", []) if isinstance(d, dict) else []

@st.cache_data(ttl=1800, show_spinner=False)
def ch_all_prices(card_id):
    """Latest price for EVERY grade in one call (Raw..PSA 10). Cheaper than N comps calls."""
    d = _ch_post("/v1/cards/all-prices-by-card", {"card_id": card_id}) or {}
    return d.get("prices", []) if isinstance(d, dict) else []

@st.cache_data(ttl=1800, show_spinner=False)
def ch_sales_stats(player, interval="week", periods=8):
    """Player sales volume + $ per period → demand trend. Returns list of buckets."""
    d = _ch_post("/v1/cards/sales-stats-by-player",
                 {"players": [player], "interval": interval, "periods": periods}) or {}
    res = d.get("results", []) if isinstance(d, dict) else []
    return (res[0].get("buckets", []) if res else [])

@st.cache_data(ttl=900, show_spinner=False)
def ch_image_match(image_b64):
    """Identify a raw card from a photo (base64). Returns dict with candidates[]."""
    return _ch_post("/v1/cards/image-match", {"image_base64": image_b64}) or {}

@st.cache_data(ttl=1800, show_spinner=False)
def ch_prices_by_cert(cert, grader="PSA", days=180):
    """Look up a graded card by its cert number → cert_info + card + price history."""
    return _ch_post("/v1/cards/prices-by-cert",
                    {"cert": str(cert), "grader": grader, "days": int(days)}) or {}

# ── Cross-platform reconciliation (CollX ↔ eBay) ─────────────────────────────
def _rec_num(x):
    try:
        return float(str(x).replace("$", "").replace(",", "").strip() or 0) or None
    except Exception:
        return None

def _rec_norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())

def _rec_numpart(n):
    m = re.search(r"\d+", n or "")
    return m.group() if m else None

def _rec_header_row(rows, needle):
    """eBay reports sometimes have a preamble row — find the real header."""
    for i, r in enumerate(rows[:8]):
        if any(needle in (c or "").lower() for c in r):
            return i
    return 0

def parse_collx_csv(text):
    return list(csv.DictReader(io.StringIO(text)))

def parse_ebay_sold_csv(text):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    hi = _rec_header_row(rows, "item title")
    col = {c: j for j, c in enumerate(rows[hi])}
    def g(r, name):
        j = col.get(name)
        return r[j] if (j is not None and j < len(r)) else ""
    out = []
    for r in rows[hi + 1:]:
        t = g(r, "Item Title").strip()
        if not t:
            continue
        out.append({"title": t, "sold_for": g(r, "Sold For"),
                    "date": g(r, "Sale Date"), "item_number": g(r, "Item Number")})
    return out

def parse_ebay_active_csv(text):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    hi = _rec_header_row(rows, "item number")
    col = {c: j for j, c in enumerate(rows[hi])}
    def g(r, name):
        j = col.get(name)
        return r[j] if (j is not None and j < len(r)) else ""
    out = []
    for r in rows[hi + 1:]:
        t = g(r, "Title").strip()
        itemno = g(r, "Item number").strip()
        if not t or not itemno:
            continue
        out.append({"title": t, "item_number": itemno,
                    "sku": g(r, "Custom label (SKU)"), "price": g(r, "Current price")})
    return out

def match_collx_to_ebay(collx_rows, ebay_items):
    """Join each CollX card to its best eBay item by name+year+number.
    Returns list of (collx_card, confidence, ebay_item)."""
    idx = collections.defaultdict(list)
    prepped = []
    for e in ebay_items:
        t = _rec_norm(e.get("title", ""))
        ts = set(t.split())
        prepped.append((t, ts, e))
        for w in ts:
            if len(w) > 2:
                idx[w].append(len(prepped) - 1)
    out = []
    for c in collx_rows:
        parts = _rec_norm(c.get("name", "")).split()
        if not parts:
            continue
        last = parts[-1]
        year = (c.get("year", "") or "").strip()
        yr2 = year[-2:] if len(year) >= 2 else year
        numv = _rec_numpart(c.get("number", ""))
        best = None
        for i in set(idx.get(last, [])):
            t, ts, e = prepped[i]
            if last not in ts:
                continue
            year_ok = (year and year in t) or (yr2 and yr2 in ts)
            num_ok = (numv in ts) if numv else False
            first_ok = parts[0] in ts if len(parts) > 1 else True
            if year_ok and num_ok and first_ok:
                conf = "High"
            elif year_ok and num_ok:
                conf = "Medium"
            elif year_ok and first_ok:
                conf = "Low"
            else:
                continue
            best = (conf, e)
            if conf == "High":
                break
        if best:
            out.append((c, best[0], best[1]))
    return out

def ebay_end_file(item_numbers):
    """eBay File Exchange 'End Listings' CSV text for bulk-ending listings."""
    lines = ["Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8),ItemID,EndCode"]
    for n in item_numbers:
        lines.append(f"End,{n},NotAvailable")
    return "\n".join(lines) + "\n"

def render_price_trend(card_id, key_prefix="pt", default_grade="PSA 10"):
    """Sold-price line chart with 7/30/60/90-day windows + sales-volume context.

    CardHedger only has SOLD data (no active-listing counts), so 'how many are
    for sale' is shown as n/a on purpose rather than faked.
    """
    if not card_id:
        return
    st.markdown("#### 📈 Sold Price Trend")
    gsel, wsel = st.columns([1, 2])
    grades = ["PSA 10", "PSA 9", "Raw"]
    gi = grades.index(default_grade) if default_grade in grades else 0
    grade_sel = gsel.selectbox("Grade", grades, index=gi, key=f"{key_prefix}_grade")
    window = wsel.radio("Window", ["7d", "30d", "60d", "90d"], index=3,
                        horizontal=True, key=f"{key_prefix}_win")
    days_map = {"7d": 7, "30d": 30, "60d": 60, "90d": 90}

    hist = ch_price_history(card_id, grade_sel, days=90)
    pts = hist.get("prices") if isinstance(hist, dict) else hist
    rows = []
    for p in (pts or []):
        try:
            dt = (p.get("closing_date") or p.get("date") or "")[:10]
            val = float(p.get("price"))
            if dt and val > 0:
                rows.append((dt, val))
        except Exception:
            pass
    if not rows:
        st.info(f"No sold-price history for {grade_sel} on this card.")
        return
    df = pd.DataFrame(rows, columns=["date", "price"]).drop_duplicates("date")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    latest = df["price"].iloc[-1]

    def _pct(days):
        cutoff = df["date"].max() - pd.Timedelta(days=days)
        win = df[df["date"] >= cutoff]
        if len(win) < 2:
            return None
        a = win["price"].iloc[0]
        return ((win["price"].iloc[-1] - a) / a * 100) if a else None

    st.metric(f"{grade_sel} — latest sold", f"${latest:,.2f}")
    cc = st.columns(4)
    for col, w in zip(cc, ["7d", "30d", "60d", "90d"]):
        pct = _pct(days_map[w])
        if pct is None:
            col.metric(f"Δ {w}", "—")
        else:
            arrow = "📈" if pct > 1 else "📉" if pct < -1 else "➡️"
            col.metric(f"Δ {w}", f"{pct:+.1f}% {arrow}")

    cutoff = df["date"].max() - pd.Timedelta(days=days_map[window])
    dfw = df[df["date"] >= cutoff].set_index("date")
    st.line_chart(dfw["price"], height=240)
    st.caption(
        f"Each point = a daily sold price (CardHedger). Showing last {window}. "
        "Short windows show momentum; 90d shows the longer-term trend."
    )

    meta = ch_card_meta(card_id)
    s7, s30 = meta.get("7 Day Sales"), meta.get("30 Day Sales")
    vc1, vc2, vc3 = st.columns(3)
    vc1.metric("🔁 Sales · 7 days", f"{int(s7):,}" if isinstance(s7, (int, float)) else "—",
               help="How many of this card sold in the last 7 days. Higher = more liquid, easier to sell.")
    vc2.metric("🔁 Sales · 30 days", f"{int(s30):,}" if isinstance(s30, (int, float)) else "—",
               help="30-day sales volume — a fuller read on demand.")
    vc3.metric("🛒 Active for sale", "n/a",
               help="CardHedger tracks SOLD sales only, not live listings — 'how many are for sale right now' isn't available from this API.")

# ── ESPN free player news + injuries (no API key) ────────────────────────────
ESPN_SPORT = {
    "Baseball":   ("baseball", "mlb"),
    "Basketball": ("basketball", "nba"),
    "Football":   ("football", "nfl"),
    "Hockey":     ("hockey", "nhl"),
}
_ESPN_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def _espn_get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _ESPN_UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

@st.cache_data(ttl=1800, show_spinner=False)
def espn_injuries_map(sport, league):
    """Whole-league injury report → {player_name_lower: {status,type,comment,team}}."""
    d = _espn_get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/injuries")
    out = {}
    for team in (d or {}).get("injuries", []):
        for inj in team.get("injuries", []):
            nm = ((inj.get("athlete") or {}).get("displayName") or "").strip().lower()
            if not nm:
                continue
            typ = inj.get("type")
            typ = typ.get("description") if isinstance(typ, dict) else typ
            out[nm] = {
                "status":  inj.get("status") or "",
                "type":    typ or "",
                "comment": inj.get("shortComment") or inj.get("longComment") or "",
                "team":    team.get("displayName", ""),
            }
    return out

@st.cache_data(ttl=900, show_spinner=False)
def espn_player_news(player, limit=4):
    """Recent ESPN articles matching a player name → [{title,url,date}]."""
    if not player:
        return []
    d = _espn_get(f"https://site.web.api.espn.com/apis/search/v2?query={urllib.parse.quote(player)}&limit={limit}")
    out = []
    for g in (d or {}).get("results", []):
        if g.get("type") == "article":
            for it in g.get("contents", []):
                title = it.get("displayName") or ""
                link = (it.get("link") or {}).get("web") if isinstance(it.get("link"), dict) else ""
                if title and link:
                    out.append({"title": title, "url": link, "date": (it.get("date") or "")[:10]})
            break
    # Prefer headlines that actually name the player (drops generic league noise).
    last = player.lower().split()[-1] if player else ""
    preferred = [a for a in out if last and last in a["title"].lower()]
    return (preferred or out)[:limit]

def render_player_watch(card_id, key_prefix="pw"):
    """News + injury status for the card's player, via the free ESPN feeds."""
    meta = ch_card_meta(card_id) if card_id else {}
    player = (meta.get("player") or "").strip()
    if not player:
        return
    category = meta.get("category") or ""
    st.markdown("#### 📰 Player Watch — news & injury")

    sport = ESPN_SPORT.get(category.title())
    injury = None
    if sport:
        inj_map = espn_injuries_map(*sport)
        injury = inj_map.get(player.lower())
        if not injury and " " in player:            # last-name fallback
            last = player.lower().split()[-1]
            for nm, v in inj_map.items():
                if nm.split()[-1] == last:
                    injury = v
                    break
    if injury:
        msg = f"🔴 **{player} — {injury['status']}**"
        if injury["type"]:
            msg += f" · {injury['type']}"
        if injury["comment"]:
            msg += f"  \n{injury['comment']}"
        st.error(msg)
    elif sport:
        st.success(f"🟢 {player} — not on the {sport[1].upper()} injury report right now.")

    news = espn_player_news(player)
    if news:
        for n in news:
            line = f"- [{n['title']}]({n['url']})"
            if n["date"]:
                line += f" · _{n['date']}_"
            st.markdown(line)
    else:
        srch = urllib.parse.quote(player)
        st.caption(f"No recent ESPN articles matched **{player}** (common for prospects). "
                   f"[Search ESPN ↗](https://www.espn.com/search/_/q/{srch})")
    st.caption("⚡ News & injuries move card prices before the comps do. Source: ESPN (free).")

def render_player_demand(card_id, key_prefix="pd"):
    """Weekly sold-volume trend across ALL of a player's cards — a demand signal."""
    meta = ch_card_meta(card_id) if card_id else {}
    player = (meta.get("player") or "").strip()
    if not player:
        return
    buckets = ch_sales_stats(player, interval="week", periods=8)
    rows = []
    for b in buckets:
        wk = (b.get("start") or "")[:10]
        try:
            rows.append({"week": wk, "sales": int(b.get("count") or 0),
                         "avg": float(b.get("average_sale") or 0)})
        except Exception:
            pass
    if len(rows) < 2:
        return
    df = pd.DataFrame(rows).sort_values("week")
    st.markdown(f"#### 📊 Player Demand — {player} (all cards)")
    st.bar_chart(df.set_index("week")["sales"], height=200)

    # Demand direction: recent half vs older half of the weekly sales counts.
    vals = df["sales"].tolist()
    mid = len(vals) // 2
    older = sum(vals[:mid]) / max(mid, 1)
    recent = sum(vals[mid:]) / max(len(vals) - mid, 1)
    pct = ((recent - older) / older * 100) if older else 0
    arrow = "📈 rising" if pct > 10 else "📉 cooling" if pct < -10 else "➡️ steady"
    m1, m2, m3 = st.columns(3)
    m1.metric("Latest week — sales", f"{vals[-1]:,}")
    m2.metric("Avg sale (latest wk)", f"${df['avg'].iloc[-1]:,.0f}")
    m3.metric("Demand trend", arrow, f"{pct:+.0f}%")
    st.caption(
        f"Weekly count of ALL {player} cards sold across marketplaces (CardHedger). "
        "Rising volume = growing demand/attention — a leading signal for where prices head."
    )

def safe_image_url(u):
    """Return a fetchable http(s) URL (normalizing protocol-relative), else None.

    st.image crashes the whole app if handed a non-URL string (it tries to open
    it as a local file → MediaFileStorageError), so anything that isn't a real
    web URL must be filtered out before it reaches st.image.
    """
    if not isinstance(u, str):
        return None
    u = u.strip()
    if u.startswith("//"):
        u = "https:" + u
    return u if u.lower().startswith(("http://", "https://")) else None

def render_card_image(url, placeholder=True, **kwargs):
    """Safely render a card image. Returns True if shown, False if not (bad/missing URL)."""
    url = safe_image_url(url)
    if url:
        try:
            st.image(url, **kwargs)
            return True
        except Exception:
            pass
    if placeholder:
        st.markdown(
            '<div style="background:#1e2130;border:1px solid #2e3250;border-radius:10px;'
            'height:180px;display:flex;align-items:center;justify-content:center;'
            'color:#4a5568;font-size:2rem;">🃏</div>',
            unsafe_allow_html=True,
        )
    return False

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

# ─── Grade-vs-Flip decision logic (the holding-cost engine) ───────────────────
def hold_cost(capital, cal_days, opp_rate):
    """Opportunity cost of `capital` locked up for cal_days at opp_rate %/yr."""
    if opp_rate <= 0 or capital <= 0:
        return 0.0
    return capital * (opp_rate / 100.0) * (cal_days / 365.0)

def flip_raw_net(raw_comp, raw_buy):
    """Net from selling the card raw right now (after eBay fees)."""
    if not raw_comp:
        return None
    return raw_comp * (1 - EBAY_FEE) - raw_buy

def grade_sale_net(sale_price, raw_buy, fee, ship, hold):
    """Net from grading then selling at sale_price, after every cost incl. holding."""
    if not sale_price:
        return None
    return sale_price * (1 - EBAY_FEE) - (raw_buy + fee + ship + hold)

def expected_graded_sale(gem_rate, psa10, psa9):
    """Gem-rate-weighted expected graded sale: P(10)*PSA10 + (1-P(10))*PSA9."""
    if psa10 is None and psa9 is None:
        return None
    p10 = max(0.0, min(1.0, (gem_rate or 0) / 100.0))
    s10 = psa10 if psa10 is not None else psa9
    s9 = psa9 if psa9 is not None else psa10
    return p10 * s10 + (1 - p10) * s9

def grade_vs_flip(raw_buy, raw_comp, psa10, psa9, gem_rate, tier, ship, opp_rate):
    """Full grade-vs-flip economics for one card. Returns a dict of outcomes."""
    fee = PSA_FEES.get(tier, 50)
    cal_days = int(PSA_DAYS.get(tier, 60) * 1.4)
    capital = raw_buy + fee + ship
    hold = round(hold_cost(capital, cal_days, opp_rate), 2)
    raw_net = flip_raw_net(raw_comp, raw_buy)
    net10 = grade_sale_net(psa10, raw_buy, fee, ship, hold)
    net9 = grade_sale_net(psa9, raw_buy, fee, ship, hold)
    exp_sale = expected_graded_sale(gem_rate, psa10, psa9)
    net_exp = grade_sale_net(exp_sale, raw_buy, fee, ship, hold)
    premium = (net_exp - raw_net) if (net_exp is not None and raw_net is not None) else None
    return {
        "fee": fee, "cal_days": cal_days, "capital": capital, "hold": hold,
        "raw_net": raw_net, "net10": net10, "net9": net9,
        "exp_sale": exp_sale, "net_exp": net_exp, "premium": premium,
        "p10": max(0.0, min(1.0, (gem_rate or 0) / 100.0)),
    }

def grade_flip_verdict(d):
    """Return (label, color, message) recommending grade vs flip for one card."""
    net_exp, raw_net, net9 = d["net_exp"], d["raw_net"], d["net9"]
    if net_exp is None:
        return "ℹ️ Need comps", "info", "Not enough comp data to compare — enter prices manually."
    downside = ""
    if net9 is not None and net9 < 0:
        downside = f" ⚠️ Downside: a PSA 9 nets **−${abs(net9):,.0f}** (a loss)."
    if raw_net is None:
        if net_exp > 0:
            return "✅ GRADE", "green", f"Expected net **${net_exp:,.0f}** after the ${d['hold']:,.0f} holding cost.{downside}"
        return "❌ SKIP", "red", f"Expected net only **${net_exp:,.0f}** — not worth grading.{downside}"
    if net_exp > raw_net and net_exp > 0:
        return "✅ GRADE", "green", (
            f"Expected **${net_exp:,.0f}** vs **${raw_net:,.0f}** flipping raw — "
            f"**+${d['premium']:,.0f}** for the ~{d['cal_days']}-day wait (after ${d['hold']:,.0f} holding cost).{downside}"
        )
    # Neither path makes money at this buy price → don't buy it.
    if raw_net <= 0 and net_exp <= 0:
        return "❌ PASS", "red", (
            f"Both paths lose at this cost: flipping raw nets **${raw_net:,.0f}**, "
            f"grading's expected is **${net_exp:,.0f}**. Skip it (or pay less).{downside}"
        )
    return "💵 FLIP RAW", "amber", (
        f"Flipping raw nets **${raw_net:,.0f}** now; grading's expected **${net_exp:,.0f}** "
        f"isn't worth locking **${d['capital']:,.0f}** for ~{d['cal_days']} days.{downside}"
    )

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
    st.markdown(f"## 💎 {APP_NAME}")
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
    st.markdown("**Grading fees (updated May 18, 2026)**")
    for tier, info in PSA_FEES_ALL.items():
        biz = info['days']
        st.caption(f"${info['fee']:.2f} · ~{biz} biz days · insured to ${info['max_insured']:,} — {tier.split('(')[0].strip()}")
    st.caption(f"eBay sell fee: {EBAY_FEE*100:.2f}%")

# ─── What's New dialog ────────────────────────────────────────────────────────
_WN_KEY = f"wn_seen_{APP_VERSION}"

@st.dialog(f"🎉 What's New in {APP_NAME}", width="large")
def _show_whats_new():
    # Mark as seen immediately — so closing via X doesn't re-trigger on next rerun
    st.session_state[_WN_KEY] = True
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

tab1, tab7, tab8, tab2, tab6, tab3, tab4, tab5, tab9, tab10 = st.tabs(["🔍 Card Research", "🔥 Hot Movers", "📷 Scan", "📦 Inventory Check", "🧰 Operations", "📬 Submission Tracker", "📥 Downloads", "🚚 Shipment Intake", "🏷️ Consignments", "💰 Sales & P&L"])

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
        gr_image_url = safe_image_url(gr_image_url)

        if gr_image_url:
            img_c, stats_c = st.columns([1, 3])
            with img_c:
                render_card_image(gr_image_url, use_container_width=True)
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
        ch_psa9_avg = None
        ch_trend_dir = None
        ch_trend_pct = 0.0
        ch_raw_sales = []
        ch_psa10_sales = []
        ch_card_name = ""
        ch_id = None
        ch_raw_fmv = {}
        ch_psa10_fmv = {}
        ch_psa9_fmv = {}

        if CARDHEDGER_KEY:
            with st.spinner("Fetching live sold comps, FMV & trend data..."):
                ch_matches = ch_search(desc)
                if ch_matches:
                    ch_card = ch_matches[0]
                    ch_id = ch_card.get("card_id") or ch_card.get("id")
                    ch_card_name = ch_card.get("name") or ch_card.get("title") or ""
                    if ch_id:
                        raw_data  = ch_comps(ch_id, "Raw")
                        psa_data  = ch_comps(ch_id, "PSA 10")
                        psa9_data = ch_comps(ch_id, "PSA 9")
                        ch_raw_fmv   = ch_fmv(ch_id, "Raw")
                        ch_psa10_fmv = ch_fmv(ch_id, "PSA 10")
                        ch_psa9_fmv  = ch_fmv(ch_id, "PSA 9")
                        ch_raw_avg   = raw_data.get("comp_price") or raw_data.get("average") or raw_data.get("mean")
                        ch_psa10_avg = psa_data.get("comp_price") or psa_data.get("average") or psa_data.get("mean")
                        ch_psa9_avg  = psa9_data.get("comp_price") or psa9_data.get("average") or psa9_data.get("mean")
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
                    _rf = fmv_caption(ch_raw_fmv)
                    if _rf:
                        st.markdown(_rf)
                    elif not ch_raw_avg and not ch_raw_sales:
                        st.info("No raw comps found")
                with fc2:
                    st.markdown("**💎 PSA 10 — recent sold comps**")
                    if ch_psa10_sales:
                        rows_g = [r for s in ch_psa10_sales[:15] if (r := _fmt_sale_row(s))]
                        if rows_g:
                            st.dataframe(pd.DataFrame(rows_g), use_container_width=True, hide_index=True, height=200)
                    if ch_psa10_avg:
                        st.markdown(f"**Comp avg: ${ch_psa10_avg:,.2f}**")
                    _gf = fmv_caption(ch_psa10_fmv)
                    if _gf:
                        st.markdown(_gf)
                    elif not ch_psa10_avg and not ch_psa10_sales:
                        st.info("No PSA 10 comps found")
            if ch_raw_sales or ch_psa10_sales:
                st.caption("⚠️ Comp avg includes all sale types. 🏷 BIN = fixed price (most reliable). 💬 Offer = accepted below ask. 🔨 Auction = bidding (use with caution).")
                st.caption("🎯 **FMV** = Fair Market Value: a statistically cleaned price (Winsorized median, recent sales) with a confidence grade (A best). More reliable than the comp avg — drives the cost/sell pre-fills below.")
            elif CARDHEDGER_KEY:
                st.info("No CardHedger match found for this card — enter prices manually below.")
        else:
            st.info("📊 Live sold comps will appear here once the CardHedger API is connected.")

        # Prefer cleaned FMV for pre-fills; fall back to the comp average.
        raw_auto    = fmv_price(ch_raw_fmv)   or ch_raw_avg
        graded_auto = fmv_price(ch_psa10_fmv) or ch_psa10_avg

        ra1, ra2, ra3 = st.columns(3)
        with ra1:
            raw_cost = st.number_input(
                "Your cost for the raw card ($)", min_value=0.0,
                value=float(raw_auto) if raw_auto else 50.0,
                step=5.0, key="t1_raw",
            )
            st.caption("What you paid (or plan to pay) for the ungraded card. Pre-filled from raw FMV (cleaned) — update to your actual price.")
        with ra2:
            tier = default_tier
            st.caption(f"**Grading tier:** {tier} (${PSA_FEES[tier]:.2f}) — change in sidebar ⚙️")
        with ra3:
            graded_price = st.number_input(
                "Expected PSA 10 sell price ($)", min_value=0.0,
                value=float(graded_auto) if graded_auto else 0.0,
                step=10.0, key="t1_graded",
            )
            st.caption("The price you expect to sell a PSA 10 for on eBay. Pre-filled from PSA 10 FMV (cleaned) — adjust up or down based on your read of the market.")

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

        # ── ⚖️ Grade vs Flip — the holding-cost decision ──────────────────────
        if CARDHEDGER_KEY and raw_cost > 0 and (ch_raw_avg or ch_psa10_avg or ch_psa9_avg):
            st.markdown("#### ⚖️ Grade vs Flip — the real decision")
            st.caption(
                "Grading locks up your cash for months. Here's what each path actually nets — "
                "weighted by this card's gem rate — so you decide with eyes open, not just \"I can 4× it.\""
            )
            # Use cleaned FMV where available, fall back to the comp average.
            gvf_raw   = fmv_price(ch_raw_fmv)   or ch_raw_avg
            gvf_psa10 = fmv_price(ch_psa10_fmv) or ch_psa10_avg
            gvf_psa9  = fmv_price(ch_psa9_fmv)  or ch_psa9_avg
            gvf = grade_vs_flip(raw_cost, gvf_raw, gvf_psa10, gvf_psa9, gem, tier, ship_cost, opp_rate)

            d1, d2, d3 = st.columns(3)
            with d1:
                st.markdown("**💵 Flip Raw Now**")
                st.metric("Sell ~", f"${gvf_raw:,.0f}" if gvf_raw else "—", help="Raw FMV (cleaned) — or sold-comp average if FMV unavailable")
                st.metric("Net profit", f"${gvf['raw_net']:,.0f}" if gvf['raw_net'] is not None else "—",
                          help="After eBay fees + your buy cost. Cash back in ~3-7 days, nothing locked up.")
            with d2:
                st.markdown("**💎 Grade → PSA 10**")
                st.metric("Sell ~", f"${gvf_psa10:,.0f}" if gvf_psa10 else "—")
                st.metric("Net profit", f"${gvf['net10']:,.0f}" if gvf['net10'] is not None else "—",
                          help=f"After grading, shipping, eBay fees, and ${gvf['hold']:,.0f} holding cost.")
            with d3:
                st.markdown("**🥈 Grade → PSA 9**")
                st.metric("Sell ~", f"${gvf_psa9:,.0f}" if gvf_psa9 else "—")
                st.metric("Net profit", f"${gvf['net9']:,.0f}" if gvf['net9'] is not None else "—",
                          help="The downside if it doesn't gem — same costs, lower sale.")

            ev1, ev2, ev3 = st.columns(3)
            ev1.metric(f"🎯 Expected net (gem {fmt_gem(gem)})",
                       f"${gvf['net_exp']:,.0f}" if gvf['net_exp'] is not None else "—",
                       help=f"Gem-rate-weighted: {gvf['p10']*100:.0f}% chance of a 10, {(1-gvf['p10'])*100:.0f}% a 9. After all costs incl. holding.")
            ev2.metric("💸 Holding cost", f"${gvf['hold']:,.0f}",
                       help=f"${gvf['capital']:,.0f} of your cash locked ~{gvf['cal_days']} days at {opp_rate:.0f}%/yr")
            if gvf['premium'] is not None:
                ev3.metric("Grade premium vs raw",
                           f"{'+' if gvf['premium'] >= 0 else '−'}${abs(gvf['premium']):,.0f}",
                           help="Expected graded net minus flip-raw net — your reward for the wait.")

            _lbl, _clr, _msg = grade_flip_verdict(gvf)
            (st.success if _clr == "green" else st.warning if _clr == "amber"
             else st.error if _clr == "red" else st.info)(f"**{_lbl}** — {_msg}")

            st.caption(
                f"⏳ Grading this card ties up **${gvf['capital']:,.0f}** "
                f"(buy ${raw_cost:,.0f} + fee ${gvf['fee']:.0f}"
                + (f" + ship ${ship_cost:.0f}" if ship_cost else "")
                + f") for ~**{gvf['cal_days']} days** (~{gvf['cal_days']/30:.1f} months). Flipping raw frees that cash now."
            )

        if CARDHEDGER_KEY and ch_id:
            render_price_trend(ch_id, key_prefix="main")
            render_player_watch(ch_id, key_prefix="main")
            render_player_demand(ch_id, key_prefix="main")

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

        # Cleaned FMV per grade (more reliable than the plain avg); falls back to avg.
        _cid = ch_match_data.get("card_id")
        fb_raw_fmv   = ch_fmv(_cid, "Raw")    if _cid else {}
        fb_psa10_fmv = ch_fmv(_cid, "PSA 10") if _cid else {}
        fb_psa9_fmv  = ch_fmv(_cid, "PSA 9")  if _cid else {}
        raw_val   = fmv_price(fb_raw_fmv)   or ch_raw
        psa10_val = fmv_price(fb_psa10_fmv) or ch_psa10
        psa9_val  = fmv_price(fb_psa9_fmv)  or ch_psa9

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
            render_card_image(image_url, use_container_width=True)
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
        if psa10_val:
            fb2.metric("PSA 10", f"${psa10_val:,.2f}")
            _c10 = fmv_band_conf(fb_psa10_fmv)
            if _c10:
                fb2.caption(_c10)
        if psa9_val:
            fb3.metric("PSA 9", f"${psa9_val:,.2f}")
            _c9 = fmv_band_conf(fb_psa9_fmv)
            if _c9:
                fb3.caption(_c9)
        if fmv_price(fb_raw_fmv) or fmv_price(fb_psa10_fmv):
            st.caption("🎯 Showing FMV (cleaned value) where available, else the CardHedger average. Confidence A = best.")

        st.markdown("#### ROI Analysis")

        ra1, ra2, ra3 = st.columns(3)
        with ra1:
            raw_cost = st.number_input(
                "Your cost for the raw card ($)", min_value=0.0,
                value=float(raw_val) if raw_val else 50.0,
                step=5.0, key="t1_raw",
            )
            st.caption("Pre-filled from raw FMV (cleaned) — update to your actual price.")
        with ra2:
            tier = default_tier
            st.caption(f"**Grading tier:** {tier} (${PSA_FEES[tier]:.2f}) — change in sidebar ⚙️")
        with ra3:
            graded_price = st.number_input(
                "Expected PSA 10 sell price ($)", min_value=0.0,
                value=float(psa10_val) if psa10_val else 0.0,
                step=10.0, key="t1_graded",
            )
            st.caption("Pre-filled from PSA 10 FMV (cleaned) — adjust as needed.")

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

        # ── ⚖️ Grade vs Flip (works even with GemRate offline) ────────────────
        if raw_cost > 0 and (raw_val or psa10_val or psa9_val):
            st.markdown("#### ⚖️ Grade vs Flip — the real decision")
            st.caption(
                "Grading locks up your cash for months. Here's what each path nets. "
                "GemRate is offline, so set your own gem-rate estimate below to weight the PSA 10 vs PSA 9 outcome."
            )
            gem_fb = st.slider(
                "Estimated gem rate % (your best guess — PSA pop is offline)",
                0, 100, 50, 5, key="fb_gem",
                help="How often you think this card grades a PSA 10. 50% is a neutral default.",
            )
            gvf = grade_vs_flip(raw_cost, raw_val, psa10_val, psa9_val, gem_fb, tier, ship_cost, opp_rate)
            d1, d2, d3 = st.columns(3)
            with d1:
                st.markdown("**💵 Flip Raw Now**")
                st.metric("Sell ~", f"${raw_val:,.0f}" if raw_val else "—", help="Raw FMV (cleaned)")
                st.metric("Net profit", f"${gvf['raw_net']:,.0f}" if gvf['raw_net'] is not None else "—",
                          help="After eBay fees + your buy cost. Cash back in days, nothing locked up.")
            with d2:
                st.markdown("**💎 Grade → PSA 10**")
                st.metric("Sell ~", f"${psa10_val:,.0f}" if psa10_val else "—")
                st.metric("Net profit", f"${gvf['net10']:,.0f}" if gvf['net10'] is not None else "—",
                          help=f"After grading, shipping, eBay fees, and ${gvf['hold']:,.0f} holding cost.")
            with d3:
                st.markdown("**🥈 Grade → PSA 9**")
                st.metric("Sell ~", f"${psa9_val:,.0f}" if psa9_val else "—")
                st.metric("Net profit", f"${gvf['net9']:,.0f}" if gvf['net9'] is not None else "—",
                          help="The downside if it doesn't gem — same costs, lower sale.")
            ev1, ev2, ev3 = st.columns(3)
            ev1.metric(f"🎯 Expected net (gem {gem_fb}%)",
                       f"${gvf['net_exp']:,.0f}" if gvf['net_exp'] is not None else "—",
                       help="Gem-rate-weighted expected profit after all costs incl. holding.")
            ev2.metric("💸 Holding cost", f"${gvf['hold']:,.0f}",
                       help=f"${gvf['capital']:,.0f} of cash locked ~{gvf['cal_days']} days at {opp_rate:.0f}%/yr")
            if gvf['premium'] is not None:
                ev3.metric("Grade premium vs raw",
                           f"{'+' if gvf['premium'] >= 0 else '−'}${abs(gvf['premium']):,.0f}",
                           help="Expected graded net minus flip-raw net — your reward for the wait.")
            _lbl, _clr, _msg = grade_flip_verdict(gvf)
            (st.success if _clr == "green" else st.warning if _clr == "amber"
             else st.error if _clr == "red" else st.info)(f"**{_lbl}** — {_msg}")
            st.caption(
                f"⏳ Grading ties up **${gvf['capital']:,.0f}** for ~**{gvf['cal_days']} days** "
                f"(~{gvf['cal_days']/30:.1f} months). Flipping raw frees that cash now."
            )

        render_price_trend(_cid, key_prefix="fb")
        render_player_watch(_cid, key_prefix="fb")
        render_player_demand(_cid, key_prefix="fb")

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

# ─── Reprice Assistant helpers ────────────────────────────────────────────────
def detect_grade(desc):
    """Infer the grade to price against from the card description. Defaults to Raw."""
    d = (desc or "").upper()
    if "PSA 10" in d or "GEM MINT 10" in d or "GEM MT 10" in d: return "PSA 10"
    if "PSA 9.5" in d: return "PSA 9.5"
    if "PSA 9"  in d: return "PSA 9"
    if "PSA 8.5" in d: return "PSA 8.5"
    if "PSA 8"  in d: return "PSA 8"
    if "PSA 7"  in d: return "PSA 7"
    if "PSA 6"  in d: return "PSA 6"
    if "PSA 5"  in d: return "PSA 5"
    if "BGS 10" in d or "BGS PRISTINE" in d: return "BGS 10"
    if "BGS 9.5" in d: return "BGS 9.5"
    if "BGS 9"  in d: return "BGS 9"
    if "SGC 10" in d: return "SGC 10"
    if "SGC 9.5" in d: return "SGC 9.5"
    if "SGC 9"  in d: return "SGC 9"
    return "Raw"

def fetch_market(desc, grade):
    """Look up a card via CardHedger card-match (AI) and return comp avg + 90-day trend."""
    out = {"grade": grade, "comp_avg": None, "trend_dir": None, "trend_pct": 0.0, "matched": False}
    if not CARDHEDGER_KEY:
        return out

    # Use card-match (AI-powered) for better accuracy than card-search
    match = ch_card_match(desc)
    if not match:
        return out

    cid = match.get("card_id") or match.get("id")
    if not cid:
        return out

    out["matched"] = True

    # First try: grade-specific comp from the match's prices array
    prices = match.get("prices") or []
    for p in prices:
        if str(p.get("grade","")).upper() == grade.upper():
            try:
                out["comp_avg"] = float(p["price"])
            except Exception:
                pass
            break

    # Second try: all-prices-by-card — ONE cached call covers every grade, so the
    # Reprice loop stops making a separate comps call per grade/card (cost saver).
    if not out["comp_avg"]:
        for p in ch_all_prices(cid):
            if str(p.get("grade", "")).upper() == grade.upper():
                try:
                    out["comp_avg"] = float(p.get("price"))
                except Exception:
                    pass
                break

    # Third try: dedicated comps endpoint (recent-sales average) as a final fallback
    if not out["comp_avg"]:
        cdata = ch_comps(cid, grade) or {}
        out["comp_avg"] = cdata.get("comp_price") or cdata.get("average") or cdata.get("mean")

    # Fall back to Raw if still nothing and the card is graded
    if not out["comp_avg"] and grade != "Raw":
        for p in prices:
            if str(p.get("grade","")).upper() == "RAW":
                try:
                    out["comp_avg"] = float(p["price"])
                    out["grade"] = "Raw (fallback)"
                except Exception:
                    pass
                break

    out["trend_dir"], out["trend_pct"] = calculate_trend(ch_price_history(cid, grade, days=90))
    return out

def suggest_reprice(comp_avg, trend_pct, strategy, adj_pct):
    """Suggested list price from the market comp, shaped by the chosen strategy."""
    if not comp_avg or comp_avg <= 0:
        return None
    if strategy == "Match market":
        return comp_avg * (1 + adj_pct / 100.0)
    if strategy == "Undercut to sell faster":
        return comp_avg * (1 - adj_pct / 100.0)
    if strategy == "List high for offers":
        return comp_avg * (1 + adj_pct / 100.0)
    # Trend-following (default): lean into momentum, capped so a wild swing can't run away
    t = max(-25.0, min(25.0, trend_pct or 0.0))
    move = t * (adj_pct / 100.0)  # adj_pct is sensitivity 0..100
    return comp_avg * (1 + move / 100.0)

def trend_label(direction, pct):
    if not direction:
        return "—"
    if direction == "up":
        return f"↑ Up +{pct:.0f}%"
    if direction == "down":
        return f"↓ Down {pct:.0f}%"
    return f"→ Flat ({pct:+.0f}%)"

# ─── Sport / rookie detection + Supabase listings helpers ────────────────────
_SPORT_KEYS = {
    "Soccer": [
        'premier league','bundesliga','la liga','champions league','serie a',
        'liga mx','fifa','messi','pulisic','yamal','ronaldo','neymar','beckham',
        'vlahovic','gavi','pedri','mbappe','haaland','lewandowski','di maria',
        'topps ucc','panini select fifa','topps now uefa','soccer','futbol',
    ],
    "Basketball": [
        'nba',' hoops ','prizm nba','mosaic nba','select nba','basketball','wnba',
        'hailey van lith','player of the day','timberwolves','nuggets','heat ',
        'bucks ','suns ','clippers','maverick','thunder','pelicans','grizzlies',
        'knicks','lakers','celtics','warriors','strawther','beringer','knueppel',
        'joan beringer','julian strawther',
    ],
    "Football": [
        'nfl','gridiron','panini contenders season ticket','panini prestige',
        'panini absolute football','ohio state university nil',
        'lagway','hartman','pierce','jalen mcmillan','dallas turner',
        'jayden daniels','jordan addison','tuli tuipulotu','tyreek hill','julian sayin',
        'chiefs','eagles','cowboys','patriots','seahawks','49ers','ravens','bengals',
        'bills','commanders','vikings','jaguars','titans','giants','bears ','packers',
        'lions ','browns ','saints','falcons','panthers','cardinals','rams ','chargers',
        'raiders','broncos','dolphins','donruss optic rated rookie',
    ],
    "Baseball": [
        'bowman','topps','upper deck','fleer','stadium club','heritage',
        '1st bowman','minor league','mlb','yankees','braves','cubs','dodgers',
        'red sox','mets','padres','astros','phillies','winfield','palmeiro',
        'topps five star',"bowman's best",'bowman draft',
    ],
}

def detect_sport(title):
    t = (title or "").lower()
    for sport in ("Soccer", "Basketball", "Football", "Baseball"):
        if any(k in t for k in _SPORT_KEYS[sport]):
            return sport
    return "Unknown"

def is_rookie_card(title):
    t = (title or "").lower()
    return any(k in t for k in [' rc ', ' rc/', '(rc)', 'rookie', '1st bowman',
                                  'prospect', 'rated rookie', 'bowman draft'])

def price_freq_for(sport):
    return {"Baseball": "daily", "Soccer": "triweekly"}.get(sport, "weekly")

def needs_pricing_today(last_priced_at_str, freq):
    if not last_priced_at_str:
        return True
    try:
        from datetime import timezone as _tz
        lp = datetime.fromisoformat(last_priced_at_str.replace("Z", "+00:00"))
        now = datetime.now(_tz.utc)
        days = (now - lp).days
        return days >= {"daily": 1, "triweekly": 3}.get(freq, 7)
    except Exception:
        return True

def parse_ebay_csv_to_listings(df):
    col_map = {str(c).lower(): c for c in df.columns}
    def col(name):
        return col_map.get(name.lower(), name)
    rows = []
    for _, r in df.iterrows():
        item_num = str(r.get(col("item number"), "") or "").strip()
        if not item_num:
            continue
        title = str(r.get(col("title"), "") or "").strip()
        try:
            price = float(r.get(col("current price"), 0) or 0)
        except Exception:
            price = 0.0
        sport = detect_sport(title)
        rookie = is_rookie_card(title)
        freq = price_freq_for(sport)
        def _parse_ebay_date(s):
            s = str(s or "").strip()
            if not s or s == "nan":
                return None
            for tz_suffix in [" PDT", " PST", " EDT", " EST"]:
                s = s.replace(tz_suffix, "")
            try:
                return datetime.strptime(s, "%b-%d-%y %H:%M:%S").isoformat()
            except Exception:
                return None
        def _int(v):
            try: return int(v or 0)
            except Exception: return 0
        rows.append({
            "item_number":   item_num,
            "title":         title,
            "sku":           str(r.get(col("custom label (sku)"), "") or "").strip() or None,
            "current_price": price,
            "start_date":    _parse_ebay_date(r.get(col("start date"))),
            "end_date":      _parse_ebay_date(r.get(col("end date"))),
            "watchers":      _int(r.get(col("watchers"))),
            "sold_qty":      _int(r.get(col("sold quantity"))),
            "condition":     str(r.get(col("condition"), "") or "").strip() or None,
            "grader":        str(r.get(col("cd:professional grader - (id: 27501)"), "") or "").strip() or None,
            "grade":         str(r.get(col("cd:grade - (id: 27502)"), "") or "").strip() or None,
            "cert_number":   str(r.get(col("cda:certification number - (id: 27503)"), "") or "").strip() or None,
            "sport":         sport,
            "is_rookie":     rookie,
            "price_freq":    freq,
            "updated_at":    datetime.utcnow().isoformat() + "Z",
        })
    return rows

def _sb_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def _sb_base_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"}

def upsert_listings(rows):
    if not SUPABASE_URL or not rows:
        return 0
    ctx = _sb_ctx()
    total = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i+500]
        body = json.dumps(chunk).encode()
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/listings",
            data=body, method="POST",
            headers={**_sb_base_headers(),
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30):
                total += len(chunk)
        except Exception:
            pass
    return total

def load_listings(min_price=20, limit=1000):
    if not SUPABASE_URL:
        return []
    ctx = _sb_ctx()
    url = (f"{SUPABASE_URL}/rest/v1/listings"
           f"?current_price=gte.{min_price}&order=current_price.desc&limit={limit}")
    req = urllib.request.Request(url, headers=_sb_base_headers())
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = json.loads(r.read().decode())
            return data if isinstance(data, list) else []
    except Exception:
        return []

def update_listing(item_number, updates):
    if not SUPABASE_URL:
        return False
    ctx = _sb_ctx()
    body = json.dumps(updates).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/listings?item_number=eq.{urllib.parse.quote(item_number)}",
        data=body, method="PATCH",
        headers={**_sb_base_headers(), "Prefer": "return=minimal"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10):
            return True
    except Exception:
        return False

def save_listing_pricing(item_number, comp_avg, trend_dir, trend_pct, suggested):
    return update_listing(item_number, {
        "comp_avg": comp_avg, "trend_dir": trend_dir,
        "trend_pct": trend_pct, "suggested_price": suggested,
        "last_priced_at": datetime.utcnow().isoformat() + "Z",
        "updated_at":     datetime.utcnow().isoformat() + "Z",
    })

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — Hot Movers (top-movers)
# ══════════════════════════════════════════════════════════════════════════════
with tab7:
    st.markdown("## 🔥 Hot Movers")
    st.markdown("The week's biggest price gainers — what's heating up right now. A buy-radar, not a card you already own.")
    if not CARDHEDGER_KEY:
        st.info("📊 Connect the CardHedger API to load hot movers.")
    else:
        hm1, hm2 = st.columns([2, 1])
        cat = hm1.selectbox("Category", ["All", "Basketball", "Baseball", "Football", "Hockey", "Pokemon", "Soccer"], key="hm_cat")
        count = hm2.slider("How many", 10, 100, 25, 5, key="hm_count")
        if st.button("🔥 Load hot movers", key="hm_go"):
            st.session_state["hm_data"] = ch_top_movers(None if cat == "All" else cat, count)
        movers = st.session_state.get("hm_data")
        if movers is not None:
            def _gp(card, grade):
                for p in card.get("prices", []):
                    if p.get("grade") == grade:
                        try:
                            return float(p.get("price"))
                        except Exception:
                            return None
                return None
            rows = []
            for c in movers:
                g = c.get("gain")
                rows.append({
                    "Card": c.get("description", ""),
                    "Gain %": round(float(g), 1) if g is not None else None,
                    "7d Sales": c.get("7 Day Sales"),
                    "30d Sales": c.get("30 Day Sales"),
                    "PSA 10": _gp(c, "PSA 10"),
                    "Raw": _gp(c, "Raw"),
                })
            if rows:
                dfm = pd.DataFrame(rows).sort_values("Gain %", ascending=False)
                st.dataframe(
                    dfm, use_container_width=True, hide_index=True,
                    column_config={
                        "Gain %": st.column_config.NumberColumn(format="%.1f%%"),
                        "PSA 10": st.column_config.NumberColumn(format="$%.2f"),
                        "Raw": st.column_config.NumberColumn(format="$%.2f"),
                    },
                )
                st.caption(f"{len(rows)} movers · {cat}. Gain = recent weekly price change (CardHedger). Cross-check volume — a spike on thin sales is fragile.")
            else:
                st.info("No movers returned for that category — try another.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — Scan (image-match raw card + cert lookup)
# ══════════════════════════════════════════════════════════════════════════════
with tab8:
    st.markdown("## 📷 Scan")
    st.markdown("Identify a card fast — snap a raw card, or look up a graded slab by its cert number.")
    if not CARDHEDGER_KEY:
        st.info("📊 Connect the CardHedger API to use scanning.")
    else:
        scan_raw, scan_cert = st.tabs(["🃏 Raw card photo", "🎫 Graded slab (cert #)"])

        with scan_raw:
            st.caption("Upload or take a photo of the **front of a raw card**. CardHedger's AI returns the closest matches + prices.")
            up = st.file_uploader("Card photo", type=["jpg", "jpeg", "png", "webp"], key="scan_up")
            if up is not None:
                pcol, rcol = st.columns([1, 2])
                with pcol:
                    st.image(up, caption="Your photo", use_container_width=True)
                with rcol:
                    with st.spinner("Identifying card..."):
                        b64 = base64.b64encode(up.getvalue()).decode()
                        res = ch_image_match(b64)
                    cands = (res or {}).get("candidates") or []
                    if not cands:
                        st.warning("No match found. Try a straighter, well-lit photo of the card front.")
                    else:
                        top = cands[0]
                        sim = top.get("similarity")
                        st.markdown(f"**Best match:** {top.get('description','')}")
                        st.caption(f"Similarity {sim}% · {top.get('set','')} · {top.get('variant','')}")
                        prices = ch_all_prices(top.get("card_id"))
                        if prices:
                            prows = []
                            for p in prices:
                                try:
                                    prows.append({"Grade": p.get("grade", ""), "Price": float(p.get("price"))})
                                except Exception:
                                    pass
                            if prows:
                                st.dataframe(
                                    pd.DataFrame(prows), use_container_width=True, hide_index=True,
                                    column_config={"Price": st.column_config.NumberColumn(format="$%.2f")},
                                )
                if cands and len(cands) > 1:
                    with st.expander("Other possible matches"):
                        for c in cands[1:5]:
                            st.markdown(f"- {c.get('description','')} · _sim {c.get('similarity')}%_")

        with scan_cert:
            st.caption("Enter the cert number printed on the slab label to pull the card + recent sold prices.")
            cc1, cc2, cc3 = st.columns([2, 1, 1])
            cert = cc1.text_input("Cert number", key="cert_num")
            grader = cc2.selectbox("Grader", ["PSA", "BGS", "SGC", "CGC"], key="cert_grader")
            days = cc3.selectbox("History", [90, 180, 365], index=1, key="cert_days")
            if st.button("🎫 Look up cert", key="cert_go") and cert.strip():
                with st.spinner("Looking up cert..."):
                    cres = ch_prices_by_cert(cert.strip(), grader, days)
                info = (cres or {}).get("cert_info") or {}
                if info.get("description"):
                    st.markdown(f"**{info.get('description','')}**")
                    st.caption(f"{info.get('grader','').upper()} {info.get('grade','')} · cert {info.get('cert','')}")
                    pr = (cres or {}).get("prices") or []
                    vals = []
                    for p in pr:
                        try:
                            vals.append({"date": (p.get("closing_date") or "")[:10], "price": float(p.get("price"))})
                        except Exception:
                            pass
                    if vals:
                        dfp = pd.DataFrame(vals).drop_duplicates("date").sort_values("date")
                        st.metric("Latest sold", f"${dfp['price'].iloc[-1]:,.2f}")
                        st.line_chart(dfp.set_index("date")["price"], height=220)
                    else:
                        st.info("Cert matched, but no recent sold-price history for this exact card.")
                else:
                    st.warning("No card found for that cert / grader. Double-check the number and grader.")

with tab2:
    st.markdown("## 📦 Inventory Check")

    _is_owner = st.session_state.get("access_name", "") == "Duane"
    _wb_label = "DFS Operations Workbook" if _is_owner else "your Operations Workbook"

    st.markdown(
        f"Analyze cards from your intake log for grading potential. "
        f"Or upload a file directly here — use the **🚚 Shipment Intake** tab to bulk-import a shipment."
    )

    st.markdown("""
**How it works:**
1. Upload a CSV or Operations Workbook (.xlsx) → select a card → search GemRate → get GO/NO-GO
2. Add grading candidates directly to the Submission Tracker
""")

    uploaded = st.file_uploader(
        f"Upload inventory (CSV template or {_wb_label} .xlsx)",
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

            # ── 💰 Reprice Assistant (bulk comps + trend) ──────────────────────
            st.markdown("---")
            st.markdown("### 💰 Reprice Assistant")
            st.caption(
                "Pull current sold comps + 90-day trend for every card, then get a suggested "
                "new list price. Built for repricing a full inventory at once instead of one eBay listing at a time."
            )

            if not CARDHEDGER_KEY:
                st.info("📊 Connect the CardHedger API to enable live comps and repricing.")
            else:
                rp1, rp2, rp3 = st.columns(3)
                strategy = rp1.selectbox(
                    "Pricing strategy",
                    ["Trend-following", "Match market", "Undercut to sell faster", "List high for offers"],
                    index=0, key="rp_strategy",
                    help="Trend-following raises the suggestion when a card is trending up and cuts it when trending down.",
                )
                if strategy == "Trend-following":
                    adj_pct = rp2.slider("Trend sensitivity (%)", 0, 100, 50, 5, key="rp_sens",
                                         help="How hard to lean into the trend. 50% moves the price half as much as the 90-day trend.")
                elif strategy == "Undercut to sell faster":
                    adj_pct = rp2.slider("Undercut below comp (%)", 0, 30, 7, 1, key="rp_under")
                elif strategy == "List high for offers":
                    adj_pct = rp2.slider("Premium above comp (%)", 0, 30, 10, 1, key="rp_prem")
                else:
                    adj_pct = rp2.slider("Adjust vs comp (%)", -20, 20, 0, 1, key="rp_match")
                misprice_thresh = rp3.slider("Mispricing flag threshold (%)", 5, 30, 10, 1, key="rp_thresh",
                                             help="How far your listed price can sit from market before it's flagged over/underpriced.")

                max_n = max(1, len(inv))
                proc_n = st.slider("How many cards to refresh this run", 1, max_n, min(25, max_n), key="rp_count",
                                   help="Each card makes a few CardHedger calls. Process in batches to stay fast and within your API quota.")

                if st.button("🔄 Refresh comps & trend", key="rp_run"):
                    rows_market = []
                    sub = inv.head(proc_n)
                    total = max(1, len(sub))
                    prog = st.progress(0.0, text="Fetching comps…")
                    for i, (_, row) in enumerate(sub.iterrows()):
                        d = str(row.get("Card Description", "") or "").strip()
                        if not d:
                            continue
                        grade = detect_grade(d)
                        mkt = fetch_market(d, grade)
                        try:
                            listed = float(row.get("Listed Price ($)", 0) or 0)
                        except Exception:
                            listed = 0.0
                        try:
                            cost = float(row.get("Cost Basis ($)", 0) or 0)
                        except Exception:
                            cost = 0.0
                        rows_market.append({
                            "Card": d, "Grade": grade, "Cost": cost, "Listed": listed,
                            "Comp": mkt["comp_avg"], "TrendDir": mkt["trend_dir"],
                            "TrendPct": mkt["trend_pct"], "Matched": mkt["matched"],
                        })
                        prog.progress((i + 1) / total, text=f"Fetching comps… {i + 1}/{total}")
                    prog.empty()
                    st.session_state["reprice_data"] = rows_market
                    st.session_state["reprice_when"] = date.today().isoformat()

                rows_market = st.session_state.get("reprice_data")
                if rows_market:
                    st.caption(
                        f"Last refreshed {st.session_state.get('reprice_when','')} · {len(rows_market)} cards. "
                        f"Adjust the strategy/sliders above to recompute instantly — no new API calls."
                    )
                    computed = []
                    for r in rows_market:
                        comp, listed = r["Comp"], r["Listed"]
                        sugg = suggest_reprice(comp, r["TrendPct"], strategy, adj_pct)
                        if not comp:
                            flag = "no comp"
                        elif listed <= 0:
                            flag = "🟡 No list price"
                        elif (listed - comp) / comp > misprice_thresh / 100:
                            flag = "🔴 Overpriced"
                        elif (listed - comp) / comp < -misprice_thresh / 100:
                            flag = "🟢 Underpriced"
                        else:
                            flag = "⚪ On market"
                        if sugg and r["Cost"] and sugg < r["Cost"]:
                            flag += " ⚠ under cost"
                        delta = (sugg - listed) if (sugg and listed) else None
                        delta_pct = (delta / listed * 100) if (delta is not None and listed) else None
                        computed.append({**r, "Sugg": sugg, "Flag": flag, "Delta": delta, "DeltaPct": delta_pct})

                    n_over = sum(1 for c in computed if c["Flag"].startswith("🔴"))
                    n_under = sum(1 for c in computed if c["Flag"].startswith("🟢"))
                    n_nomatch = sum(1 for c in computed if not c["Matched"])
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("🔴 Overpriced", n_over, help="Listed above market — lower to sell")
                    mc2.metric("🟢 Underpriced", n_under, help="Listed below market — room to raise")
                    mc3.metric("No match", n_nomatch, help="CardHedger couldn't price these — check the card name")

                    tdf = pd.DataFrame([{
                        "Card": c["Card"], "Grade": c["Grade"],
                        "Cost": f"${c['Cost']:,.0f}" if c["Cost"] else "—",
                        "Listed": f"${c['Listed']:,.0f}" if c["Listed"] else "—",
                        "Comp (Market)": f"${c['Comp']:,.0f}" if c["Comp"] else ("—" if c["Matched"] else "no match"),
                        "Trend": trend_label(c["TrendDir"], c["TrendPct"]),
                        "Suggested": f"${c['Sugg']:,.0f}" if c["Sugg"] else "—",
                        "Δ vs Listed": (f"{'+' if c['Delta'] >= 0 else ''}${c['Delta']:,.0f} ({c['DeltaPct']:+.0f}%)"
                                        if c["Delta"] is not None else "—"),
                        "Flag": c["Flag"],
                    } for c in computed])
                    st.dataframe(tdf, use_container_width=True, hide_index=True)

                    csv_buf = io.StringIO()
                    pd.DataFrame([{
                        "Card Description": c["Card"], "Grade": c["Grade"],
                        "Cost Basis": round(c["Cost"], 2) if c["Cost"] else "",
                        "Current Listed Price": round(c["Listed"], 2) if c["Listed"] else "",
                        "Comp Avg (Market)": round(c["Comp"], 2) if c["Comp"] else "",
                        "90-Day Trend": trend_label(c["TrendDir"], c["TrendPct"]),
                        "Suggested Price": round(c["Sugg"], 2) if c["Sugg"] else "",
                        "Flag": c["Flag"],
                    } for c in computed]).to_csv(csv_buf, index=False)
                    st.download_button(
                        "📥 Download reprice CSV",
                        data=csv_buf.getvalue().encode(),
                        file_name=f"reprice_{date.today().isoformat()}.csv",
                        mime="text/csv", key="rp_csv",
                    )
                    st.caption(
                        "Use this CSV with eBay's bulk-edit / File Exchange, or work down the list by hand. "
                        "There's no eBay API, so prices can't be pushed automatically."
                    )
    else:
        st.info("👆 Upload your inventory file above to get started, or download the template first.")

    # ── 📐 Submission Planner — Grade vs Flip a whole batch ────────────────────
    st.markdown("---")
    st.markdown("### 📐 Submission Planner — Grade vs Flip a whole batch")
    st.caption(
        "Model a full submission the way new sellers don't: how much cash gets locked up, for how long, "
        "and whether grading actually beats flipping the lot raw. Defaults to a 20-card order — change to your numbers."
    )
    with st.expander("📐 Open the batch planner", expanded=False):
        bp1, bp2, bp3 = st.columns(3)
        n_cards = bp1.number_input("Number of cards", min_value=1, max_value=500, value=20, step=1, key="bp_n")
        avg_buy = bp2.number_input("Avg buy cost / card ($)", min_value=0.0, value=40.0, step=5.0, key="bp_buy")
        bp_tier = bp3.selectbox("Grading tier", list(PSA_FEES.keys()), index=0, key="bp_tier")

        bc1, bc2, bc3, bc4 = st.columns(4)
        avg_raw = bc1.number_input("Avg RAW comp ($)", min_value=0.0, value=55.0, step=5.0, key="bp_raw",
                                   help="What each card sells for raw right now")
        avg_10 = bc2.number_input("Avg PSA 10 comp ($)", min_value=0.0, value=180.0, step=10.0, key="bp_10")
        avg_9 = bc3.number_input("Avg PSA 9 comp ($)", min_value=0.0, value=70.0, step=5.0, key="bp_9")
        avg_gem = bc4.number_input("Avg gem rate (%)", min_value=0.0, max_value=100.0, value=50.0, step=5.0, key="bp_gem")

        fee_b = PSA_FEES[bp_tier]
        cal_b = int(PSA_DAYS.get(bp_tier, 60) * 1.4)
        gvf_b = grade_vs_flip(avg_buy, avg_raw, avg_10, avg_9, avg_gem, bp_tier, ship_cost, opp_rate)
        capital_total = gvf_b["capital"] * n_cards
        hold_total = gvf_b["hold"] * n_cards
        raw_total = (gvf_b["raw_net"] or 0) * n_cards
        exp_total = (gvf_b["net_exp"] or 0) * n_cards
        best_total = (gvf_b["net10"] or 0) * n_cards
        down_total = (gvf_b["net9"] or 0) * n_cards
        premium_total = exp_total - raw_total

        st.markdown("**If you GRADE the batch**")
        gm1, gm2, gm3 = st.columns(3)
        gm1.metric("💰 Cash locked up", f"${capital_total:,.0f}",
                   help=f"{n_cards} × (buy ${avg_buy:,.0f} + fee ${fee_b:.0f}"
                        + (f" + ship ${ship_cost:.0f}" if ship_cost else "") + ")")
        gm2.metric("⏳ Locked for", f"~{cal_b} days", help=f"~{cal_b/30:.1f} months at {bp_tier.split('(')[0].strip()}")
        gm3.metric("💸 Holding cost", f"${hold_total:,.0f}", help=f"At {opp_rate:.0f}%/yr opportunity cost")

        gn1, gn2, gn3 = st.columns(3)
        gn1.metric(f"🎯 Expected net (gem {avg_gem:.0f}%)", f"${exp_total:,.0f}",
                   help="Gem-rate-weighted across the batch, after every cost incl. holding")
        gn2.metric("💎 Best case (all 10s)", f"${best_total:,.0f}")
        gn3.metric("🥈 Downside (all 9s)", f"${down_total:,.0f}")

        st.markdown("**If you FLIP the batch RAW now**")
        fr1, fr2 = st.columns(2)
        fr1.metric("💵 Net now", f"${raw_total:,.0f}", help="Sell all raw today — cash in ~a week, nothing locked up")
        fr2.metric("Grade premium (expected)", f"{'+' if premium_total >= 0 else '−'}${abs(premium_total):,.0f}",
                   help="Expected graded net minus raw-flip net across the batch")

        if exp_total > raw_total and exp_total > 0:
            st.success(
                f"**✅ Grading wins (expected)** — across {n_cards} cards you'd net ~**${exp_total:,.0f}** vs "
                f"**${raw_total:,.0f}** flipping raw: **+${premium_total:,.0f}** for tying up **${capital_total:,.0f}** "
                f"for ~{cal_b/30:.1f} months. If none gem, downside is **${down_total:,.0f}**."
            )
        else:
            st.warning(
                f"**💵 Flipping raw may win** — grading's expected **${exp_total:,.0f}** doesn't beat the "
                f"**${raw_total:,.0f}** you'd net flipping raw now, and grading locks **${capital_total:,.0f}** "
                f"for ~{cal_b/30:.1f} months. Grade only the cards with the highest gem rates."
            )
        st.caption(
            "Rule of thumb: the lower the gem rate, the more the PSA 9 downside drags your expected return — "
            "and the longer your cash is locked, the more the holding cost eats the upside."
        )

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
                st.markdown(f"### 📊 {APP_NAME} — Operations Kit")
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
                        file_name=f"{APP_NAME.replace(' ', '_')}_Operations_Kit.xlsx",
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

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Shipment Intake
# ══════════════════════════════════════════════════════════════════════════════
INTAKE_PLATFORMS = ["eBay", "COMC", "Whatnot", "Card Show", "Private Sale", "MySlabs", "Facebook", "Other"]
INTAKE_STATUSES  = ["Received", "Sent to PSA", "In Collection", "Listed", "Sold"]

with tab5:
    st.markdown("## 🚚 Shipment Intake")
    st.markdown("Log cards as they arrive. Build a queue to evaluate or send to PSA.")

    if not SUPABASE_URL:
        st.warning("Supabase not configured — intake log unavailable in this environment.")
    else:
        # ── Add Card form ─────────────────────────────────────────────────────
        st.markdown("### ➕ Add a Card")
        with st.form("intake_form", clear_on_submit=True):
            fi1, fi2, fi3, fi4 = st.columns([3, 1, 1, 1])
            with fi1:
                i_player = st.text_input("Player *", placeholder="e.g. Steph Curry")
            with fi2:
                i_year = st.text_input("Year", placeholder="2021")
            with fi3:
                i_card_num = st.text_input("Card #", placeholder="44")
            with fi4:
                i_date = st.date_input("Date Received", value=date.today())

            fi5, fi6 = st.columns([3, 2])
            with fi5:
                i_set = st.text_input("Set", placeholder="e.g. Topps Chrome")
            with fi6:
                i_parallel = st.text_input("Parallel / Variation", placeholder="e.g. Silver Prizm")

            fi7, fi8, fi9 = st.columns([2, 2, 2])
            with fi7:
                i_cost = st.number_input("Cost ($) *", min_value=0.0, step=1.0, format="%.2f",
                                         help="What you paid — include shipping if buying from a single seller")
            with fi8:
                i_platform = st.selectbox("Platform", INTAKE_PLATFORMS)
            with fi9:
                i_source = st.text_input("Source / Seller", placeholder="e.g. cardking88")

            i_notes = st.text_input("Notes", placeholder="e.g. Pack fresh, lot of 3, small corner wear")

            intake_submitted = st.form_submit_button("Log Card", type="primary", use_container_width=True)
            if intake_submitted:
                if not i_player:
                    st.session_state["intake_msg"] = ("error", "Player name is required.")
                else:
                    parts = [p for p in [i_year, i_set, i_player, i_parallel] if p]
                    auto_desc = " ".join(parts)
                    if i_card_num:
                        auto_desc += f" #{i_card_num}"
                    _res, _err = sb_intake_insert({
                        "date_received": i_date.isoformat(),
                        "player":        i_player.strip(),
                        "year":          i_year.strip(),
                        "set_name":      i_set.strip(),
                        "parallel":      i_parallel.strip(),
                        "card_number":   i_card_num.strip(),
                        "card_description": auto_desc.strip(),
                        "cost":          float(i_cost) if i_cost > 0 else None,
                        "source":        i_source.strip(),
                        "platform":      i_platform,
                        "notes":         i_notes.strip(),
                        "status":        "Received",
                    })
                    if _err:
                        st.session_state["intake_msg"] = ("error", f"Save failed: {_err}")
                    else:
                        st.session_state["intake_msg"] = ("success", f"✓ Logged: {auto_desc}")

        # ── Bulk Upload from Spreadsheet ──────────────────────────────────────
        with st.expander("📂 Bulk Upload from Spreadsheet", expanded=False):
            st.markdown(
                "Upload your inventory CSV or Operations Workbook (.xlsx) to log multiple cards at once. "
                "Each row becomes a card in the Received Cards log below."
            )
            bu1, bu2 = st.columns([3, 1])
            with bu2:
                st.download_button(
                    "⬇️ Download Template",
                    data=make_template_csv(),
                    file_name="card_inventory_template.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="Fill this out and upload it here",
                )
            with bu1:
                bulk_file = st.file_uploader(
                    "Upload CSV template or Operations Workbook (.xlsx)",
                    type=["csv", "xlsx"],
                    key="intake_bulk_upload",
                )

            if bulk_file:
                bulk_df, bulk_source = load_inventory(bulk_file)
                if bulk_df is None:
                    st.error(f"Could not read file: {bulk_source}")
                else:
                    st.success(f"Found **{len(bulk_df)} cards** — preview below. Click Import to save them all.")
                    preview_cols = [c for c in ["Card Description", "Player", "Year", "Set",
                                                "Parallel", "Card Number", "Cost Basis ($)", "Source", "Notes"]
                                    if c in bulk_df.columns]
                    st.dataframe(bulk_df[preview_cols].head(20), use_container_width=True, hide_index=True)

                    if st.button(f"⬆️ Import {len(bulk_df)} cards into Intake Log", type="primary", key="bulk_import_btn"):
                        saved, failed = 0, 0
                        for _, brow in bulk_df.iterrows():
                            def _str(col): return str(brow.get(col, "") or "").strip()
                            def _flt(col):
                                try: return float(brow.get(col, 0) or 0) or None
                                except: return None
                            parts = [p for p in [_str("Year"), _str("Set"), _str("Player"), _str("Parallel")] if p]
                            desc  = _str("Card Description") or " ".join(parts)
                            card_num = _str("Card Number")
                            if card_num and card_num not in desc:
                                desc += f" #{card_num}"
                            _, err = sb_intake_insert({
                                "date_received":   date.today().isoformat(),
                                "player":          _str("Player"),
                                "year":            _str("Year"),
                                "set_name":        _str("Set"),
                                "parallel":        _str("Parallel"),
                                "card_number":     card_num,
                                "card_description": desc,
                                "cost":            _flt("Cost Basis ($)"),
                                "source":          _str("Source"),
                                "platform":        "Other",
                                "notes":           _str("Notes"),
                                "status":          "Received",
                            })
                            if err:
                                failed += 1
                            else:
                                saved += 1
                        if failed:
                            st.error(f"Imported {saved} cards — {failed} failed. Error: {err}")
                        else:
                            st.success(f"✓ Imported {saved} cards into your Intake Log!")
                        st.rerun()

        # ── Feedback from last submit ─────────────────────────────────────────
        if "intake_msg" in st.session_state:
            _msg_type, _msg_text = st.session_state.pop("intake_msg")
            if _msg_type == "success":
                st.success(_msg_text)
            else:
                st.error(_msg_text)

        # ── Received cards log ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("### 📋 Received Cards")

        intake_rows, intake_err = sb_intake_get()
        if intake_err:
            st.error(f"Could not load cards: {intake_err}")
            st.stop()
        if not intake_rows:
            st.info("No cards logged yet — use the form above to start tracking incoming shipments.")
        else:
            df_i = pd.DataFrame(intake_rows)

            # Summary strip
            total_i    = len(df_i)
            cost_i     = pd.to_numeric(df_i.get("cost", pd.Series(dtype=float)), errors="coerce").sum()
            received_i = (df_i["status"] == "Received").sum() if "status" in df_i.columns else 0
            sent_i     = (df_i["status"] == "Sent to PSA").sum() if "status" in df_i.columns else 0

            mi1, mi2, mi3, mi4 = st.columns(4)
            mi1.metric("Total Cards",    total_i)
            mi2.metric("Total Cost",     f"${cost_i:,.2f}")
            mi3.metric("Awaiting Eval",  received_i)
            mi4.metric("Sent to PSA",    sent_i)

            st.markdown("")

            # Coerce types so data_editor doesn't crash on Supabase string returns
            if "date_received" in df_i.columns:
                df_i["date_received"] = pd.to_datetime(df_i["date_received"], errors="coerce").dt.date
            if "cost" in df_i.columns:
                df_i["cost"] = pd.to_numeric(df_i["cost"], errors="coerce")

            _show_cols = [c for c in [
                "id", "date_received", "card_description", "player", "year",
                "set_name", "card_number", "parallel", "cost",
                "platform", "source", "status", "notes",
            ] if c in df_i.columns]

            edited_i = st.data_editor(
                df_i[_show_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id":               st.column_config.NumberColumn("ID", disabled=True),
                    "date_received":    st.column_config.DateColumn("Date Received"),
                    "card_description": st.column_config.TextColumn("Card", disabled=True),
                    "player":           st.column_config.TextColumn("Player"),
                    "year":             st.column_config.TextColumn("Year"),
                    "set_name":         st.column_config.TextColumn("Set"),
                    "card_number":      st.column_config.TextColumn("Card #"),
                    "parallel":         st.column_config.TextColumn("Parallel"),
                    "cost":             st.column_config.NumberColumn("Cost $", format="$%.2f"),
                    "platform":         st.column_config.SelectboxColumn("Platform", options=INTAKE_PLATFORMS),
                    "source":           st.column_config.TextColumn("Seller / Source"),
                    "status":           st.column_config.SelectboxColumn("Status", options=INTAKE_STATUSES),
                    "notes":            st.column_config.TextColumn("Notes"),
                },
            )

            ci1, ci2 = st.columns([1, 1])
            with ci1:
                if st.button("💾 Save changes", type="primary", key="intake_save", use_container_width=True):
                    for _, row in edited_i.iterrows():
                        row_id = int(row.get("id", 0))
                        if row_id:
                            updates = {k: (None if (isinstance(v, float) and pd.isna(v)) else v)
                                       for k, v in row.items() if k != "id"}
                            sb_intake_update(row_id, updates)
                    st.success("Saved ✓")
                    st.rerun()
            with ci2:
                csv_bytes = df_i[_show_cols].to_csv(index=False).encode()
                st.download_button(
                    "⬇️ Export to CSV",
                    data=csv_bytes,
                    file_name=f"shipment_intake_{date.today().isoformat()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Operations & Inventory (paid, metered live pricing)
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("## 🧰 Operations & Inventory")

    if is_beta:
        st.warning("🔒 Operations is part of full membership. Your preview includes Card Research and Inventory Check.")
        st.caption(
            "Operations adds live real-time pricing across your whole inventory, an editable cost basis, "
            "and reprice + margin tools — metered with a daily look-up budget to keep pricing fast and fair."
        )
    elif not CARDHEDGER_KEY:
        st.info("📊 Connect the CardHedger API to enable live pricing.")
    else:
        from datetime import timezone as _optz

        op_tab_inv, op_tab_queue = st.tabs(["📦 Inventory & Aging", "🔄 Reprice Queue"])

        # ── helpers shared across both sub-tabs ───────────────────────────────
        def _days_since(dt_str):
            if not dt_str:
                return None
            try:
                d = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=_optz.utc)
                return (datetime.now(_optz.utc) - d).days
            except Exception:
                return None

        def _last_priced_label(ts):
            if not ts:
                return "Never"
            days = _days_since(ts)
            return f"{days}d ago" if days is not None else "?"

        # ── INVENTORY & AGING ─────────────────────────────────────────────────
        with op_tab_inv:
            st.markdown("### Sync from eBay")
            st.caption(
                "eBay Seller Hub → Reports → Active listings → Download CSV. "
                "Drop it here — all 4,000+ listings sync into Supabase in seconds."
            )
            op_sync_file = st.file_uploader("eBay active listings CSV", type=["csv"], key="op_sync")
            if op_sync_file:
                sync_df = pd.read_csv(op_sync_file, encoding="utf-8-sig")
                listing_rows = parse_ebay_csv_to_listings(sync_df)
                st.caption(f"Parsed {len(listing_rows):,} listings. Click below to sync.")
                if st.button(f"⬆️ Sync {len(listing_rows):,} listings to Supabase", type="primary", key="op_sync_btn"):
                    with st.spinner("Syncing… (batches of 500)"):
                        n_synced = upsert_listings(listing_rows)
                    if n_synced:
                        st.success(f"✅ Synced {n_synced:,} listings.")
                        st.session_state.pop("op_listings_cache", None)
                        st.rerun()
                    else:
                        st.error("Sync failed. Run the Supabase SQL to create the `listings` table first, then retry.")

            st.divider()

            # Load from Supabase
            if "op_listings_cache" not in st.session_state:
                with st.spinner("Loading from Supabase…"):
                    st.session_state["op_listings_cache"] = load_listings(min_price=20)

            all_ls = st.session_state.get("op_listings_cache", [])

            if not all_ls:
                st.info("No $20+ listings in Supabase yet. Sync your eBay CSV above to get started.")
            else:
                today_due = sum(1 for l in all_ls if needs_pricing_today(l.get("last_priced_at"), l.get("price_freq","weekly")))
                never_priced = sum(1 for l in all_ls if not l.get("last_priced_at"))
                total_value = sum(l.get("current_price") or 0 for l in all_ls)
                sc1, sc2, sc3, sc4 = st.columns(4)
                sc1.metric("$20+ Listings", f"{len(all_ls):,}")
                sc2.metric("Need Pricing Today", f"{today_due:,}")
                sc3.metric("Never Priced", f"{never_priced:,}")
                sc4.metric("Listed Value", f"${total_value:,.0f}")

                fc1, fc2, fc3 = st.columns(3)
                sports_avail = sorted(set(l.get("sport","Unknown") for l in all_ls))
                f_sport = fc1.selectbox("Sport", ["All"] + sports_avail, key="inv_f_sport")
                f_show  = fc2.selectbox("Show", ["All","Needs Pricing","Never Priced"], key="inv_f_show")
                if fc3.button("🔄 Refresh inventory", key="inv_refresh"):
                    st.session_state.pop("op_listings_cache", None)
                    st.rerun()

                filtered_ls = all_ls
                if f_sport != "All":
                    filtered_ls = [l for l in filtered_ls if l.get("sport") == f_sport]
                if f_show == "Needs Pricing":
                    filtered_ls = [l for l in filtered_ls if needs_pricing_today(l.get("last_priced_at"), l.get("price_freq","weekly"))]
                elif f_show == "Never Priced":
                    filtered_ls = [l for l in filtered_ls if not l.get("last_priced_at")]

                inv_rows = []
                for l in filtered_ls:
                    inv_rows.append({
                        "Title":        (l.get("title") or "")[:65],
                        "Sport":        l.get("sport","?"),
                        "RC":           "✓" if l.get("is_rookie") else "",
                        "Price ($)":    l.get("current_price"),
                        "Cost ($)":     l.get("cost_basis"),
                        "Comp ($)":     l.get("comp_avg"),
                        "Suggested ($)":l.get("suggested_price"),
                        "Trend":        trend_label(l.get("trend_dir"), l.get("trend_pct") or 0),
                        "Days Listed":  _days_since(l.get("start_date")),
                        "Last Priced":  _last_priced_label(l.get("last_priced_at")),
                        "Freq":         l.get("price_freq","weekly"),
                        "Item #":       l.get("item_number",""),
                    })

                st.dataframe(
                    pd.DataFrame(inv_rows), use_container_width=True, hide_index=True,
                    column_config={
                        "Price ($)":     st.column_config.NumberColumn(format="$%.2f"),
                        "Cost ($)":      st.column_config.NumberColumn(format="$%.2f"),
                        "Comp ($)":      st.column_config.NumberColumn(format="$%.2f"),
                        "Suggested ($)": st.column_config.NumberColumn(format="$%.2f"),
                    },
                )
                st.caption(f"Showing {len(filtered_ls):,} of {len(all_ls):,} listings.")

        # ── REPRICE QUEUE ─────────────────────────────────────────────────────
        with op_tab_queue:
            used = pricing_used_today()
            if pricing_unlimited():
                st.caption("⚡ Live pricing: **unlimited** on your account.")
            else:
                st.progress(min(1.0, used / DAILY_PRICING_CAP) if DAILY_PRICING_CAP else 1.0,
                            text=f"Live look-ups today: {used} / {DAILY_PRICING_CAP}")
                if pricing_remaining() == 0:
                    st.warning(f"You've used today's {DAILY_PRICING_CAP} live look-ups — resets tomorrow.")

            if "op_listings_cache" not in st.session_state:
                st.session_state["op_listings_cache"] = load_listings(min_price=20)

            all_ls2 = st.session_state.get("op_listings_cache", [])
            if not all_ls2:
                st.info("No listings in Supabase yet. Go to Inventory & Aging → sync your eBay CSV first.")
            else:
                force_all = st.toggle("Price all $20+ listings (ignore schedule)", key="q_force_all")

                due = all_ls2 if force_all else [l for l in all_ls2 if needs_pricing_today(l.get("last_priced_at"), l.get("price_freq","weekly"))]

                def _queue_priority(l):
                    sport, rc = l.get("sport","Unknown"), l.get("is_rookie", False)
                    if sport == "Baseball" and rc: return 0
                    if sport == "Baseball": return 1
                    if sport == "Soccer": return 2
                    return 3

                due.sort(key=_queue_priority)

                st.markdown(f"### Today's queue — {len(due)} cards")
                st.caption(
                    "Priority order: ⚾ Baseball rookies → ⚾ Baseball → ⚽ Soccer → 🏈 Football / 🏀 Basketball / Other. "
                    f"{len(all_ls2) - len(due)} cards already up to date."
                )

                if not due:
                    st.success("✅ All $20+ listings are current — toggle 'Price all' above to force a full run.")
                else:
                    qc1, qc2, qc3 = st.columns(3)
                    q_strat = qc1.selectbox("Strategy", ["Trend-following","Match market","Undercut to sell faster","List high for offers"], key="q_strat")
                    if q_strat == "Trend-following":
                        q_adj = qc2.slider("Trend sensitivity (%)", 0, 100, 50, 5, key="q_sens")
                    elif q_strat == "Undercut to sell faster":
                        q_adj = qc2.slider("Undercut below comp (%)", 0, 30, 7, 1, key="q_under")
                    elif q_strat == "List high for offers":
                        q_adj = qc2.slider("Premium above comp (%)", 0, 30, 10, 1, key="q_prem")
                    else:
                        q_adj = qc2.slider("Adjust vs comp (%)", -20, 20, 0, 1, key="q_match")

                    budget = pricing_remaining()
                    max_run = len(due) if pricing_unlimited() else max(1, min(len(due), budget))
                    run_n = qc3.number_input("Cards this run", 1, max(1, len(due)), min(min(100, len(due)), max_run), key="q_runn")

                    blocked = (budget <= 0 and not pricing_unlimited())
                    if st.button(f"🔄 Run queue ({int(run_n)} look-ups)", type="primary", key="q_run", disabled=blocked):
                        batch = due[:int(run_n)]
                        prog = st.progress(0.0, text="Pricing…")
                        q_res = []
                        for i, l in enumerate(batch):
                            title = l.get("title","")
                            grade = detect_grade(title)
                            mkt = fetch_market(title, grade)
                            sugg = suggest_reprice(mkt["comp_avg"], mkt["trend_pct"], q_strat, q_adj)
                            save_listing_pricing(l["item_number"], mkt["comp_avg"], mkt["trend_dir"], mkt["trend_pct"], sugg)
                            q_res.append({**l, "comp_avg": mkt["comp_avg"], "trend_dir": mkt["trend_dir"],
                                          "trend_pct": mkt["trend_pct"], "suggested_price": sugg})
                            prog.progress((i+1)/len(batch), text=f"Pricing… {i+1}/{len(batch)}")
                        pricing_bump(len(batch))
                        prog.empty()
                        st.session_state.pop("op_listings_cache", None)
                        st.session_state["q_results"] = q_res
                        st.success(f"✅ Priced {len(q_res)} cards. Results saved to Supabase.")
                        st.rerun()

                    display_list = st.session_state.get("q_results") or due[:100]
                    if display_list:
                        rtbl = []
                        for l in display_list:
                            cur  = l.get("current_price") or 0
                            comp = l.get("comp_avg")
                            sugg = l.get("suggested_price")
                            diff = ((sugg - cur) / cur * 100) if (sugg and cur) else None
                            rtbl.append({
                                "Title":         (l.get("title","") or "")[:65],
                                "Sport":         l.get("sport","?"),
                                "RC":            "✓" if l.get("is_rookie") else "",
                                "Current ($)":   cur,
                                "Comp ($)":      comp,
                                "Trend":         trend_label(l.get("trend_dir"), l.get("trend_pct") or 0),
                                "Suggested ($)": sugg,
                                "∆ vs Listed":   f"{diff:+.0f}%" if diff is not None else "—",
                                "Item #":        l.get("item_number",""),
                            })
                        st.dataframe(
                            pd.DataFrame(rtbl), use_container_width=True, hide_index=True,
                            column_config={
                                "Current ($)":   st.column_config.NumberColumn(format="$%.2f"),
                                "Comp ($)":      st.column_config.NumberColumn(format="$%.2f"),
                                "Suggested ($)": st.column_config.NumberColumn(format="$%.2f"),
                            },
                        )

                        ebay_rows = [l for l in display_list if l.get("suggested_price")]
                        if ebay_rows:
                            # eBay upload file — price-only, 2 columns
                            # Uploading any extra columns risks overwriting Heystack formatting
                            ebuf = io.StringIO()
                            pd.DataFrame([{
                                "Item number": l.get("item_number",""),
                                "Start price": round(l["suggested_price"], 2),
                            } for l in ebay_rows]).to_csv(ebuf, index=False)

                            # Reference sheet with full context (keep for your own records)
                            ref_buf = io.StringIO()
                            pd.DataFrame([{
                                "Item number":   l.get("item_number",""),
                                "Title":         l.get("title",""),
                                "Current Price": l.get("current_price",""),
                                "New Price":     round(l["suggested_price"], 2),
                                "Comp Avg":      round(l["comp_avg"], 2) if l.get("comp_avg") else "",
                                "Trend":         trend_label(l.get("trend_dir"), l.get("trend_pct") or 0),
                                "Sport":         l.get("sport",""),
                            } for l in ebay_rows]).to_csv(ref_buf, index=False)

                            ec1, ec2 = st.columns(2)
                            ec1.download_button(
                                "📤 Upload to eBay (price only)",
                                data=ebuf.getvalue().encode(),
                                file_name=f"ebay_reprice_{date.today().isoformat()}.csv",
                                mime="text/csv", key="q_export_ebay",
                                help="Safe to upload directly — only Item number + Start price. Nothing else touched.",
                            )
                            ec2.download_button(
                                "📋 Full reference sheet",
                                data=ref_buf.getvalue().encode(),
                                file_name=f"reprice_reference_{date.today().isoformat()}.csv",
                                mime="text/csv", key="q_export_ref",
                                help="Your records — current price, comp, trend, sport. Do NOT upload this to eBay.",
                            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 9 — Consignments (DC Sports)
# ══════════════════════════════════════════════════════════════════════════════
with tab9:
    st.markdown("## 🏷️ Consignments")
    st.caption("DC Sports auction consignment tracking — import history, assign lot cost basis, track P&L.")

    if not SUPABASE_URL:
        st.warning("Supabase not connected. Configure in sidebar to enable Consignments.")
    else:
        # ── Helpers ───────────────────────────────────────────────────────────
        def _csn_get(table, params=""):
            url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
            req = urllib.request.Request(url, headers=sb_headers())
            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
                    return json.loads(r.read().decode())
            except Exception:
                return []

        def _csn_post(table, payload, prefer="return=representation"):
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/{table}",
                data=data,
                headers={**sb_headers(), "Prefer": prefer},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
                    body = r.read()
                    return json.loads(body.decode()) if body else []
            except Exception:
                return None

        def _csn_patch(table, filt, updates):
            data = json.dumps(updates).encode()
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/{table}?{filt}",
                data=data,
                headers={**sb_headers(), "Prefer": "return=minimal"},
                method="PATCH",
            )
            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10):
                    return True
            except Exception:
                return False

        def _csn_delete_row(table, filt):
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/{table}?{filt}",
                headers=sb_headers(),
                method="DELETE",
            )
            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10):
                    return True
            except Exception:
                return False

        def _parse_dc_amount(val):
            if val is None or str(val).strip() in ("", "nan"):
                return 0.0
            try:
                return float(str(val).replace("$", "").replace(",", "").strip())
            except ValueError:
                return 0.0

        def _load_csn():
            lots = _csn_get("consignment_lots", "?order=lot_sku.asc")
            ships = _csn_get("consignment_shipments", "?order=shipped_date.desc.nullslast,dc_package_id.desc")
            items = _csn_get("consignment_items", "?order=id.asc&limit=2000")
            return lots, ships, items

        if "csn_data" not in st.session_state:
            with st.spinner("Loading consignment data…"):
                st.session_state["csn_data"] = _load_csn()

        lots_raw, ships_raw, items_raw = st.session_state["csn_data"]

        # Per-card cost by lot SKU
        lot_per_card = {
            lot["lot_sku"]: round(lot["total_cost"] / max(lot["card_count"], 1), 2)
            for lot in lots_raw
        }

        # Augment items with cost + P&L
        csn_items = []
        for raw in items_raw:
            item = dict(raw)
            sku = item.get("lot_sku") or ""
            cost = lot_per_card.get(sku, 0.0) if sku else 0.0
            net = float(item.get("dc_net") or 0)
            item["_cost"] = cost
            item["_pl"] = round(net - cost, 2) if cost else None
            csn_items.append(item)

        # Business snapshot numbers
        paid_items = [i for i in csn_items if (i.get("dc_status") or "").lower() == "paid"]
        active_items = [i for i in csn_items if (i.get("dc_status") or "").lower() not in ("paid", "unsold")]
        total_net = sum(float(i.get("dc_net") or 0) for i in paid_items)
        total_invested = sum(i["_cost"] for i in paid_items if i["_cost"])
        total_pl = round(total_net - total_invested, 2) if total_invested else None

        sn1, sn2, sn3, sn4, sn5 = st.columns(5)
        sn1.metric("Cards Still Out", f"{len(active_items)}")
        sn2.metric("Total Cards (all)", f"{len(csn_items)}")
        sn3.metric("Total Invested", f"${total_invested:,.2f}" if total_invested else "— (assign lots)")
        sn4.metric("Total Net (Paid)", f"${total_net:,.2f}")
        if total_pl is not None:
            sn5.metric("Net P&L", f"${total_pl:+,.2f}")
        else:
            sn5.metric("Net P&L", "— assign lots")

        st.divider()

        csn_t1, csn_t2, csn_t3, csn_t4 = st.tabs(["📦 Shipments", "🃏 Cards", "🧰 Lots & Cost Basis", "⬆️ Import"])

        # ── SHIPMENTS ─────────────────────────────────────────────────────────
        with csn_t1:
            st.markdown("### DC Sports Shipments")
            if not ships_raw:
                st.info("No shipments yet. Import a DC Sports CSV to get started, or run the SQL below to create the tables first.")
            else:
                items_by_pkg = {}
                for item in csn_items:
                    pkg = item.get("dc_package_id") or "?"
                    items_by_pkg.setdefault(pkg, []).append(item)

                ship_rows = []
                for ship in ships_raw:
                    pkg = ship.get("dc_package_id") or "?"
                    pkg_items = items_by_pkg.get(pkg, [])
                    paid_c = sum(1 for i in pkg_items if (i.get("dc_status") or "").lower() == "paid")
                    unsold_c = sum(1 for i in pkg_items if (i.get("dc_status") or "").lower() == "unsold")
                    active_c = len(pkg_items) - paid_c - unsold_c
                    batch_net = sum(float(i.get("dc_net") or 0) for i in pkg_items if (i.get("dc_status") or "").lower() == "paid")
                    batch_cost = sum(i["_cost"] for i in pkg_items if i["_cost"])
                    ship_rows.append({
                        "Package ID": pkg,
                        "Shipped": ship.get("shipped_date") or "—",
                        "Cards": len(pkg_items),
                        "Paid": paid_c,
                        "Unsold": unsold_c,
                        "Active": active_c,
                        "Net ($)": round(batch_net, 2),
                        "Cost Basis ($)": round(batch_cost, 2) if batch_cost else None,
                        "P&L ($)": round(batch_net - batch_cost, 2) if batch_cost else None,
                        "Notes": ship.get("notes") or "",
                    })

                st.dataframe(
                    pd.DataFrame(ship_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Net ($)": st.column_config.NumberColumn(format="$%.2f"),
                        "Cost Basis ($)": st.column_config.NumberColumn(format="$%.2f"),
                        "P&L ($)": st.column_config.NumberColumn(format="$%.2f"),
                    },
                )

            with st.expander("Edit shipment notes / shipped date"):
                if ships_raw:
                    pkg_opts = [s["dc_package_id"] for s in ships_raw if s.get("dc_package_id")]
                    sel_pkg = st.selectbox("Shipment", pkg_opts, key="csn_edit_pkg")
                    match = next((s for s in ships_raw if s["dc_package_id"] == sel_pkg), None)
                    if match:
                        raw_date = match.get("shipped_date")
                        default_date = pd.to_datetime(raw_date).date() if raw_date else None
                        new_date = st.date_input("Shipped date", value=default_date, key="csn_edit_date")
                        new_notes = st.text_input("Notes", value=match.get("notes") or "", key="csn_edit_notes")
                        if st.button("Save", key="csn_save_ship"):
                            _csn_patch("consignment_shipments", f"id=eq.{match['id']}", {
                                "shipped_date": str(new_date) if new_date else None,
                                "notes": new_notes.strip() or None,
                            })
                            st.success("Saved.")
                            st.session_state.pop("csn_data", None)
                            st.rerun()
                else:
                    st.caption("No shipments to edit yet.")

        # ── CARDS ─────────────────────────────────────────────────────────────
        with csn_t2:
            st.markdown("### Card-Level Tracking")
            st.caption("Assign a Lot SKU to any card to connect its cost basis. Click **Save Lot SKU Assignments** after editing.")

            f1, f2, f3 = st.columns(3)
            pkg_opts2 = ["All"] + sorted(set(i.get("dc_package_id") or "?" for i in csn_items))
            pkg_filt = f1.selectbox("Shipment", pkg_opts2, key="csn_cards_pkg")
            status_opts = ["All"] + sorted(set((i.get("dc_status") or "Unknown") for i in csn_items))
            status_filt = f2.selectbox("Status", status_opts, key="csn_cards_status")
            basis_opts = ["All", "Has Cost Basis", "Missing Basis"]
            basis_filt = f3.selectbox("Cost Basis", basis_opts, key="csn_cards_basis")

            filtered = csn_items
            if pkg_filt != "All":
                filtered = [i for i in filtered if i.get("dc_package_id") == pkg_filt]
            if status_filt != "All":
                filtered = [i for i in filtered if (i.get("dc_status") or "Unknown") == status_filt]
            if basis_filt == "Has Cost Basis":
                filtered = [i for i in filtered if i["_cost"] > 0]
            elif basis_filt == "Missing Basis":
                filtered = [i for i in filtered if i["_cost"] == 0]

            if not filtered:
                st.info("No cards match the current filters.")
            else:
                card_rows = []
                card_ids = []
                for i in filtered:
                    card_ids.append(i["id"])
                    card_rows.append({
                        "Title": i.get("title") or "",
                        "Status": i.get("dc_status") or "",
                        "Package": i.get("dc_package_id") or "",
                        "Ended": (i.get("dc_ending_date") or "")[:10],
                        "DC Net ($)": float(i.get("dc_net") or 0),
                        "Lot SKU": i.get("lot_sku") or "",
                        "Cost ($)": i["_cost"] if i["_cost"] else None,
                        "P&L ($)": i["_pl"],
                    })

                card_df = pd.DataFrame(card_rows)
                edited_df = st.data_editor(
                    card_df,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="fixed",
                    disabled=["Title", "Status", "Package", "Ended", "DC Net ($)", "Cost ($)", "P&L ($)"],
                    column_config={
                        "DC Net ($)": st.column_config.NumberColumn(format="$%.2f"),
                        "Cost ($)": st.column_config.NumberColumn(format="$%.2f"),
                        "P&L ($)": st.column_config.NumberColumn(format="$%.2f"),
                        "Lot SKU": st.column_config.TextColumn(help="Type or clear a lot SKU — matches against Lots & Cost Basis tab"),
                    },
                    key="csn_cards_editor",
                )

                if st.button("💾 Save Lot SKU Assignments", key="csn_save_skus", type="primary"):
                    changed = 0
                    for idx, row in edited_df.iterrows():
                        orig_sku = str(card_df.iloc[idx]["Lot SKU"]).strip()
                        new_sku = str(row["Lot SKU"]).strip()
                        if new_sku != orig_sku:
                            item_id = card_ids[idx]
                            _csn_patch("consignment_items", f"id=eq.{item_id}", {"lot_sku": new_sku or None})
                            changed += 1
                    if changed:
                        st.success(f"Saved {changed} SKU assignment(s).")
                        st.session_state.pop("csn_data", None)
                        st.rerun()
                    else:
                        st.info("No changes detected.")

        # ── LOTS & COST BASIS ─────────────────────────────────────────────────
        with csn_t3:
            st.markdown("### Lots & Cost Basis")
            st.caption(
                "Record each lot you bought. Give it a SKU (e.g. LOT-001), enter the total cost and card count — "
                "per-card average is auto-calculated. Then assign that SKU to cards in the Cards tab."
            )

            with st.form("csn_new_lot_form"):
                st.markdown("**Add Lot**")
                l1, l2, l3 = st.columns(3)
                nl_sku = l1.text_input("Lot SKU *", placeholder="LOT-001")
                nl_name = l1.text_input("Lot Name", placeholder="eBay lot June 2026")
                nl_cost = l2.number_input("Total Cost ($)", min_value=0.0, step=0.01, format="%.2f")
                nl_count = l2.number_input("Card Count", min_value=1, step=1, value=1)
                nl_notes = l3.text_area("Notes", height=80)
                if nl_count > 0 and nl_cost > 0:
                    l3.caption(f"Per-card avg: **${nl_cost / nl_count:.2f}**")
                lot_submitted = st.form_submit_button("Add Lot", type="primary")

            if lot_submitted:
                if not nl_sku.strip():
                    st.error("Lot SKU is required.")
                else:
                    res = _csn_post("consignment_lots", {
                        "lot_sku": nl_sku.strip().upper(),
                        "lot_name": nl_name.strip() or None,
                        "total_cost": float(nl_cost),
                        "card_count": int(nl_count),
                        "notes": nl_notes.strip() or None,
                    })
                    if res is not None:
                        st.success(f"Lot {nl_sku.strip().upper()} added. Per-card: ${nl_cost / max(nl_count, 1):.2f}")
                        st.session_state.pop("csn_data", None)
                        st.rerun()
                    else:
                        st.error("Could not save — SKU may already exist. Delete the existing lot first to replace it.")

            st.divider()

            if not lots_raw:
                st.info("No lots yet. Add one above.")
            else:
                lot_rows2 = []
                for lot in lots_raw:
                    per_card = round(lot["total_cost"] / max(lot["card_count"], 1), 2)
                    assigned = sum(1 for i in csn_items if i.get("lot_sku") == lot["lot_sku"])
                    lot_rows2.append({
                        "SKU": lot["lot_sku"],
                        "Name": lot.get("lot_name") or "",
                        "Total Cost": lot["total_cost"],
                        "Cards": lot["card_count"],
                        "Per-Card Avg": per_card,
                        "Assigned Items": assigned,
                        "Notes": lot.get("notes") or "",
                        "_id": lot["id"],
                    })
                lot_df2 = pd.DataFrame(lot_rows2)
                st.dataframe(
                    lot_df2.drop(columns=["_id"]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Total Cost": st.column_config.NumberColumn(format="$%.2f"),
                        "Per-Card Avg": st.column_config.NumberColumn(format="$%.2f"),
                    },
                )

                del_sku_opts = ["— select to delete —"] + [lot["lot_sku"] for lot in lots_raw]
                del_sku = st.selectbox("Delete a lot", del_sku_opts, key="csn_del_lot_sel")
                if del_sku != "— select to delete —":
                    lot_id = next(lot["id"] for lot in lots_raw if lot["lot_sku"] == del_sku)
                    if st.button(f"🗑️ Delete {del_sku}", key="csn_del_lot_btn"):
                        _csn_delete_row("consignment_lots", f"id=eq.{lot_id}")
                        st.success(f"Deleted {del_sku}.")
                        st.session_state.pop("csn_data", None)
                        st.rerun()

        # ── IMPORT ────────────────────────────────────────────────────────────
        with csn_t4:
            st.markdown("### Import DC Sports Export")
            st.caption(
                "In DC Sports, go to your Seller Dashboard → export your cards CSV. "
                "The file should have columns: Title, Status, ListingDate, EndingDate, BuyItNow, "
                "SalePrice, Fees, Net, FriendlyPackageId, FrontImageUrl. "
                "Re-importing the same file is safe — duplicates are skipped automatically."
            )

            csn_file = st.file_uploader("DC Sports CSV", type=["csv"], key="csn_import_file")
            if csn_file:
                try:
                    import_df = pd.read_csv(csn_file, encoding="utf-8-sig")
                    st.caption(f"Found **{len(import_df):,}** rows. Preview:")
                    st.dataframe(import_df.head(10), use_container_width=True, hide_index=True)

                    uniq_pkgs = import_df["FriendlyPackageId"].dropna().astype(str).nunique() if "FriendlyPackageId" in import_df.columns else 0
                    st.caption(f"Shipment batches detected: **{uniq_pkgs}**")

                    if st.button("⬆️ Import to Supabase", type="primary", key="csn_import_btn"):
                        existing_raw2 = _csn_get("consignment_items", "?select=dedup_key")
                        existing_keys2 = {r["dedup_key"] for r in existing_raw2 if r.get("dedup_key")}

                        # Ensure shipment rows exist
                        pkg_ids2 = import_df["FriendlyPackageId"].dropna().astype(str).unique() if "FriendlyPackageId" in import_df.columns else []
                        existing_ships2 = {s["dc_package_id"] for s in ships_raw if s.get("dc_package_id")}
                        for pkg in pkg_ids2:
                            if str(pkg) not in existing_ships2:
                                _csn_post("consignment_shipments", {"dc_package_id": str(pkg)}, prefer="return=minimal")

                        fresh_ships2 = _csn_get("consignment_shipments", "?order=id.asc")
                        ship_id_map = {s["dc_package_id"]: s["id"] for s in fresh_ships2 if s.get("dc_package_id")}

                        imported = skipped = failed = 0
                        progress = st.progress(0)
                        total_rows = len(import_df)

                        for idx, row in import_df.iterrows():
                            progress.progress(int((idx + 1) / total_rows * 100))
                            pkg = str(row.get("FriendlyPackageId") or "").strip()
                            title = str(row.get("Title") or "").strip()
                            ending = str(row.get("EndingDate") or "").strip()[:19]
                            dedup = f"{pkg}|{title}|{ending}"

                            if dedup in existing_keys2:
                                skipped += 1
                                continue

                            item_row = {
                                "dc_package_id": pkg or None,
                                "shipment_id": ship_id_map.get(pkg),
                                "title": title or None,
                                "dc_status": str(row.get("Status") or "").strip() or None,
                                "dc_listing_date": str(row.get("ListingDate") or "").strip()[:19] or None,
                                "dc_ending_date": ending or None,
                                "dc_buy_it_now": _parse_dc_amount(row.get("BuyItNow")),
                                "dc_sale_price": _parse_dc_amount(row.get("SalePrice")),
                                "dc_fees": _parse_dc_amount(row.get("Fees")),
                                "dc_net": _parse_dc_amount(row.get("Net")),
                                "dc_front_image_url": str(row.get("FrontImageUrl") or "").strip() or None,
                                "dedup_key": dedup,
                            }
                            res2 = _csn_post("consignment_items", item_row, prefer="return=minimal")
                            if res2 is not None:
                                imported += 1
                                existing_keys2.add(dedup)
                            else:
                                failed += 1

                        progress.empty()
                        msg = f"✅ Imported **{imported}** cards"
                        if skipped:
                            msg += f", skipped **{skipped}** duplicates"
                        if failed:
                            msg += f", **{failed}** failed"
                        st.success(msg + ".")
                        if imported:
                            st.session_state.pop("csn_data", None)
                            st.rerun()
                except Exception as e:
                    st.error(f"Error reading CSV: {e}")

            st.divider()
            st.markdown("**SQL — Create Consignment Tables** *(run once in Supabase SQL Editor)*")
            st.code(
                """create table if not exists consignment_lots (
  id bigint primary key generated always as identity,
  lot_sku text not null unique,
  lot_name text,
  total_cost numeric not null default 0,
  card_count integer not null default 1,
  notes text,
  created_at timestamptz default now()
);

create table if not exists consignment_shipments (
  id bigint primary key generated always as identity,
  dc_package_id text unique,
  shipped_date date,
  notes text,
  created_at timestamptz default now()
);

create table if not exists consignment_items (
  id bigint primary key generated always as identity,
  shipment_id bigint references consignment_shipments(id),
  dc_package_id text,
  lot_sku text,
  title text,
  dc_status text,
  dc_listing_date text,
  dc_ending_date text,
  dc_buy_it_now numeric,
  dc_sale_price numeric,
  dc_fees numeric,
  dc_net numeric,
  dc_front_image_url text,
  dedup_key text unique,
  created_at timestamptz default now()
);
create index if not exists idx_ci_shipment on consignment_items(shipment_id);
create index if not exists idx_ci_lot_sku on consignment_items(lot_sku);""",
                language="sql",
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 10 — Sales & P&L
# ══════════════════════════════════════════════════════════════════════════════
with tab10:
    st.markdown("## 💰 Sales & P&L")
    st.caption("Import eBay and CollX sales exports — track gross revenue, platform fees, and net proceeds across all channels.")

    if not SUPABASE_URL:
        st.warning("Supabase not connected. Configure in sidebar to enable Sales & P&L.")
    else:
        # ── Helpers ───────────────────────────────────────────────────────────
        def _sal_get(params=""):
            url = f"{SUPABASE_URL}/rest/v1/sales_records{params}"
            req = urllib.request.Request(url, headers=sb_headers())
            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
                    return json.loads(r.read().decode())
            except Exception:
                return []

        def _sal_post(payload, prefer="return=minimal"):
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/sales_records",
                data=data,
                headers={**sb_headers(), "Prefer": prefer},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
                    body = r.read()
                    return json.loads(body.decode()) if body else []
            except Exception:
                return None

        def _sal_delete(filt):
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/sales_records?{filt}",
                headers=sb_headers(),
                method="DELETE",
            )
            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10):
                    return True
            except Exception:
                return False

        def _parse_money(val):
            if val is None or str(val).strip() in ("", "nan"):
                return 0.0
            try:
                return float(str(val).replace("$", "").replace(",", "").strip())
            except ValueError:
                return 0.0

        def _parse_ebay_date(s):
            s = str(s).strip()
            for fmt in ("%b-%d-%y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return s[:10] if len(s) >= 10 else s

        def _parse_collx_date(s):
            s = str(s).strip()
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return s[:10] if len(s) >= 10 else s

        # Load all sales records
        if "sal_data" not in st.session_state:
            with st.spinner("Loading sales data…"):
                st.session_state["sal_data"] = _sal_get("?order=sale_date.desc&limit=5000")

        all_sales = st.session_state.get("sal_data", [])

        # ── Snapshot ──────────────────────────────────────────────────────────
        ebay_sales = [s for s in all_sales if s.get("source") == "ebay"]
        collx_sales = [s for s in all_sales if s.get("source") == "collx"]
        dc_sales = [s for s in all_sales if s.get("source") == "dc_sports"]

        total_gross = sum(_parse_money(s.get("gross_revenue")) for s in all_sales)
        total_fees = sum(_parse_money(s.get("platform_fee")) for s in all_sales)
        total_net = sum(_parse_money(s.get("net_proceeds")) for s in all_sales)
        total_txns = len(all_sales)

        sn1, sn2, sn3, sn4, sn5 = st.columns(5)
        sn1.metric("Total Transactions", f"{total_txns:,}")
        sn2.metric("Gross Revenue", f"${total_gross:,.2f}")
        sn3.metric("Platform Fees", f"${total_fees:,.2f}")
        sn4.metric("Net Proceeds", f"${total_net:,.2f}")
        margin = round((total_net / total_gross * 100), 1) if total_gross else 0
        sn5.metric("Keep Rate", f"{margin}%")

        # Per-platform breakdown
        if all_sales:
            st.divider()
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                eb_gross = sum(_parse_money(s.get("gross_revenue")) for s in ebay_sales)
                eb_net = sum(_parse_money(s.get("net_proceeds")) for s in ebay_sales)
                st.markdown(f"**eBay** — {len(ebay_sales)} sales")
                st.markdown(f"Gross: **${eb_gross:,.2f}** · Net: **${eb_net:,.2f}**")
            with pc2:
                cx_gross = sum(_parse_money(s.get("gross_revenue")) for s in collx_sales)
                cx_net = sum(_parse_money(s.get("net_proceeds")) for s in collx_sales)
                st.markdown(f"**CollX** — {len(collx_sales)} sales")
                st.markdown(f"Gross: **${cx_gross:,.2f}** · Net: **${cx_net:,.2f}**")
            with pc3:
                dc_gross = sum(_parse_money(s.get("gross_revenue")) for s in dc_sales)
                dc_net = sum(_parse_money(s.get("net_proceeds")) for s in dc_sales)
                st.markdown(f"**DC Sports** — {len(dc_sales)} sales")
                st.markdown(f"Gross: **${dc_gross:,.2f}** · Net: **${dc_net:,.2f}**")

        st.divider()

        sal_t1, sal_t2, sal_t3 = st.tabs(["📊 P&L by Month", "📋 Sales Log", "⬆️ Import"])

        # ── P&L BY MONTH ──────────────────────────────────────────────────────
        with sal_t1:
            if not all_sales:
                st.info("No sales yet. Import eBay or CollX data in the Import tab.")
            else:
                year_opts = sorted(set(
                    str(s.get("sale_date") or "")[:4]
                    for s in all_sales
                    if str(s.get("sale_date") or "")[:4].isdigit()
                ), reverse=True)
                sel_year = st.selectbox("Year", year_opts, key="sal_year")

                from collections import defaultdict
                monthly = defaultdict(lambda: {"gross": 0.0, "fees": 0.0, "net": 0.0, "txns": 0})
                for s in all_sales:
                    d = str(s.get("sale_date") or "")
                    if not d[:4] == sel_year:
                        continue
                    month_key = d[:7]
                    monthly[month_key]["gross"] += _parse_money(s.get("gross_revenue"))
                    monthly[month_key]["fees"] += _parse_money(s.get("platform_fee"))
                    monthly[month_key]["net"] += _parse_money(s.get("net_proceeds"))
                    monthly[month_key]["txns"] += 1

                if not monthly:
                    st.info(f"No sales for {sel_year}.")
                else:
                    month_names = {
                        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
                        "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
                        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
                    }
                    rows_m = []
                    ytd_gross = ytd_fees = ytd_net = ytd_txns = 0
                    for mk in sorted(monthly.keys()):
                        m = monthly[mk]
                        mn = month_names.get(mk[5:7], mk[5:7])
                        rows_m.append({
                            "Month": f"{mn} {mk[:4]}",
                            "Sales": m["txns"],
                            "Gross ($)": round(m["gross"], 2),
                            "Fees ($)": round(m["fees"], 2),
                            "Net ($)": round(m["net"], 2),
                            "Keep %": round(m["net"] / m["gross"] * 100, 1) if m["gross"] else 0,
                        })
                        ytd_gross += m["gross"]; ytd_fees += m["fees"]
                        ytd_net += m["net"]; ytd_txns += m["txns"]

                    # YTD totals row
                    rows_m.append({
                        "Month": f"— YTD {sel_year} —",
                        "Sales": ytd_txns,
                        "Gross ($)": round(ytd_gross, 2),
                        "Fees ($)": round(ytd_fees, 2),
                        "Net ($)": round(ytd_net, 2),
                        "Keep %": round(ytd_net / ytd_gross * 100, 1) if ytd_gross else 0,
                    })

                    st.dataframe(
                        pd.DataFrame(rows_m),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Gross ($)": st.column_config.NumberColumn(format="$%.2f"),
                            "Fees ($)": st.column_config.NumberColumn(format="$%.2f"),
                            "Net ($)": st.column_config.NumberColumn(format="$%.2f"),
                            "Keep %": st.column_config.NumberColumn(format="%.1f%%"),
                        },
                    )

                    # Channel mix for the year
                    st.markdown("**Channel Mix**")
                    ch_rows = []
                    for src, label in [("ebay", "eBay"), ("collx", "CollX"), ("dc_sports", "DC Sports")]:
                        src_sales = [s for s in all_sales if s.get("source") == src and str(s.get("sale_date") or "")[:4] == sel_year]
                        if src_sales:
                            sg = sum(_parse_money(s.get("gross_revenue")) for s in src_sales)
                            sn_ = sum(_parse_money(s.get("net_proceeds")) for s in src_sales)
                            sf = sum(_parse_money(s.get("platform_fee")) for s in src_sales)
                            ch_rows.append({"Channel": label, "Sales": len(src_sales), "Gross ($)": round(sg, 2), "Fees ($)": round(sf, 2), "Net ($)": round(sn_, 2)})
                    if ch_rows:
                        st.dataframe(
                            pd.DataFrame(ch_rows),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Gross ($)": st.column_config.NumberColumn(format="$%.2f"),
                                "Fees ($)": st.column_config.NumberColumn(format="$%.2f"),
                                "Net ($)": st.column_config.NumberColumn(format="$%.2f"),
                            },
                        )

        # ── SALES LOG ─────────────────────────────────────────────────────────
        with sal_t2:
            if not all_sales:
                st.info("No sales yet.")
            else:
                lf1, lf2, lf3 = st.columns(3)
                src_opts = ["All"] + sorted(set(s.get("source", "") for s in all_sales))
                src_filt = lf1.selectbox("Platform", src_opts, key="sal_log_src",
                                          format_func=lambda x: {"ebay": "eBay", "collx": "CollX", "dc_sports": "DC Sports"}.get(x, x))
                status_opts2 = ["All"] + sorted(set(s.get("status", "") or "" for s in all_sales if s.get("status")))
                status_filt2 = lf2.selectbox("Status", status_opts2, key="sal_log_status")
                year_opts2 = ["All"] + sorted(set(str(s.get("sale_date") or "")[:4] for s in all_sales if str(s.get("sale_date") or "")[:4].isdigit()), reverse=True)
                year_filt2 = lf3.selectbox("Year", year_opts2, key="sal_log_year")

                log_filtered = all_sales
                if src_filt != "All":
                    log_filtered = [s for s in log_filtered if s.get("source") == src_filt]
                if status_filt2 != "All":
                    log_filtered = [s for s in log_filtered if s.get("status") == status_filt2]
                if year_filt2 != "All":
                    log_filtered = [s for s in log_filtered if str(s.get("sale_date") or "")[:4] == year_filt2]

                st.caption(f"Showing {len(log_filtered):,} of {len(all_sales):,} sales")

                src_label = {"ebay": "eBay", "collx": "CollX", "dc_sports": "DC Sports"}
                log_rows = []
                for s in log_filtered[:500]:
                    log_rows.append({
                        "Date": str(s.get("sale_date") or "")[:10],
                        "Platform": src_label.get(s.get("source", ""), s.get("source", "")),
                        "Title": s.get("title") or "",
                        "Qty": s.get("quantity") or 1,
                        "Gross ($)": _parse_money(s.get("gross_revenue")),
                        "Fee ($)": _parse_money(s.get("platform_fee")),
                        "Net ($)": _parse_money(s.get("net_proceeds")),
                        "Status": s.get("status") or "",
                    })
                if len(log_filtered) > 500:
                    st.caption("Showing first 500 rows — filter by year or platform to see more.")

                st.dataframe(
                    pd.DataFrame(log_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Gross ($)": st.column_config.NumberColumn(format="$%.2f"),
                        "Fee ($)": st.column_config.NumberColumn(format="$%.2f"),
                        "Net ($)": st.column_config.NumberColumn(format="$%.2f"),
                    },
                )

                # Export
                if log_rows:
                    csv_out = pd.DataFrame(log_rows).to_csv(index=False).encode()
                    st.download_button("⬇️ Export filtered to CSV", data=csv_out,
                                       file_name=f"sales_export_{date.today()}.csv",
                                       mime="text/csv", key="sal_export")

                st.divider()
                with st.expander("🗑️ Delete sales by platform (re-import to refresh)"):
                    del_src = st.selectbox("Delete all records from", ["— select —", "eBay", "CollX", "DC Sports"], key="sal_del_src")
                    src_map = {"eBay": "ebay", "CollX": "collx", "DC Sports": "dc_sports"}
                    if del_src != "— select —":
                        st.warning(f"This permanently deletes all {del_src} sales records from Supabase. Re-import the CSV to restore.")
                        if st.button(f"Delete all {del_src} records", type="primary", key="sal_del_btn"):
                            _sal_delete(f"source=eq.{src_map[del_src]}")
                            st.success(f"Deleted all {del_src} records.")
                            st.session_state.pop("sal_data", None)
                            st.rerun()

        # ── IMPORT ────────────────────────────────────────────────────────────
        with sal_t3:
            imp_ebay, imp_collx, imp_whatnot, imp_dc, imp_manual = st.tabs(["📦 eBay", "🃏 CollX", "🎥 Whatnot", "🏷️ DC Sports", "✏️ Manual"])

            # ── eBay import ───────────────────────────────────────────────────
            with imp_ebay:
                st.markdown("### Import eBay Sold Report")
                st.caption(
                    "eBay Seller Hub → Reports → Downloads → Transactions report (CSV). "
                    "Import as many date ranges as you like — duplicates are skipped. "
                    "eBay's report doesn't include fees directly; final value fee is estimated at **12.9% of (item price + shipping) + $0.30**."
                )
                ebay_file = st.file_uploader("eBay Transactions / Sold Report CSV", type=["csv"], key="sal_ebay_file")
                if ebay_file:
                    try:
                        raw_content = ebay_file.read().decode("utf-8-sig")
                        lines = raw_content.split("\n")
                        # eBay reports have a blank/junk first line — find the header
                        header_idx = 0
                        for i, line in enumerate(lines[:5]):
                            if "Sale Date" in line or "Item Title" in line or "Sales Record" in line:
                                header_idx = i
                                break
                        csv_content = "\n".join(lines[header_idx:])
                        ebay_df = pd.read_csv(io.StringIO(csv_content), encoding="utf-8-sig")
                        ebay_df.columns = [c.strip() for c in ebay_df.columns]
                        # Drop completely empty rows
                        ebay_df = ebay_df.dropna(how="all")
                        ebay_df = ebay_df[ebay_df.get("Sale Date", ebay_df.iloc[:, 0]).astype(str).str.strip() != ""]

                        st.caption(f"Found **{len(ebay_df):,}** rows. Preview:")
                        st.dataframe(ebay_df.head(5), use_container_width=True, hide_index=True)

                        if st.button("⬆️ Import eBay Sales", type="primary", key="sal_ebay_btn"):
                            existing_raw3 = _sal_get("?select=dedup_key&source=eq.ebay")
                            existing_keys3 = {r["dedup_key"] for r in existing_raw3 if r.get("dedup_key")}

                            imported3 = skipped3 = failed3 = 0
                            prog3 = st.progress(0)
                            total3 = len(ebay_df)

                            for idx3, row3 in ebay_df.iterrows():
                                prog3.progress(int((idx3 + 1) / max(total3, 1) * 100))
                                sale_date3 = _parse_ebay_date(row3.get("Sale Date", ""))
                                item_num3 = str(row3.get("Item Number", "") or "").strip()
                                sold_for3 = _parse_money(row3.get("Sold For", 0))
                                shipping3 = _parse_money(row3.get("Shipping And Handling", 0))
                                title3 = str(row3.get("Item Title", "") or "").strip()
                                qty3 = int(float(str(row3.get("Quantity", 1) or 1)))
                                gross3 = round(sold_for3 + shipping3, 2)
                                fee3 = round(gross3 * 0.129 + 0.30, 2)
                                net3 = round(gross3 - fee3, 2)
                                dedup3 = f"ebay|{item_num3}|{sale_date3}|{round(sold_for3, 2)}"

                                if dedup3 in existing_keys3:
                                    skipped3 += 1
                                    continue

                                rec3 = {
                                    "source": "ebay",
                                    "order_id": str(row3.get("Order Number", "") or "").strip() or None,
                                    "sale_date": sale_date3 or None,
                                    "title": title3 or None,
                                    "item_number": item_num3 or None,
                                    "quantity": qty3,
                                    "sale_price": sold_for3,
                                    "shipping_collected": shipping3,
                                    "gross_revenue": gross3,
                                    "platform_fee": fee3,
                                    "net_proceeds": net3,
                                    "status": str(row3.get("Feedback Received", "") or "sold").strip() or "sold",
                                    "dedup_key": dedup3,
                                }
                                res3 = _sal_post(rec3)
                                if res3 is not None:
                                    imported3 += 1
                                    existing_keys3.add(dedup3)
                                else:
                                    failed3 += 1

                            prog3.empty()
                            msg3 = f"✅ Imported **{imported3}** eBay sales"
                            if skipped3:
                                msg3 += f", skipped **{skipped3}** duplicates"
                            if failed3:
                                msg3 += f", **{failed3}** failed"
                            st.success(msg3 + ".")
                            st.caption("Note: eBay fees are estimated at 12.9% + $0.30. For exact fees, cross-reference your eBay invoice.")
                            if imported3:
                                st.session_state.pop("sal_data", None)
                                st.rerun()
                    except Exception as e3:
                        st.error(f"Error reading eBay CSV: {e3}")

            # ── CollX import ──────────────────────────────────────────────────
            with imp_collx:
                st.markdown("### Import CollX Orders Export")
                st.caption(
                    "CollX app → Orders → Export. "
                    "Columns: order_number, order_date, buyer_name, total_items, merchandise_value, gross_subtotal, net_proceeds, status. "
                    "Net proceeds are exact from CollX (fees already deducted). Re-importing is safe — duplicates skipped."
                )
                collx_file = st.file_uploader("CollX orders export CSV", type=["csv"], key="sal_collx_file")
                if collx_file:
                    try:
                        collx_df = pd.read_csv(collx_file, encoding="utf-8-sig")
                        collx_df.columns = [c.strip() for c in collx_df.columns]
                        st.caption(f"Found **{len(collx_df):,}** rows. Preview:")
                        st.dataframe(collx_df.head(5), use_container_width=True, hide_index=True)

                        date_range = ""
                        if "order_date" in collx_df.columns:
                            dates4 = collx_df["order_date"].dropna().tolist()
                            if dates4:
                                date_range = f" ({dates4[-1]} → {dates4[0]})"
                        st.caption(f"Date range detected{date_range}")

                        if st.button("⬆️ Import CollX Sales", type="primary", key="sal_collx_btn"):
                            existing_raw4 = _sal_get("?select=dedup_key&source=eq.collx")
                            existing_keys4 = {r["dedup_key"] for r in existing_raw4 if r.get("dedup_key")}

                            imported4 = skipped4 = failed4 = 0
                            prog4 = st.progress(0)
                            total4 = len(collx_df)

                            for idx4, row4 in collx_df.iterrows():
                                prog4.progress(int((idx4 + 1) / max(total4, 1) * 100))
                                order_num4 = str(row4.get("order_number", "") or "").strip()
                                order_date4 = _parse_collx_date(row4.get("order_date", ""))
                                gross4 = _parse_money(row4.get("gross_subtotal", 0))
                                net4 = _parse_money(row4.get("net_proceeds", 0))
                                merch4 = _parse_money(row4.get("merchandise_value", 0))
                                fee4 = round(gross4 - net4, 2)
                                qty4 = int(float(str(row4.get("total_items", 1) or 1)))
                                status4 = str(row4.get("status", "") or "").strip()
                                dedup4 = f"collx|{order_num4}|{order_date4}"

                                if dedup4 in existing_keys4:
                                    skipped4 += 1
                                    continue

                                rec4 = {
                                    "source": "collx",
                                    "order_id": order_num4 or None,
                                    "sale_date": order_date4 or None,
                                    "title": f"CollX order {order_num4} ({qty4} item{'s' if qty4 != 1 else ''})",
                                    "item_number": None,
                                    "quantity": qty4,
                                    "sale_price": merch4,
                                    "shipping_collected": round(gross4 - merch4, 2),
                                    "gross_revenue": gross4,
                                    "platform_fee": fee4,
                                    "net_proceeds": net4,
                                    "status": status4 or "completed",
                                    "dedup_key": dedup4,
                                }
                                res4 = _sal_post(rec4)
                                if res4 is not None:
                                    imported4 += 1
                                    existing_keys4.add(dedup4)
                                else:
                                    failed4 += 1

                            prog4.empty()
                            msg4 = f"✅ Imported **{imported4}** CollX orders"
                            if skipped4:
                                msg4 += f", skipped **{skipped4}** duplicates"
                            if failed4:
                                msg4 += f", **{failed4}** failed"
                            st.success(msg4 + ".")
                            if imported4:
                                st.session_state.pop("sal_data", None)
                                st.rerun()
                    except Exception as e4:
                        st.error(f"Error reading CollX CSV: {e4}")

            # ── Whatnot import ────────────────────────────────────────────────
            with imp_whatnot:
                st.markdown("### Import Whatnot Seller Earnings")
                st.caption(
                    "Accepts the **WhatNot_Seller_Earnings_XXXX.xlsx** format "
                    "(columns: Month, Created Date, Completed Date, Card / Item, Order ID, Listing ID, Net Earnings, Status). "
                    "Net Earnings is already after Whatnot's fee. Re-importing is safe — duplicates skipped."
                )
                wn_file = st.file_uploader("Whatnot Seller Earnings XLSX", type=["xlsx"], key="sal_wn_file")
                if wn_file:
                    try:
                        import openpyxl as _opxl
                        wb5 = _opxl.load_workbook(wn_file, data_only=True)
                        # Find the right sheet — first sheet with 'Sales' in name or first sheet
                        ws5 = None
                        for sn in wb5.sheetnames:
                            if 'sale' in sn.lower() or 'earning' in sn.lower():
                                ws5 = wb5[sn]
                                break
                        if not ws5:
                            ws5 = wb5.active

                        all_rows5 = list(ws5.iter_rows(values_only=True))
                        # Find header row (has 'Order ID' or 'Net Earnings')
                        header_idx5 = None
                        for i, row in enumerate(all_rows5):
                            if any(str(c or '').strip().lower() in ('order id', 'net earnings') for c in row):
                                header_idx5 = i
                                break

                        if header_idx5 is None:
                            st.error("Could not find header row. Expected columns: Month, Created Date, Card / Item, Order ID, Net Earnings, Status.")
                        else:
                            headers5 = [str(c or '').strip().lower() for c in all_rows5[header_idx5]]
                            data_rows5 = all_rows5[header_idx5 + 1:]

                            def _col5(row, name):
                                try: return row[headers5.index(name)]
                                except ValueError: return None

                            # Filter to real sale rows: order id must be non-None and numeric-ish
                            sale_rows5 = [r for r in data_rows5 if _col5(r, 'order id') and str(_col5(r, 'order id') or '').strip().isdigit()]
                            st.caption(f"Found **{len(sale_rows5)}** sales. Preview:")
                            preview5 = [{"Month": _col5(r,'month'), "Date": _col5(r,'created date'), "Card": str(_col5(r,'card / item') or '')[:60], "Order ID": _col5(r,'order id'), "Net $": _col5(r,'net earnings'), "Status": _col5(r,'status')} for r in sale_rows5[:5]]
                            st.dataframe(pd.DataFrame(preview5), use_container_width=True, hide_index=True)

                            if st.button("⬆️ Import Whatnot Sales", type="primary", key="sal_wn_btn"):
                                existing_raw5 = _sal_get("?select=dedup_key&source=eq.whatnot")
                                existing_keys5 = {r["dedup_key"] for r in existing_raw5 if r.get("dedup_key")}
                                imported5 = skipped5 = failed5 = 0
                                prog5 = st.progress(0)

                                for idx5, row5 in enumerate(sale_rows5):
                                    prog5.progress(int((idx5 + 1) / max(len(sale_rows5), 1) * 100))
                                    order_id5 = str(_col5(row5, 'order id') or '').strip()
                                    dedup5 = f"whatnot|{order_id5}"
                                    if dedup5 in existing_keys5:
                                        skipped5 += 1
                                        continue

                                    created5 = _col5(row5, 'created date')
                                    try:
                                        sale_date5 = pd.to_datetime(str(created5)).strftime('%Y-%m-%d') if created5 else None
                                    except Exception:
                                        sale_date5 = str(created5)[:10] if created5 else None

                                    net5 = float(_col5(row5, 'net earnings') or 0)
                                    title5 = str(_col5(row5, 'card / item') or '').strip()[:200]
                                    status5 = str(_col5(row5, 'status') or 'completed').strip()

                                    rec5 = {
                                        "source": "whatnot",
                                        "order_id": order_id5 or None,
                                        "sale_date": sale_date5,
                                        "title": title5 or None,
                                        "item_number": str(_col5(row5, 'listing id') or '').strip() or None,
                                        "quantity": 1,
                                        "sale_price": net5,
                                        "shipping_collected": 0,
                                        "gross_revenue": net5,
                                        "platform_fee": 0,
                                        "net_proceeds": net5,
                                        "status": status5,
                                        "dedup_key": dedup5,
                                    }
                                    res5 = _sal_post(rec5)
                                    if res5 is not None:
                                        imported5 += 1
                                        existing_keys5.add(dedup5)
                                    else:
                                        failed5 += 1

                                prog5.empty()
                                msg5 = f"✅ Imported **{imported5}** Whatnot sales"
                                if skipped5: msg5 += f", skipped **{skipped5}** duplicates"
                                if failed5: msg5 += f", **{failed5}** failed"
                                st.success(msg5 + ".")
                                st.caption("Note: Whatnot Net Earnings is already after their fee — gross and fee are not broken out separately in their export.")
                                if imported5:
                                    st.session_state.pop("sal_data", None)
                                    st.rerun()
                    except Exception as e5:
                        st.error(f"Error reading Whatnot file: {e5}")

            # ── DC Sports import ───────────────────────────────────────────────
            with imp_dc:
                st.markdown("### Import DC Sports Sales")
                st.caption(
                    "Accepts the DC Sports seller CSV export "
                    "(columns: Title, Status, ListingDate, EndingDate, BuyItNow, SalePrice, Fees, Net, FriendlyPackageId). "
                    "Only **Paid** rows are imported as sales. Re-importing is safe — duplicates skipped."
                )
                dc_sal_file = st.file_uploader("DC Sports CSV export", type=["csv"], key="sal_dc_file")
                if dc_sal_file:
                    try:
                        dc_df6 = pd.read_csv(dc_sal_file, encoding="utf-8-sig")
                        dc_df6.columns = [c.strip() for c in dc_df6.columns]
                        paid_df6 = dc_df6[dc_df6.get("Status", dc_df6.iloc[:,1]).astype(str).str.lower() == "paid"].copy() if "Status" in dc_df6.columns else dc_df6
                        st.caption(f"Found **{len(dc_df6):,}** total rows, **{len(paid_df6):,}** Paid (will import as sales).")
                        st.dataframe(paid_df6.head(5), use_container_width=True, hide_index=True)

                        if st.button("⬆️ Import DC Sports Sales", type="primary", key="sal_dc_btn"):
                            existing_raw6 = _sal_get("?select=dedup_key&source=eq.dc_sports")
                            existing_keys6 = {r["dedup_key"] for r in existing_raw6 if r.get("dedup_key")}
                            imported6 = skipped6 = failed6 = 0
                            prog6 = st.progress(0)
                            total6 = len(paid_df6)

                            for idx6, row6 in paid_df6.iterrows():
                                prog6.progress(int((list(paid_df6.index).index(idx6) + 1) / max(total6, 1) * 100))
                                pkg6 = str(row6.get("FriendlyPackageId", "") or "").strip()
                                title6 = str(row6.get("Title", "") or "").strip()
                                ending6 = str(row6.get("EndingDate", "") or "").strip()[:19]
                                dedup6 = f"dc_sports|{pkg6}|{title6}|{ending6}"

                                if dedup6 in existing_keys6:
                                    skipped6 += 1
                                    continue

                                sale_price6 = _parse_money(row6.get("SalePrice"))
                                fees6 = _parse_money(row6.get("Fees"))
                                net6 = _parse_money(row6.get("Net"))
                                try:
                                    sale_date6 = pd.to_datetime(ending6).strftime('%Y-%m-%d') if ending6 else None
                                except Exception:
                                    sale_date6 = ending6[:10] if ending6 else None

                                rec6 = {
                                    "source": "dc_sports",
                                    "order_id": pkg6 or None,
                                    "sale_date": sale_date6,
                                    "title": title6 or None,
                                    "item_number": None,
                                    "quantity": 1,
                                    "sale_price": sale_price6,
                                    "shipping_collected": 0,
                                    "gross_revenue": sale_price6,
                                    "platform_fee": fees6,
                                    "net_proceeds": net6,
                                    "status": "paid",
                                    "dedup_key": dedup6,
                                }
                                res6 = _sal_post(rec6)
                                if res6 is not None:
                                    imported6 += 1
                                    existing_keys6.add(dedup6)
                                else:
                                    failed6 += 1

                            prog6.empty()
                            msg6 = f"✅ Imported **{imported6}** DC Sports sales"
                            if skipped6: msg6 += f", skipped **{skipped6}** duplicates"
                            if failed6: msg6 += f", **{failed6}** failed"
                            st.success(msg6 + ".")
                            if imported6:
                                st.session_state.pop("sal_data", None)
                                st.rerun()
                    except Exception as e6:
                        st.error(f"Error reading DC Sports CSV: {e6}")

            # ── Manual entry ───────────────────────────────────────────────────
            with imp_manual:
                st.markdown("### Manual Sale Entry")
                st.caption("Use for social media sales, cash sales, show sales, or any platform without an export.")

                with st.form("sal_manual_form"):
                    m1, m2, m3 = st.columns(3)
                    m_platform = m1.selectbox("Platform / Channel", ["Social Media", "Facebook", "Instagram", "Card Show", "Whatnot (manual)", "Other"], key="sal_m_platform")
                    m_date = m2.date_input("Sale Date", value=date.today(), key="sal_m_date")
                    m_status = m3.selectbox("Status", ["completed", "pending"], key="sal_m_status")
                    m_title = st.text_input("Card / Item Description *", placeholder="2025 Topps Chrome Aaron Judge #250 PSA 10", key="sal_m_title")
                    m4, m5, m6 = st.columns(3)
                    m_gross = m4.number_input("Gross / Sale Price ($)", min_value=0.0, step=0.01, format="%.2f", key="sal_m_gross")
                    m_fee = m5.number_input("Platform Fee ($)", min_value=0.0, step=0.01, format="%.2f", key="sal_m_fee")
                    m_net = m6.number_input("Net Proceeds ($)", min_value=0.0, step=0.01, format="%.2f", key="sal_m_net",
                                             help="Leave 0 to auto-calc as Gross − Fee")
                    m_submitted = st.form_submit_button("Add Sale", type="primary")

                if m_submitted:
                    if not m_title.strip():
                        st.error("Item description is required.")
                    else:
                        net_m = float(m_net) if m_net else round(float(m_gross) - float(m_fee), 2)
                        src_m = m_platform.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                        dedup_m = f"manual|{src_m}|{m_date}|{m_title.strip()[:40]}|{round(float(m_gross),2)}"
                        rec_m = {
                            "source": "manual",
                            "order_id": None,
                            "sale_date": str(m_date),
                            "title": m_title.strip(),
                            "item_number": None,
                            "quantity": 1,
                            "sale_price": float(m_gross),
                            "shipping_collected": 0,
                            "gross_revenue": float(m_gross),
                            "platform_fee": float(m_fee),
                            "net_proceeds": net_m,
                            "status": m_status,
                            "dedup_key": dedup_m,
                        }
                        res_m = _sal_post(rec_m)
                        if res_m is not None:
                            st.success(f"✅ Added: {m_title.strip()} — net ${net_m:.2f}")
                            st.session_state.pop("sal_data", None)
                            st.rerun()
                        else:
                            st.error("Could not save. Check Supabase connection.")

        st.divider()
        st.markdown("**SQL — Create Sales Table** *(run once in Supabase SQL Editor)*")
        st.code(
            """create table if not exists sales_records (
  id bigint primary key generated always as identity,
  source text not null,
  order_id text,
  sale_date date,
  title text,
  item_number text,
  quantity integer default 1,
  sale_price numeric default 0,
  shipping_collected numeric default 0,
  gross_revenue numeric default 0,
  platform_fee numeric default 0,
  net_proceeds numeric default 0,
  status text,
  dedup_key text unique,
  created_at timestamptz default now()
);
create index if not exists idx_sr_date on sales_records(sale_date);
create index if not exists idx_sr_source on sales_records(source);""",
            language="sql",
        )

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f"""
    <div style="text-align:center; color:#666; font-size:0.78rem; line-height:1.9; padding-bottom:1rem;">
        <strong style="color:#aaa;">Disclaimer</strong><br>
        {APP_NAME} is a research and decision-support tool only. All pricing data (GemRate, eBay)
        is pulled from third-party sources and may be incomplete, delayed, or inaccurate.
        Gem rates and market values fluctuate — always verify data independently before submitting cards for grading.
        All grading decisions and associated costs are solely your responsibility.
        {APP_NAME} assumes no liability for financial outcomes resulting from use of this tool.<br><br>
        ©️ 2026 {APP_NAME}. All rights reserved.
    </div>
    """,
    unsafe_allow_html=True,
)
