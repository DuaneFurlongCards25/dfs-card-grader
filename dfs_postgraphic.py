"""Branded "for sale" graphics for Instagram and Facebook.

Charcoal ground, platinum type, hairline rules with a diamond — the same system
as the eBay storefront tiles and the YouTube kit, so every channel reads as one
brand. Pure Pillow, no Streamlit: it takes a card's facts and a photo and
returns PNG bytes, so it can be tested from a script and called from any tab.

Two formats:
  post   1080 x 1350  (4:5, the feed and Facebook)
  story  1080 x 1920  (9:16, with the top and bottom kept clear of the app UI)

Nothing here invents a fact. Every word on the graphic is what the caller
passes in; the only defaults are the brand wordmark and the CTA wording.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
_PLAYFAIR = FONT_DIR / "PlayfairDisplay[wght].ttf"
_JOST = FONT_DIR / "Jost[wght].ttf"

# Brand palette (matches the YouTube brand kit)
BG_TOP, BG_BOT = (22, 27, 36), (14, 17, 23)
PLAT, PLAT_HI, DIM = (198, 206, 218), (238, 243, 250), (138, 148, 166)
INK, RED = (14, 17, 23), (226, 128, 110)

W = 1080
SS = 2                     # draw at 2x, then downsample, for clean edges
STATUSES = ["FOR SALE", "JUST IN", "MAIL DAY PICKUP", "SOLD"]


def _font(path: Path, size: int, wght: int):
    try:
        f = ImageFont.truetype(str(path), size * SS)
        try:
            f.set_variation_by_axes([wght])
        except Exception:
            pass
        return f
    except Exception:
        return ImageFont.load_default()


def display(size, wght=700):
    return _font(_PLAYFAIR, size, wght)


def label(size, wght=500):
    return _font(_JOST, size, wght)


def _tw(font, text, spacing=0):
    """Width of text with letter spacing (px at 1x)."""
    if not text:
        return 0
    w = sum(font.getlength(ch) for ch in text) if spacing else font.getlength(text)
    return w / SS + spacing * (len(text) - 1 if spacing else 0)


def _text(d, xy, text, font, fill, spacing=0, anchor="l"):
    """Draw text at 1x coords. anchor: l / r / m, baseline-aligned."""
    x, y = xy
    w = _tw(font, text, spacing)
    if anchor == "r":
        x -= w
    elif anchor == "m":
        x -= w / 2
    if not spacing:
        d.text((x * SS, y * SS), text, font=font, fill=fill, anchor="ls")
        return
    cx = x
    for ch in text:
        d.text((cx * SS, y * SS), ch, font=font, fill=fill, anchor="ls")
        cx += font.getlength(ch) / SS + spacing


def _wrap(font, text, max_w, spacing=0):
    lines, cur = [], ""
    for word in text.split():
        t = f"{cur} {word}".strip()
        if _tw(font, t, spacing) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def money(v) -> str:
    try:
        n = float(re.sub(r"[^0-9.]", "", str(v)))
    except ValueError:
        return str(v or "").strip()
    return f"${n:,.0f}" if n == int(n) else f"${n:,.2f}"


def _diamond(d, cx, cy, r, fill):
    d.polygon([(cx * SS, (cy - r) * SS), ((cx + r) * SS, cy * SS),
               (cx * SS, (cy + r) * SS), ((cx - r) * SS, cy * SS)], fill=fill)


def _rule(d, x0, x1, y):
    mid = (x0 + x1) / 2
    c = (*PLAT, 140)
    d.line([(x0 * SS, y * SS), ((mid - 14) * SS, y * SS)], fill=c, width=2 * SS // 2 + 1)
    d.line([((mid + 14) * SS, y * SS), (x1 * SS, y * SS)], fill=c, width=2 * SS // 2 + 1)
    _diamond(d, mid, y, 7, PLAT)


def _ground(h):
    """Charcoal gradient, soft key light upper-left, faint film grain."""
    hh, ww = h * SS, W * SS
    t = np.linspace(0, 1, hh)[:, None]
    base = np.array(BG_TOP)[None, None, :] * (1 - t[..., None]) + np.array(BG_BOT)[None, None, :] * t[..., None]
    base = np.repeat(base, ww, axis=1)
    yy, xx = np.mgrid[0:hh, 0:ww]
    cx, cy = ww * 0.22, hh * (0.10 if h < 1500 else 0.07)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (W * SS * 1.0)
    glow = np.clip(1 - dist, 0, 1) ** 2 * 0.13
    base = base + (np.array(PLAT)[None, None, :] - base) * glow[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype("uint8"), "RGB")
    noise = Image.effect_noise((ww, hh), 48).convert("RGB")
    return Image.blend(img, noise, 0.035)


def _load_photo(photo):
    if photo is None:
        return None
    if isinstance(photo, Image.Image):
        return photo.convert("RGB")
    if isinstance(photo, (bytes, bytearray)):
        return Image.open(io.BytesIO(photo)).convert("RGB")
    try:
        return Image.open(photo).convert("RGB")
    except Exception:
        return None


def render_post(*, name: str, setline: str = "", price="", chips=None,
                status: str = "FOR SALE", handle: str = "@duanefurlongcards",
                terms: str = "", photo=None, fmt: str = "post") -> bytes:
    """Return PNG bytes for one card."""
    story = fmt == "story"
    H = 1920 if story else 1350
    sold = status == "SOLD"
    name = (name or "").upper().strip()
    chips = [c.strip() for c in (chips or []) if c and c.strip()][:5]
    price_s = money(price)
    M = 90
    pad_t, pad_b = (250, 270) if story else (64, 64)

    img = _ground(H).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([28 * SS, 28 * SS, (W - 28) * SS, (H - 28) * SS],
                outline=(*PLAT, 46), width=2 * SS)

    # header
    y = pad_t + 34
    f_dfs = display(46)
    _text(d, (M, y), "DFS", f_dfs, PLAT_HI, spacing=2)
    _text(d, (M + _tw(f_dfs, "DFS", 2) + 18, y - 2), "CARDS", label(22, 500), PLAT, spacing=5)
    _text(d, (W - M, y - 2), status, label(26, 600), RED if sold else PLAT_HI,
          spacing=7, anchor="r")
    _rule(d, M, W - M, pad_t + 70)

    # photo
    info_h = 360 if story else 330
    cta_h = 120 if story else 112
    gap = 30
    py0 = pad_t + 112
    py1 = H - pad_b - cta_h - info_h - gap * 2
    bh = py1 - py0
    bw = W - 2 * M
    ph = _load_photo(photo)
    if ph is not None:
        s = min((bw - 24) / ph.width, (bh - 24) / ph.height)
        iw, ih = int(ph.width * s * SS), int(ph.height * s * SS)
        ph = ph.resize((iw, ih), Image.LANCZOS)
        ix = int(M * SS + (bw * SS - iw) / 2)
        iy = int(py0 * SS + (bh * SS - ih) / 2)
        # soft platinum glow behind, then a drop shadow
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse(
            [ix - 60 * SS, iy - 40 * SS, ix + iw + 60 * SS, iy + ih + 40 * SS],
            fill=(*PLAT, 26))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(60 * SS)))
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle([ix, iy + 24 * SS, ix + iw, iy + ih + 24 * SS],
                                     fill=(0, 0, 0, 190))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26 * SS)))
        img.paste(ph, (ix, iy))
        if sold:
            veil = Image.new("RGBA", (iw, ih), (*INK, 115))
            img.alpha_composite(veil, (ix, iy))
        d = ImageDraw.Draw(img, "RGBA")
    else:
        d.rectangle([(M + 60) * SS, (py0 + 20) * SS, (W - M - 60) * SS, (py1 - 20) * SS],
                    outline=DIM, width=2 * SS)
        _text(d, (W / 2, py0 + bh / 2), "ADD A CARD PHOTO", label(30, 400), DIM,
              spacing=4, anchor="m")

    # info block
    iy0 = py1 + gap
    pf = 132 if story else 124
    f_price = display(pf)
    while _tw(f_price, price_s) > 400 and pf > 60:
        pf -= 4
        f_price = display(pf)
    pw = _tw(f_price, price_s)
    _text(d, (W - M, iy0 + pf * 0.82), price_s, f_price, DIM if sold else PLAT_HI, anchor="r")
    if sold:
        d.line([((W - M - pw - 6) * SS, (iy0 + pf * 0.5) * SS),
                ((W - M + 6) * SS, (iy0 + pf * 0.4) * SS)], fill=RED, width=5 * SS)
    _text(d, (W - M + 6, iy0 + pf * 0.82 + 34), "SOLD AT" if sold else "ASKING",
          label(20, 500), DIM, spacing=6, anchor="r")

    name_w = W - 2 * M - max(pw, 170) - 36
    nf, lines = 68, []
    while nf >= 38:
        f_name = display(nf)
        lines = _wrap(f_name, name, name_w)
        if len(lines) <= 2:
            break
        nf -= 2
    f_name = display(nf)
    ny = iy0 + nf * 0.85
    for i, ln in enumerate(lines[:2]):
        _text(d, (M, ny + i * nf * 1.12), ln, f_name, PLAT_HI)
    cy = ny + (min(len(lines), 2) - 1) * nf * 1.12 + 44
    f_set = label(32, 400)
    sl = _wrap(f_set, (setline or "").upper(), name_w, spacing=1.5)[:2]
    for i, ln in enumerate(sl):
        _text(d, (M, cy + i * 40), ln, f_set, PLAT, spacing=1.5)
    cy += (len(sl) - 1) * 40

    chip_y = max(cy + 30, iy0 + info_h - 96)
    f_chip = label(24, 500)
    cx = M
    for t in chips:
        t = t.upper()
        w = _tw(f_chip, t, 1) + 44
        if cx + w > W - M:
            break
        d.rounded_rectangle([cx * SS, chip_y * SS, (cx + w) * SS, (chip_y + 52) * SS],
                            radius=26 * SS, outline=(*PLAT, 150), width=2 * SS)
        _text(d, (cx + 22, chip_y + 34), t, f_chip, PLAT_HI, spacing=1)
        cx += w + 14
    if terms:
        _text(d, (M, iy0 + info_h - 6), terms.upper(), label(22, 400), DIM, spacing=2)

    # CTA bar
    cy0 = H - pad_b - cta_h
    bar = Image.new("RGBA", ((W - 2 * M) * SS, cta_h * SS))
    px = np.zeros((cta_h * SS, (W - 2 * M) * SS, 4), dtype="uint8")
    stops = ([(0, (42, 49, 64)), (1, (29, 35, 48))] if sold else
             [(0, PLAT_HI), (0.55, PLAT), (1, (170, 179, 193))])
    ts = np.linspace(0, 1, cta_h * SS)
    for ch in range(3):
        px[..., ch] = np.interp(ts, [s[0] for s in stops], [s[1][ch] for s in stops])[:, None]
    px[..., 3] = 255
    bar = Image.fromarray(px, "RGBA")
    img.alpha_composite(bar, (M * SS, cy0 * SS))
    d = ImageDraw.Draw(img, "RGBA")
    cta = "SOLD. THANKS!" if sold else f"DM {(handle or '@duanefurlongcards').upper()} TO CLAIM"
    cf = 36 if story else 34
    while _tw(label(cf, 600), cta, 5) > W - 2 * M - 120 and cf > 22:
        cf -= 2
    ink = PLAT if sold else INK
    _text(d, (W / 2, cy0 + cta_h / 2 + cf * 0.34), cta, label(cf, 600), ink,
          spacing=5, anchor="m")
    for x in (M + 30, W - M - 30):
        _diamond(d, x, cy0 + cta_h / 2, 7, ink)

    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ─── Helpers that read inventory cards ───────────────────────────────────────

def chips_for(card: dict) -> list:
    """Tags drawn from fields the card record actually has — never guessed."""
    chips = []
    serial = str(card.get("serial") or card.get("print_run") or "").strip()
    if serial:
        chips.append(serial if "/" in serial else f"/{serial}")
    blob = " ".join(str(card.get(k) or "") for k in
                    ("title", "parallel", "set_name", "subset")).lower()
    if re.search(r"\bauto(graph)?s?\b", blob):
        chips.append("Auto")
    if re.search(r"\b(rc|rookie)\b", blob) or card.get("rookie"):
        chips.append("RC")
    if card.get("grade"):
        chips.append(" ".join(x for x in [card.get("grader"), card.get("grade")] if x))
    if card.get("team"):
        chips.append(str(card["team"]))
    return chips[:5]


def setline_for(card: dict) -> str:
    # "Base" is the scanner saying there is NO parallel. Printed under a
    # player's name on a sale graphic it reads as a feature of the card, and
    # it pushed the Okamoto render onto two lines to say nothing.
    par = str(card.get("parallel") or "").strip()
    if par.lower() in {"base", "none", "n/a"}:
        par = ""
    bits = [card.get("year"), card.get("set_name"),
            f"#{card['card_number']}" if card.get("card_number") else None,
            par]
    s = " ".join(str(b).strip() for b in bits if b and str(b).strip())
    return s or str(card.get("title") or "")


# ─── Hype style ──────────────────────────────────────────────────────────────
#
# The second look, built to Duane's reference: the format the hobby's eye is
# already trained on. Price as the headline, the card floating on a glow,
# spec chips in a row, a bright call-to-action bar across the bottom.
#
# Loud is the point. The luxury style above says expensive quietly and stands
# out precisely because it is unlike everything else in the feed; this one
# stops a thumb because it looks like what a buyer already associates with a
# card for sale. Which actually sells is a question for a week of posting,
# not for either of us to guess — hence both.
#
# The accent follows the card's team when one is known, so a Hornets card
# comes out teal and a Lakers card purple. A graphic in the team's own colours
# reads as made for that card rather than stamped out.

TEAM_ACCENT = {
    # NBA
    "hornets": ((0, 120, 140), (29, 17, 96)), "lakers": ((253, 185, 39), (85, 37, 130)),
    "warriors": ((253, 185, 39), (29, 66, 138)), "celtics": ((0, 122, 51), (139, 111, 78)),
    "bulls": ((206, 17, 65), (6, 25, 34)), "knicks": ((245, 132, 38), (0, 107, 182)),
    "heat": ((152, 0, 46), (249, 160, 27)), "spurs": ((196, 206, 211), (6, 25, 34)),
    "nuggets": ((255, 198, 39), (13, 34, 64)), "timberwolves": ((35, 97, 146), (120, 190, 32)),
    "rockets": ((206, 17, 65), (6, 25, 34)), "nets": ((255, 255, 255), (6, 25, 34)),
    "magic": ((0, 125, 197), (196, 206, 211)), "pistons": ((200, 16, 46), (29, 66, 138)),
    "76ers": ((0, 107, 182), (237, 23, 76)), "grizzlies": ((93, 118, 169), (18, 23, 60)),
    "pacers": ((253, 187, 48), (0, 45, 98)), "trail blazers": ((224, 58, 62), (6, 25, 34)),
    "jazz": ((0, 43, 92), (249, 160, 27)), "hawks": ((225, 68, 52), (38, 40, 42)),
    "wizards": ((0, 43, 92), (227, 24, 55)), "mavericks": ((0, 83, 188), (0, 43, 92)),
    # MLB
    "dodgers": ((0, 90, 156), (239, 62, 66)), "yankees": ((12, 35, 64), (196, 206, 211)),
    "blue jays": ((19, 74, 142), (232, 41, 28)), "red sox": ((189, 48, 57), (12, 35, 64)),
    "cubs": ((14, 51, 134), (204, 52, 51)), "braves": ((206, 17, 65), (19, 39, 79)),
    "guardians": ((228, 0, 43), (12, 35, 64)), "pirates": ((253, 184, 39), (27, 27, 27)),
    "royals": ((0, 70, 135), (189, 155, 96)), "reds": ((198, 1, 31), (27, 27, 27)),
    "rays": ((9, 44, 92), (139, 211, 230)), "brewers": ((255, 197, 47), (18, 40, 75)),
    "white sox": ((39, 37, 31), (196, 206, 211)), "angels": ((186, 0, 33), (0, 50, 99)),
}
HYPE_DEFAULT = ((0, 183, 206), (247, 110, 36))     # teal + orange, the reference
HYPE_INK = (10, 12, 16)


def _accent_for(team: str):
    t = (team or "").lower()
    for k, v in TEAM_ACCENT.items():
        if k in t:
            return v
    return HYPE_DEFAULT


def _hype_ground(h, accent, second):
    """Near-black with diagonal light streaks in the accent colours."""
    hh, ww = h * SS, W * SS
    img = Image.new("RGB", (ww, hh), HYPE_INK)
    d = ImageDraw.Draw(img, "RGBA")
    # Corner washes, so the middle stays dark enough for the card to read.
    for (cx, cy, col, rad, al) in (
            (0.08, 0.10, accent, 0.72, 52), (0.95, 0.06, second, 0.55, 46),
            (0.04, 0.95, second, 0.52, 34), (0.97, 0.92, accent, 0.60, 40)):
        g = Image.new("RGBA", (ww, hh), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse([cx * ww - rad * ww, cy * hh - rad * ww,
                                   cx * ww + rad * ww, cy * hh + rad * ww],
                                  fill=(*col, al))
        img.paste(Image.alpha_composite(img.convert("RGBA"),
                                        g.filter(ImageFilter.GaussianBlur(120 * SS))).convert("RGB"))
    # Speed lines top-left and bottom-right.
    for i in range(7):
        o = i * 46 * SS
        d.line([(-60 * SS + o, 0), (260 * SS + o, hh * 0.42)],
               fill=(*accent, 44 if i % 2 else 26), width=(5 if i % 2 else 3) * SS)
        d.line([(ww - 240 * SS + o, hh), (ww + 60 * SS + o, hh * 0.62)],
               fill=(*second, 40 if i % 2 else 22), width=(5 if i % 2 else 3) * SS)
    # Dot grids, the small texture the reference uses in its corners.
    for (x0, y0) in ((ww * 0.80, hh * 0.17), (ww * 0.08, hh * 0.74)):
        for r in range(5):
            for c in range(7):
                d.ellipse([x0 + c * 15 * SS, y0 + r * 15 * SS,
                           x0 + c * 15 * SS + 4 * SS, y0 + r * 15 * SS + 4 * SS],
                          fill=(*accent, 70))
    return img


def render_hype(*, name: str, setline: str = "", price="", chips=None,
                status: str = "FOR SALE", handle: str = "@duanefurlongcards",
                team: str = "", photo=None, fmt: str = "post",
                cta: str = "DM TO CLAIM / BUY NOW", footnote: str = "") -> bytes:
    """The loud style: price headline, card on a glow, chips, CTA bar."""
    story = fmt == "story"
    H = 1920 if story else 1350
    accent, second = _accent_for(team)
    sold = status == "SOLD"
    name = (name or "").upper().strip()
    chips = [c.strip() for c in (chips or []) if c and c.strip()][:4]
    M = 72
    pad_t, pad_b = (210, 230) if story else (54, 54)

    img = _hype_ground(H, accent, second).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")

    # ── headline: the price, because that is what the reference leads with
    head = f"{'SOLD' if sold else status}:"
    f_head = label(78 if story else 72, 700)
    f_price = label(104 if story else 96, 700)
    base = pad_t + (96 if story else 88)          # baseline, not the top
    hw = _tw(f_head, head, 2) + 22 + _tw(f_price, money(price), 0)
    x = max(M, (W - hw) // 2)
    _text(d, (x, base), head, f_head, (255, 255, 255), spacing=2)
    _text(d, (x + _tw(f_head, head, 2) + 22, base), money(price), f_price, accent)
    y = base

    # ── the card, floating on an accent glow
    info_h = 300 if story else 286
    cta_h = 104
    py0 = y + (150 if story else 138)
    py1 = H - pad_b - cta_h - info_h - 26
    bw, bh = W - 2 * M, py1 - py0
    ph = _load_photo(photo)
    if ph is not None and bh > 80:
        s = min((bw - 40) / ph.width, (bh - 20) / ph.height)
        iw, ih = int(ph.width * s * SS), int(ph.height * s * SS)
        ph = ph.resize((iw, ih), Image.LANCZOS)
        ix = int(M * SS + (bw * SS - iw) / 2)
        iy = int(py0 * SS + (bh * SS - ih) / 2)
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse(
            [ix - 90 * SS, iy - 60 * SS, ix + iw + 90 * SS, iy + ih + 60 * SS],
            fill=(*accent, 78))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(85 * SS)))
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle([ix, iy + 26 * SS, ix + iw, iy + ih + 26 * SS],
                                     fill=(0, 0, 0, 205))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(30 * SS)))
        img.paste(ph, (ix, iy))

    # ── name, set line, chips
    iy = H - pad_b - cta_h - info_h + 64          # first baseline
    f_name = label(72 if story else 66, 700)
    for ln in _wrap(f_name, name, W - 2 * M, 1)[:2]:
        _text(d, (W // 2, iy), ln, f_name, (255, 255, 255), spacing=1, anchor="m")
        iy += 74
    if setline:
        f_set = label(36, 600)
        for ln in _wrap(f_set, setline.upper(), W - 2 * M, 2)[:2]:
            _text(d, (W // 2, iy), ln, f_set, accent, spacing=2, anchor="m")
            iy += 46
    if chips:
        f_chip = label(30, 600)
        line = "   |   ".join(c.upper() for c in chips)
        while _tw(f_chip, line, 1) > W - 2 * M and len(chips) > 1:
            chips = chips[:-1]                     # drop the least important
            line = "   |   ".join(c.upper() for c in chips)
        iy += 34
        _text(d, (W // 2, iy), line, f_chip, (255, 255, 255), spacing=1, anchor="m")
        iy += 18
    if footnote:
        iy += 30
        _text(d, (W // 2, iy), footnote.upper(), label(24, 500), (*PLAT, 190),
              spacing=4, anchor="m")

    # ── call to action
    by = H - pad_b - cta_h
    bar = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle(
        [M * SS, by * SS, (W - M) * SS, (by + 74) * SS], radius=12 * SS,
        fill=(*second, 255))
    img.alpha_composite(bar)
    _text(d, (W // 2, by + 50), cta.upper(), label(36, 700), (255, 255, 255),
          spacing=3, anchor="m")
    _text(d, (W // 2, by + 98), handle.upper(), label(24, 500), (*PLAT, 210),
          spacing=5, anchor="m")

    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


STYLES = {"luxury": render_post, "hype": render_hype}
