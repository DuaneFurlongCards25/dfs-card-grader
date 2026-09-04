"""
DFS Card Scanner — Haystack-style workflow
Upload images → pick correct parallel → comps + trend → export Haystack CSV
"""

import json, os, re, csv, io, time, uuid, threading, traceback
from pathlib import Path
from datetime import datetime

import requests
from flask import Flask, render_template, jsonify, request, send_file

# ── Config ───────────────────────────────────────────────────────────────────

CONFIG_FILE = Path(__file__).parent / 'config.json'

def load_cfg():
    return json.loads(CONFIG_FILE.read_text())

def save_cfg(data):
    CONFIG_FILE.write_text(json.dumps(data, indent=2))

cfg = load_cfg()

CARDHEDGER_KEY = cfg['cardhedger_key']
SUPABASE_URL   = cfg['supabase_url']
SUPABASE_KEY   = cfg['supabase_key']
DEFAULT_PRICE  = float(cfg.get('default_price', 2.49))
BUCKET         = 'company-files'

# Sport → (eBay category, league)
SPORT_MAP = {
    'BASEBALL':   ('261328', 'MLB'),
    'FOOTBALL':   ('183655', 'NFL'),
    'BASKETBALL': ('218116', 'NBA'),
    'SOCCER':     ('261330', ''),
    'HOCKEY':     ('219',    'NHL'),
}

# Exact 84-column Haystack header
HAYSTACK_COLS = [
    '*Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)',
    'CustomLabel','*Category','StoreCategory','*Title','Subtitle',
    'Relationship','*ConditionID','*C:Graded','*C:Sport','*C:Player/Athlete',
    '*C:Parallel/Variety','*C:Manufacturer','C:Season','*C:Features','*C:Set',
    'CD:Grade - (ID: 27502)','*C:League','CD:Professional Grader - (ID: 27501)',
    '*C:Team','*C:Autographed','CD:Card Condition - (ID: 40001)','*C:Card Name',
    '*C:Card Number','CDA:Certification Number - (ID: 27503)','*C:Type',
    'C:Signed By','C:Autograph Authentication','C:Year Manufactured','C:Card Size',
    'C:Country/Region of Manufacturer','C:Material','C:Autograph Format','C:Vintage',
    'C:Original/Licensed Reprint','C:Event/Tournament','C:Language',
    'C:Autograph Authentication Number','C:Bundle Description',
    'C:California Prop 65 Warning','C:Card Thickness','C:Custom Bundle',
    'C:Insert Set','C:Print Run','PicURL','GalleryType','*Description',
    '*Format','*Duration','*StartPrice','BuyItNowPrice','*Quantity',
    'PayPalAccepted','PayPalEmailAddress','ImmediatePayRequired',
    'PaymentInstructions','*Location','PostalCode','ShippingType',
    'ShippingService-1:Option','ShippingService-1:FreeShipping',
    'ShippingService-1:Cost','ShippingService-1:AdditionalCost',
    'ShippingService-2:Option','ShippingService-2:Cost','*DispatchTimeMax',
    'PromotionalShippingDiscount','ShippingDiscountProfileID',
    '*ReturnsAcceptedOption','ReturnsWithinOption','RefundOption',
    'ShippingCostPaidByOption','AdditionalDetails','ShippingProfileName',
    'ReturnProfileName','PaymentProfileName','TakeBackPolicyID',
    'ProductCompliancePolicyID','ScheduleTime','BestOfferEnabled',
    'MinimumBestOfferPrice','BestOfferAutoAcceptPrice','*C:Rookie','*C:Memorabilia',
]
ACTION_COL = HAYSTACK_COLS[0]

# ── State ─────────────────────────────────────────────────────────────────────
# queue  : images being uploaded / identified by CardHedger
# matched: user has confirmed the correct card — comps running in background
# batch  : comps done, ready for export
app     = Flask(__name__)
queue   = []
matched = []
batch   = []
_lock   = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────

def ch_post(endpoint, payload):
    r = requests.post(
        f'https://api.cardhedger.com{endpoint}',
        headers={'X-API-Key': CARDHEDGER_KEY, 'Content-Type': 'application/json'},
        json=payload, timeout=30,
    )
    if r.status_code == 200:
        return r.json()
    raise RuntimeError(f'CardHedger {endpoint} → {r.status_code}: {r.text[:200]}')

def upload_image(image_bytes, filename, content_type='image/jpeg'):
    """Upload to Supabase storage, return (signed_url, storage_path)."""
    storage_path = f"scanner/{int(time.time())}_{filename}"
    r = requests.post(
        f'{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}',
        headers={'Authorization': f'Bearer {SUPABASE_KEY}', 'Content-Type': content_type},
        data=image_bytes, timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f'Supabase upload failed {r.status_code}: {r.text[:200]}')
    sign = requests.post(
        f'{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{storage_path}',
        headers={'Authorization': f'Bearer {SUPABASE_KEY}', 'Content-Type': 'application/json'},
        json={'expiresIn': 31536000}, timeout=15,
    )
    sd = sign.json() if sign.status_code == 200 else {}
    url = sd.get('signedURL') or sd.get('signedUrl') or ''
    if url.startswith('/'):
        url = SUPABASE_URL + url
    if not url:
        raise RuntimeError('No signed URL from Supabase')
    return url, storage_path

def delete_image(storage_path):
    try:
        requests.delete(
            f'{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}',
            headers={'Authorization': f'Bearer {SUPABASE_KEY}'}, timeout=10,
        )
    except Exception:
        pass

def calc_trend(prices_recent, prices_older):
    """Compare two lists of prices. Returns 'up'/'down'/'flat' and pct change."""
    if not prices_recent or not prices_older:
        return 'flat', 0.0
    r = sum(prices_recent) / len(prices_recent)
    o = sum(prices_older)  / len(prices_older)
    if o == 0:
        return 'flat', 0.0
    pct = (r - o) / o * 100
    if pct > 5:
        return 'up',   round(pct, 1)
    if pct < -5:
        return 'down', round(pct, 1)
    return 'flat', round(pct, 1)

def fetch_comps(card_id, grade='Raw'):
    """Fetch two time windows and return pricing + trend."""
    result = {}
    try:
        # Recent window (30 days)
        r30 = ch_post('/v1/cards/comps', {
            'card_id': card_id, 'count': 10, 'grade': grade,
            'time_weighted': True, 'include_raw_prices': True,
        })
        recent_prices = [float(p) for p in (r30.get('raw_prices') or []) if p]
        result.update({
            'comp_price':    r30.get('comp_price'),
            'comp_high':     r30.get('high'),
            'comp_low':      r30.get('low'),
            'recent_sales':  len(recent_prices),
            'recent_prices': recent_prices,
        })

        # Older window (90 days) — for trend comparison
        r90 = ch_post('/v1/cards/comps', {
            'card_id': card_id, 'count': 10, 'grade': grade,
            'time_weighted': False, 'include_raw_prices': True,
        })
        all_prices = [float(p) for p in (r90.get('raw_prices') or []) if p]
        # Prices assumed most-recent first: first half = recent, second half = older
        mid = max(1, len(all_prices) // 2)
        older_prices = all_prices[mid:]

        trend, pct = calc_trend(recent_prices, older_prices)
        result['trend']     = trend
        result['trend_pct'] = pct
    except Exception as e:
        result['comp_note'] = str(e)
        result['trend']     = 'flat'
        result['trend_pct'] = 0.0
    return result

def make_haystack_title(player, year, set_name, number, parallel='', is_rc=False):
    """
    Haystack-style title: Year Set Player #Number Parallel RC
    e.g. '2025 Bowman Chrome Marcelo Mayer #BCP-150 Refractor RC'
    """
    # Clean set name: strip leading year if present
    set_clean = re.sub(r'^\d{4}\s*[-–]?\s*', '', set_name or '').strip()
    # ALL CAPS player name (house style)
    player_tc = (player or '').upper()
    # Skip generic parallel labels
    skip_parallels = {'base', 'base set', '', 'none', 'standard'}
    par = (parallel or '').strip()
    par_str = '' if par.lower() in skip_parallels else par
    # RC tag
    rc_str = 'RC' if is_rc else ''
    parts = [p for p in [year, set_clean, player_tc,
                          f'#{number}' if number else '',
                          par_str, rc_str] if p]
    return ' '.join(parts)[:80]

def make_description(title):
    return (
        '<div style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.6;padding:20px;">'
        f'<h2 style="margin:0 0 12px;font-size:20px;">{title}</h2>'
        '<ul style="margin:0 0 16px;padding-left:20px;">'
        '<li>All cards are scanned — ask if you want additional photos.</li>'
        '<li>Cards over $20 ship with tracking. Patches ship ground to prevent damage.</li>'
        '<li>Cards over $100 include insurance. No returns accepted.</li>'
        '</ul>'
        '<p style="margin:0;color:#374151;">Questions? Ask before buying — happy to help!</p>'
        '</div>'
    )

def is_free_ship(price):
    try:
        return abs(float(price) - 2.49) < 0.005
    except Exception:
        return False

# ── Background processing ─────────────────────────────────────────────────────

def process_identify(card):
    """Phase 1: upload image + run image-match to get candidates."""
    try:
        card['status'] = 'uploading'
        url, path = upload_image(card.pop('_bytes'), card['filename'],
                                 card.pop('_ctype', 'image/jpeg'))
        card['public_url']   = url
        card['storage_path'] = path

        card['status'] = 'identifying'
        res  = ch_post('/v1/cards/image-match', {'image_url': url, 'k': 8})
        best = res.get('best_match') or {}
        candidates = res.get('candidates') or []
        if best and best.get('card_id'):
            candidates = [best] + [c for c in candidates if c.get('card_id') != best.get('card_id')]

        card['candidates'] = [
            {
                'card_id':    c.get('card_id', ''),
                'player':     c.get('player', ''),
                'set':        c.get('set', ''),
                'number':     c.get('number', ''),
                'variant':    c.get('variant', ''),
                'year':       c.get('year', '') or re.search(r'\b(19|20)\d{2}\b', c.get('set','') or '').group() if re.search(r'\b(19|20)\d{2}\b', c.get('set','') or '') else '',
                'similarity': round(float(c.get('similarity') or 0), 1),
                'is_rc':      bool(c.get('rookie') or 'rc' in (c.get('variant') or '').lower()),
            }
            for c in candidates[:8] if c.get('card_id')
        ]
        card['status'] = 'ready'
    except Exception as e:
        card['status'] = 'error'
        card['error']  = str(e)

def process_comps(card):
    """Phase 2: fetch comps + trend for a matched card."""
    card_id = card.get('card_id', '')
    if not card_id:
        card['comp_status'] = 'done'
        return
    try:
        card['comp_status'] = 'running'
        data = fetch_comps(card_id)
        card.update(data)
        # Set suggested price from comps (fall back to default)
        if not card.get('price_locked'):
            raw = card.get('comp_price') or DEFAULT_PRICE
            card['price'] = round(float(raw), 2)
    except Exception as e:
        card['comp_note']   = str(e)
        card['trend']       = 'flat'
        card['trend_pct']   = 0.0
    finally:
        card['comp_status'] = 'done'

# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/state')
def state():
    with _lock:
        return jsonify({
            'queue':   list(queue),
            'matched': list(matched),
            'batch':   list(batch),
        })

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Accept one or more image files, kick off identification for each."""
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'no files'}), 400
    added = []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in {'.jpg','.jpeg','.png','.tif','.tiff','.webp'}:
            continue
        ctype_map = {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png',
                     '.tif':'image/tiff','.tiff':'image/tiff','.webp':'image/webp'}
        card = {
            'id':         str(uuid.uuid4())[:8],
            'filename':   f.filename,
            'status':     'queued',
            'added_at':   datetime.now().strftime('%H:%M:%S'),
            'sport':      'BASEBALL',
            '_bytes':     f.read(),
            '_ctype':     ctype_map.get(ext, 'image/jpeg'),
        }
        with _lock:
            queue.append(card)
        threading.Thread(target=process_identify, args=(card,), daemon=True).start()
        added.append(card['id'])
    return jsonify({'ok': True, 'added': len(added)})

@app.route('/api/confirm-match', methods=['POST'])
def confirm_match():
    """User picked a candidate. Move from queue → matched, kick off comps."""
    data    = request.json
    card_id = data.get('id')
    cand_i  = int(data.get('candidate_index', 0))
    sport   = (data.get('sport') or 'BASEBALL').upper()

    with _lock:
        card = next((c for c in queue if c['id'] == card_id), None)
        if not card:
            return jsonify({'error': 'not found'}), 404
        cands = card.get('candidates', [])
        chosen = cands[cand_i] if cand_i < len(cands) else (cands[0] if cands else {})
        card.update({
            'card_id':  chosen.get('card_id', ''),
            'player':   chosen.get('player', ''),
            'set':      chosen.get('set', ''),
            'number':   chosen.get('number', ''),
            'variant':  chosen.get('variant', ''),
            'year':     chosen.get('year', ''),
            'is_rc':    chosen.get('is_rc', False),
            'sport':    sport,
            'price':    DEFAULT_PRICE,
            'sku':      data.get('sku') or f"DFS-{datetime.now().strftime('%m%d%y')}-{card['id']}",
            'comp_status': 'queued',
        })
        card['title'] = make_haystack_title(
            card['player'], card['year'], card['set'],
            card['number'], card.get('variant', ''), card.get('is_rc', False),
        )
        queue.remove(card)
        matched.append(card)

    threading.Thread(target=process_comps, args=(card,), daemon=True).start()
    return jsonify({'ok': True})

@app.route('/api/update-price', methods=['POST'])
def update_price():
    data    = request.json
    card_id = data.get('id')
    price   = float(data.get('price', DEFAULT_PRICE))
    with _lock:
        for lst in (matched, batch):
            card = next((c for c in lst if c['id'] == card_id), None)
            if card:
                card['price']        = round(price, 2)
                card['price_locked'] = True
                return jsonify({'ok': True})
    return jsonify({'error': 'not found'}), 404

@app.route('/api/move-to-batch', methods=['POST'])
def move_to_batch():
    """Move all matched cards with comps done into the export batch."""
    with _lock:
        ready = [c for c in matched if c.get('comp_status') == 'done']
        for c in ready:
            matched.remove(c)
            batch.append(c)
    return jsonify({'ok': True, 'moved': len(ready)})

@app.route('/api/skip-queue', methods=['POST'])
def skip_queue():
    card_id = request.json.get('id')
    with _lock:
        card = next((c for c in queue if c['id'] == card_id), None)
        if card:
            sp = card.get('storage_path')
            if sp:
                threading.Thread(target=delete_image, args=(sp,), daemon=True).start()
            queue.remove(card)
    return jsonify({'ok': True})

@app.route('/api/remove-batch', methods=['POST'])
def remove_batch():
    card_id = request.json.get('id')
    with _lock:
        card = next((c for c in batch if c['id'] == card_id), None)
        if card:
            batch.remove(card)
    return jsonify({'ok': True})

@app.route('/api/remove-matched', methods=['POST'])
def remove_matched():
    card_id = request.json.get('id')
    with _lock:
        card = next((c for c in matched if c['id'] == card_id), None)
        if card:
            matched.remove(card)
    return jsonify({'ok': True})

@app.route('/api/catalog-search', methods=['POST'])
def catalog_search():
    """Text search fallback — replaces candidate list with search results."""
    data    = request.json
    card_id = data.get('id')
    query   = data.get('query', '').strip()
    if not query:
        return jsonify({'ok': False, 'error': 'no query'})
    with _lock:
        card = next((c for c in queue if c['id'] == card_id), None)
        if not card:
            return jsonify({'ok': False, 'error': 'card not found'})
    try:
        res  = ch_post('/v1/cards/search', {'query': query, 'k': 8})
        hits = res.get('results') or res.get('candidates') or []
        card['candidates'] = [
            {
                'card_id':    h.get('card_id', ''),
                'player':     h.get('player', '') or h.get('name', ''),
                'set':        h.get('set', '') or h.get('set_name', ''),
                'number':     h.get('number', ''),
                'variant':    h.get('variant', '') or h.get('parallel', ''),
                'year':       h.get('year', ''),
                'similarity': round(float(h.get('similarity') or h.get('score') or 0), 1),
                'is_rc':      bool(h.get('rookie')),
            }
            for h in hits[:8] if h.get('card_id')
        ]
        card['status'] = 'ready'
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    return jsonify({'ok': True, 'count': len(card['candidates'])})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    c = load_cfg()
    return jsonify({
        'sku_prefix':           c.get('sku_prefix', 'DFS'),
        'default_price':        c.get('default_price', 2.49),
        'condition_id':         c.get('condition_id', '4000'),
        'condition_desc':       c.get('condition_desc', 'Excellent'),
        'description_template': c.get('description_template', ''),
        'store_categories':     c.get('store_categories', {}),
        'ebay_postal_code':     c.get('ebay_postal_code', ''),
    })

@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    c = load_cfg()
    for key in ('sku_prefix','default_price','condition_id','condition_desc',
                'description_template','store_categories','ebay_postal_code'):
        if key in data:
            c[key] = data[key]
    save_cfg(c)
    return jsonify({'ok': True})

def render_description(template, title, image_url):
    return template.replace('[LISTING_TITLE]', title).replace('[FRONT_IMAGE]', image_url or '')

@app.route('/api/export')
def export():
    with _lock:
        cards = list(batch)

    c        = load_cfg()
    prefix   = c.get('sku_prefix', 'DFS')
    cond_id  = c.get('condition_id', '4000')
    cond_desc = c.get('condition_desc', 'Excellent')
    tmpl     = c.get('description_template', '')
    store_cats = c.get('store_categories', {})
    postal   = c.get('ebay_postal_code', '85250-6312')
    date_str = datetime.now().strftime('%m%d%y')

    buf = io.StringIO()
    info = ['Info','Version=1.0.0','Template=fx_category_template_EBAY_US'] + \
           [''] * (len(HAYSTACK_COLS) - 3)
    csv.writer(buf).writerow(info)

    writer = csv.DictWriter(buf, fieldnames=HAYSTACK_COLS, extrasaction='ignore')
    writer.writeheader()

    for i, card in enumerate(cards, 1):
        sport  = (card.get('sport') or 'BASEBALL').upper()
        cat, league = SPORT_MAP.get(sport, ('261328', 'MLB'))
        price  = float(card.get('price', DEFAULT_PRICE))
        title  = card.get('title', '')
        sku    = card.get('sku') or f"{prefix}-{date_str}-{i:04d}"
        img    = card.get('public_url', '')
        desc   = render_description(tmpl, title, img) if tmpl else make_description(title)
        store_cat = store_cats.get(sport, '') or '0'

        writer.writerow({
            ACTION_COL:                         'Add',
            'CustomLabel':                      sku,
            '*Category':                        cat,
            'StoreCategory':                    store_cat,
            '*Title':                           title,
            '*ConditionID':                     cond_id,
            '*C:Graded':                        'No',
            '*C:Sport':                         sport,
            '*C:Player/Athlete':                card.get('player', ''),
            '*C:Parallel/Variety':              card.get('variant', ''),
            '*C:Set':                           card.get('set', ''),
            '*C:League':                        league,
            '*C:Autographed':                   'No',
            'CD:Card Condition - (ID: 40001)':  cond_desc,
            '*C:Card Number':                   card.get('number', ''),
            '*C:Type':                          'Sports Trading Card',
            '*C:Rookie':                        'Yes' if card.get('is_rc') else '',
            'PicURL':                           img,
            '*Description':                     desc,
            '*Format':                          'FixedPrice',
            '*Duration':                        'GTC',
            '*StartPrice':                      f'{price:.2f}',
            '*Quantity':                        '1',
            'PayPalEmailAddress':               'ImmediatePayRequired',
            'PaymentInstructions':              'United States',
            '*Location':                        'United States',
            'PostalCode':                       postal,
            'ShippingType':                     'Flat',
            'ShippingService-1:Option':         'USPSFirstClass',
            'ShippingService-1:FreeShipping':   '1' if is_free_ship(price) else '0',
            'ShippingService-1:Cost':           '0' if is_free_ship(price) else '',
            '*DispatchTimeMax':                 '3',
            '*ReturnsAcceptedOption':           'ReturnsNotAccepted',
            'PromotionalShippingDiscount':      '',
            'BestOfferEnabled':                 '',
            'MinimumBestOfferPrice':            '',
            'BestOfferAutoAcceptPrice':         '',
            '*C:Memorabilia':                   '',
        })

    filename = f"{prefix}_Scan_{date_str}.csv"
    return send_file(
        io.BytesIO(buf.getvalue().encode('utf-8')),
        mimetype='text/csv', as_attachment=True, download_name=filename,
    )

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('DFS Card Scanner → http://localhost:5100')
    app.run(host='0.0.0.0', port=5100, debug=False)
