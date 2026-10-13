"""Streamlit pieces for the branded post graphics.

Kept out of app.py on purpose (it is already 16,000 lines). app.py calls
`render(...)` from the Instagram tab; everything else lives here.

The lot-payoff goal is read from sales_records, not typed in a second place:
every sale logged anywhere in the app (eBay import, claim sales, manual) counts
toward it, so there is one set of books. Net proceeds are used when the sale
has them, because a goal is about cash left after fees.
"""

from __future__ import annotations

import ssl
import urllib.request
from datetime import date

import streamlit as st

import dfs_postgraphic as pg

GOAL_LOT1 = 3500.0
GOAL_LOT2 = 250.0
GOAL_START = date(2026, 10, 12)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_image(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return urllib.request.urlopen(req, context=ssl.create_default_context(),
                                      timeout=30).read()
    except Exception:
        return None


def _sales(neon_get):
    """Sales rows, fetched once per couple of minutes. Streamlit runs every tab's
    body on every click, so an uncached Neon call here would slow the whole
    claim-sale screen."""
    import time
    hit = st.session_state.get("_pm_sales")
    if hit and time.time() - hit[0] < 180:
        return hit[1]
    rows = neon_get("sales_records", "?order=sale_date.desc&limit=3000") or []
    st.session_state["_pm_sales"] = (time.time(), rows)
    return rows


def goal_panel(neon_get, key: str):
    """Progress toward paying off the two lots, from real sales."""
    with st.expander("🎯 Lot payoff goal", expanded=True):
        g1, g2, g3 = st.columns(3)
        lot1 = g1.number_input("Lot 1 ($)", 0.0, value=GOAL_LOT1, step=50.0, key=f"{key}_g1")
        lot2 = g2.number_input("Lot 2 ($)", 0.0, value=GOAL_LOT2, step=50.0, key=f"{key}_g2")
        since = g3.date_input("Count sales since", value=GOAL_START, key=f"{key}_gs")

        rows = _sales(neon_get)
        got, n = 0.0, 0
        for r in rows:
            if str(r.get("sale_date") or "")[:10] < str(since):
                continue
            if str(r.get("status") or "completed").lower() in ("cancelled", "canceled", "returned"):
                continue
            amt = r.get("net_proceeds")
            if amt in (None, ""):
                amt = r.get("gross_revenue")
            if amt in (None, ""):
                amt = float(r.get("sale_price") or 0) * float(r.get("quantity") or 1)
            got += float(amt or 0)
            n += 1

        total = lot1 + lot2
        a, b = min(got, lot1), min(max(got - lot1, 0.0), lot2)
        m1, m2, m3 = st.columns(3)
        m1.metric("Raised", f"${got:,.0f}", f"{n} sale(s)", delta_color="off")
        m2.metric("To go", f"${max(total - got, 0):,.0f}")
        m3.metric("Goal", f"${total:,.0f}")
        st.progress(min(a / lot1, 1.0) if lot1 else 1.0,
                    text=f"Lot 1: ${a:,.0f} of ${lot1:,.0f}")
        st.progress(min(b / lot2, 1.0) if lot2 else 1.0,
                    text=f"Lot 2: ${b:,.0f} of ${lot2:,.0f}")
        if st.button("Refresh", key=f"{key}_grf"):
            st.session_state.pop("_pm_sales", None)
            st.rerun()
        st.caption("Counts net proceeds from Sales & P&L since the date above — fees "
                   "already out. Sales log themselves from Claims & totals; add any "
                   "other sale in Sales & P&L → Import → Manual.")


def _controls(key: str, default_handle: str):
    c0, c1, c2, c3 = st.columns([1.1, 1, 1, 1.4])
    style = c0.radio("Style", ["hype", "luxury"], horizontal=True,
                     key=f"{key}_style",
                     format_func=lambda v: "🔥 Hype" if v == "hype" else "💎 Luxury",
                     help="Hype is the loud format the hobby's eye is trained on — "
                          "price headline, team colours, claim bar. Luxury is the "
                          "quiet platinum look that stands out by being unlike "
                          "everything else in the feed. Post both for a week and "
                          "let the DMs decide.")
    fmt = c1.radio("Format", ["post", "story"], horizontal=True, key=f"{key}_fmt",
                   format_func=lambda v: "Post 4:5" if v == "post" else "Story 9:16")
    status = c2.selectbox("Status", pg.STATUSES, key=f"{key}_status")
    terms = c3.text_input("Fine print", "Ships in a box with UPS, insured",
                          key=f"{key}_terms")
    return fmt, status, terms, style


def _make(style, *, team="", terms="", **kw):
    """Call whichever renderer is selected; they take slightly different extras."""
    if style == "hype":
        return pg.render_hype(team=team, footnote=terms, **kw)
    return pg.render_post(terms=terms, **kw)


def _show(png: bytes, name: str, fmt: str, key: str, style: str = ""):
    st.image(png, width=360)
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")[:40] or "card"
    st.download_button("⬇️ Download PNG", png,
                       file_name=f"dfs-{slug}-{style or 'post'}-{fmt}.png",
                       mime="image/png", key=key, use_container_width=True)


def card_graphics(picked, price_of, handle: str, key: str):
    """One branded graphic per picked card."""
    st.markdown("#### 🖼️ Branded graphics")
    st.caption("Same look as the store and YouTube. Uses the card's front photo from "
               "Inventory; upload a different shot if you want to override it.")
    fmt, status, terms, style = _controls(f"{key}_pm", handle)
    for c in picked:
        sku = c["sku"]
        title = c.get("title") or sku
        with st.expander(f"{title} — ${float(price_of(c) or 0):,.0f}"):
            e1, e2 = st.columns(2)
            nm = e1.text_input("Name on graphic", c.get("player") or title,
                               key=f"{key}_pm_n_{sku}")
            sl = e2.text_input("Set line", pg.setline_for(c), key=f"{key}_pm_s_{sku}")
            tg = st.text_input("Tags (comma separated)", ", ".join(pg.chips_for(c)),
                               key=f"{key}_pm_t_{sku}")
            up = st.file_uploader("Photo override", type=["jpg", "jpeg", "png", "webp"],
                                  key=f"{key}_pm_u_{sku}")
            if st.button("Make graphic", key=f"{key}_pm_b_{sku}", type="primary"):
                photo = up.getvalue() if up else None
                if photo is None:
                    imgs = c.get("images") or []
                    photo = _fetch_image(imgs[0]) if imgs else None
                if photo is None:
                    st.warning("No photo found for this card. Upload one above.")
                st.session_state[f"{key}_pm_png_{sku}"] = _make(
                    style, name=nm, setline=sl, price=price_of(c),
                    chips=[t for t in tg.split(",")], status=status,
                    handle=handle, terms=terms, photo=photo, fmt=fmt,
                    team=str(c.get("team") or ""))
            png = st.session_state.get(f"{key}_pm_png_{sku}")
            if png:
                _show(png, nm, fmt, f"{key}_pm_d_{sku}", style)


def manual_builder(handle: str, key: str):
    """For a card that is not in Inventory yet."""
    with st.expander("➕ Card not in Inventory? Make a graphic from a photo"):
        fmt, status, terms, style = _controls(f"{key}_mb", handle)
        up = st.file_uploader("Card photo", type=["jpg", "jpeg", "png", "webp"],
                              key=f"{key}_mb_up")
        e1, e2 = st.columns(2)
        nm = e1.text_input("Player name", key=f"{key}_mb_n")
        pr = e2.text_input("Price ($)", key=f"{key}_mb_p")
        sl = st.text_input("Year, set, number, parallel", key=f"{key}_mb_s",
                           placeholder="2025 Topps Inception Rookie Auto /99")
        tg = st.text_input("Tags (comma separated, up to 5)", key=f"{key}_mb_t",
                           placeholder="27/99, On-card auto, RC, Hornets")
        if st.button("Make graphic", key=f"{key}_mb_b", type="primary"):
            if not nm or not pr:
                st.warning("Add a player name and a price.")
            else:
                st.session_state[f"{key}_mb_png"] = _make(
                    style, name=nm, setline=sl, price=pr, chips=tg.split(","),
                    status=status, handle=handle, terms=terms,
                    photo=up.getvalue() if up else None, fmt=fmt,
                    team=st.session_state.get(f"{key}_mb_team", ""))
        png = st.session_state.get(f"{key}_mb_png")
        if png:
            _show(png, nm or "card", fmt, f"{key}_mb_d", style)


def render(picked, price_of, neon_get, key: str):
    goal_panel(neon_get, key)
    handle = st.text_input("Instagram handle on graphics", "@duanefurlongcards",
                           key=f"{key}_pm_handle")
    manual_builder(handle, key)
    if picked:
        card_graphics(picked, price_of, handle, key)
