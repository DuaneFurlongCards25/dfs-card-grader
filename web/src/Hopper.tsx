import { useEffect, useState } from 'react';
import { API, getToken, num, post } from './api';
import { usd } from './pricing';
import { download, stamp } from './exports';
import { ADD_DEFAULTS, ebayAddCsv } from './ebayAdd';
import { cropToCard } from './cropPhotos';
import { buildCardTitle, FEATURES, PARALLELS, type Attrs } from './cardTitle';

/**
 * eBay's own sold-and-completed search for a card.
 *
 * A link, not a scrape: eBay's terms forbid using their sold data as a
 * price feed, which is why no card app prices off it. Opening the search
 * in a tab is him looking at eBay, which is just browsing.
 */
const soldSearch = (title: string) =>
  `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(title)}` +
  `&_sacat=261328&LH_Sold=1&LH_Complete=1&_sop=13`;

/* ------------------------------------------------------------------ *
 * The Hopper — photographs become listable cards.
 *
 * Three steps, same as any scanning workflow worth using: read the
 * cards, check what was read, send them out. The checking step is the
 * one that cannot be skipped, so it is the one this screen is built
 * around — every field the model was unsure of is marked, and anything
 * below full confidence is held back from the listing file until a
 * person has looked at it.
 * ------------------------------------------------------------------ */

type Shot = { key: string; stack: string; name: string; bytes: number; uploaded: string };
type Card = {
  id: number; idx: number; stack_name: string; r2_front: string; r2_back: string | null;
  player: string | null; title: string | null; year: string | null; set_name: string | null;
  card_number: string | null; parallel: string | null; serial: string | null;
  grader: string | null; grade: string | null; team: string | null; sport: string | null;
  confidence: string | null; unsure: string | null; fmv: string | null;
  price: string | null; sku: string | null; status: string | null;
  is_rookie: boolean | null; is_auto: boolean | null;
  is_memorabilia: boolean | null; is_sp: boolean | null;
  title_locked: boolean | null;
  r2_front_orig: string | null; r2_back_orig: string | null;
  cropped_at: string | null;
};

const img = (key: string) => `${API}/api/scan/img/${encodeURIComponent(key)}`;
const pairOf = (name: string) => {
  const m = name.match(/-(\d{3})-(front|back)\.jpe?g$/i);
  return m ? { n: +m[1], side: m[2].toLowerCase() } : { n: 0, side: '' };
};

/** Marks a field amber when the reader said it was unsure of it. */
const flag = (unsure: string[], field: string) =>
  unsure.some((u) => u.toLowerCase().includes(field)) ? 'flagged' : '';

export default function Hopper() {
  const [stacks, setStacks] = useState<{ name: string; photos: number }[]>([]);
  const [photos, setPhotos] = useState<Shot[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [stack, setStack] = useState<string | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [licence, setLicence] = useState('');
  const [degraded, setDegraded] = useState('');
  const [zoom, setZoom] = useState<string | null>(null);   // a photo, full size

  /**
   * Crop the saved photos to the card, the way the scanning apps do it —
   * shoot the whole frame, crop afterwards in software. Better order:
   * the camera keeps every pixel and the crop can be undone.
   *
   * The original is kept, so Undo is real rather than a reshoot.
   */
  const cropPhotos = async (c: Card) => {
    setBusy(`Cropping card ${c.idx}…`);
    try {
      let changed = 0;
      for (const side of ['front', 'back'] as const) {
        const key = side === 'front' ? c.r2_front : c.r2_back;
        if (!key) continue;
        const blob = await cropToCard(img(key));
        if (!blob) continue;                       // already right; leave it
        const cropped = key.replace(/\.jpe?g$/i, '') + '-crop.jpg';
        const r = await fetch(
          `${API}/api/scan/upload?stack=${encodeURIComponent(c.stack_name)}` +
          `&name=${encodeURIComponent(cropped.split('/').pop()!)}`,
          { method: 'POST',
            headers: { Authorization: `Bearer ${getToken()}`, 'Content-Type': 'image/jpeg' },
            body: blob });
        if (!r.ok) throw new Error((await r.json())?.error || `HTTP ${r.status}`);
        const saved = (await r.json()).key as string;
        await post('/api/hopper/save', {
          id: c.id,
          [side === 'front' ? 'r2_front_orig' : 'r2_back_orig']: key,
          [side === 'front' ? 'r2_front' : 'r2_back']: saved,
          cropped_at: new Date().toISOString(),
        });
        changed++;
      }
      await load();
      setBusy('');
      if (!changed) setError('Those photos are already framed tightly — nothing to crop.');
    } catch (e: any) { setError(e.message || String(e)); setBusy(''); }
  };

  const undoCrop = async (c: Card) => {
    try {
      await post('/api/hopper/save', {
        id: c.id,
        r2_front: c.r2_front_orig ?? c.r2_front,
        r2_back: c.r2_back_orig ?? c.r2_back,
        r2_front_orig: '', r2_back_orig: '', cropped_at: '',
      });
      await load();
    } catch (e: any) { setError(e.message || String(e)); }
  };

  const load = async () => {
    setError('');
    try {
      const h = { Authorization: `Bearer ${getToken()}` };
      const [s, c] = await Promise.all([
        fetch(`${API}/api/scan/list`, { headers: h }).then((r) => r.json()),
        fetch(`${API}/api/hopper/cards`, { headers: h }).then((r) => r.json()),
      ]);
      setStacks(s.stacks ?? []); setPhotos(s.photos ?? []);
      setCards(c.cards ?? []);
      if (!stack && s.stacks?.length) setStack(s.stacks[0].name);
    } catch (e: any) { setError(e.message || String(e)); }
  };
  useEffect(() => { load(); }, []);

  const inStack = photos.filter((p) => p.stack === stack);
  const pairs = new Map<number, { front?: Shot; back?: Shot }>();
  for (const p of inStack) {
    const { n, side } = pairOf(p.name);
    const v = pairs.get(n) ?? {};
    if (side === 'front') v.front = p; else if (side === 'back') v.back = p;
    pairs.set(n, v);
  }
  const list = [...pairs.entries()].sort((a, z) => a[0] - z[0]);
  const byFront = new Map(cards.map((c) => [c.r2_front, c]));

  const unread = list.filter(([, v]) => v.front && !byFront.has(v.front.key));
  const read = list.map(([, v]) => v.front && byFront.get(v.front.key)).filter(Boolean) as Card[];
  const needReview = read.filter((c) => c.status !== 'ready');
  const ready = read.filter((c) => c.status === 'ready');

  const identify = async () => {
    setError(''); setLicence(''); setDegraded('');
    let done = 0;
    for (const [n, v] of list) {
      if (!v.front || byFront.has(v.front.key)) continue;
      setBusy(`Reading card ${n} — ${++done} of ${unread.length}…`);
      try {
        const r = await post('/api/hopper/identify',
          { stack, idx: n, front: v.front.key, back: v.back?.key ?? '' });
        // A degraded read is reported, not swallowed: carrying on quietly
        // with a worse reader is how a whole batch goes out wrong.
        if (r.degraded) setDegraded(r.degraded);
      } catch (e: any) {
        const m = e.message || String(e);
        if (/licence|agree/i.test(m)) { setLicence(m); setBusy(''); return; }
        setError(`Card ${n}: ${m}`); setBusy(''); return;
      }
      await load();
    }
    setBusy('');
  };

  const acceptLicence = async () => {
    setBusy('Accepting…');
    try { await post('/api/ai/accept-licence', {}); setLicence(''); setBusy(''); }
    catch (e: any) { setError(e.message || String(e)); setBusy(''); }
  };

  /**
   * Change an attribute and the title follows — the way Card Luma does
   * it, and the reason a missed parallel is a two-second fix rather than
   * a retyped title.
   *
   * Unless the title has been edited by hand: then it is locked and the
   * attributes stop overwriting his wording.
   */
  const edit = async (c: Card, patch: Partial<Card>) => {
    const next = { ...c, ...patch };
    const body: any = { id: c.id, ...patch };

    if (!next.title_locked && !('title' in patch)) {
      const rebuilt = buildCardTitle(next as Attrs);
      if (rebuilt && rebuilt !== next.title) body.title = rebuilt;
    }
    // Typing in the title box is a decision; stop rewriting it after that.
    if ('title' in patch) body.title_locked = true;

    setCards((all) => all.map((x) => (x.id === c.id ? { ...next, ...body } : x)));
    try {
      const r = await post('/api/hopper/save', body);
      setCards((all) => all.map((x) => (x.id === c.id ? r.card : x)));
    } catch (e: any) { setError(e.message || String(e)); }
  };

  return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Hopper</h1>
      <p className="sub">Photographs in, listable cards out</p>

      {licence && (
        <div className="legend" style={{ borderColor: 'var(--watch)' }}>
          <span style={{ color: 'var(--watch)' }}>
            The card reader needs Meta's community licence accepted on your Cloudflare
            account — once, by you.
          </span>
          <span className="spacer" />
          <a className="btn sm" target="_blank" rel="noreferrer"
             href="https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE">
            Read it ↗
          </a>
          <button className="btn write" onClick={acceptLicence} disabled={!!busy}>
            I accept it
          </button>
        </div>
      )}

      {degraded && (
        <div className="legend" style={{ borderColor: 'var(--watch)' }}>
          <span style={{ color: 'var(--watch)' }}>⚠ {degraded}</span>
          <span className="muted">
            These reads are guesses — check every field before marking any card ready.
          </span>
        </div>
      )}

      {error && (
        <div className="legend" style={{ borderColor: 'var(--danger)' }}>
          <span style={{ color: 'var(--danger)' }}>{error}</span>
          <span className="spacer" /><button className="btn sm" onClick={load}>Reload</button>
        </div>
      )}

      <div className="toolbar">
        <select className="pick" value={stack ?? ''} onChange={(e) => setStack(e.target.value)}>
          {!stacks.length && <option value="">no stacks scanned yet</option>}
          {stacks.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name} — {Math.ceil(s.photos / 2)} cards
            </option>
          ))}
        </select>
        <button className="btn read" onClick={identify} disabled={!!busy || !unread.length}>
          {busy || (unread.length ? `Read ${unread.length} new cards` : 'All read')}
        </button>
        <button className="btn sm" onClick={load}>⟳ Check for scans</button>
        <span className="spacer" />
        <button className="btn" disabled={!read.length || !!busy}
          onClick={async () => { for (const c of read) if (!c.cropped_at) await cropPhotos(c); }}>
          ✂ Crop all photos
        </button>
        <button className="btn write" disabled={!ready.length}
          onClick={() => download(`hopper-list-${stamp()}.csv`, ebayAddCsv(
            ready.map((c) => ({
              sku: c.sku || `${c.stack_name}-${String(c.idx).padStart(3, '0')}`,
              title: c.title || '', price: num(c.price) ?? num(c.fmv),
              sport: c.sport || '', grader: c.grader || '', grade: c.grade || '',
              cert: '', picUrl: img(c.r2_front),
            })), ADD_DEFAULTS))}>
          ⬆ List {ready.length} on eBay
        </button>
      </div>

      <div className="stats">
        <div className="stat"><div className="k">In this stack</div>
          <div className="v">{list.length}</div><div className="n">cards photographed</div></div>
        <div className="stat cool"><div className="k">Not read yet</div>
          <div className="v">{unread.length}</div><div className="n">waiting for the reader</div></div>
        <div className="stat watch"><div className="k">Need checking</div>
          <div className="v">{needReview.length}</div><div className="n">something was unsure</div></div>
        <div className="stat fresh"><div className="k">Ready to list</div>
          <div className="v">{ready.length}</div><div className="n">checked off by you</div></div>
      </div>

      <p className="note" style={{ marginTop: 0 }}>
        A field the reader could not make out is left <b>empty and flagged</b>, never guessed —
        a wrong parallel or year makes a listing that looks right and sells at the wrong price.
        Nothing reaches the listing file until you mark it ready.
      </p>

      {read.map((c) => {
        const conf = num(c.confidence) ?? 0;
        const unsure = (c.unsure || '').split(',').map((x) => x.trim()).filter(Boolean);
        const price = num(c.price) ?? num(c.fmv);
        return (
          <div key={c.id} className={`hop${c.status === 'ready' ? ' ok' : ''}`}>
            <div className="hop-pics">
              {/* Click either one to see it full size — the card number and
                  the parallel are the fields worth checking against the
                  photograph, and both are small print. */}
              <img src={img(c.r2_front)} alt="front" loading="lazy"
                   title="Click to see it full size"
                   onClick={() => setZoom(img(c.r2_front))} />
              {c.r2_back && (
                <img src={img(c.r2_back)} alt="back" loading="lazy"
                     title="Click to see it full size"
                     onClick={() => setZoom(img(c.r2_back!))} />
              )}
              {c.cropped_at
                ? <button className="btn sm" onClick={() => undoCrop(c)}>↶ Undo crop</button>
                : <button className="btn sm" onClick={() => cropPhotos(c)} disabled={!!busy}>
                    ✂ Crop to card
                  </button>}
            </div>
            <div className="hop-body">
              <div className="hop-titlerow">
                <input className="hop-title" value={c.title ?? ''}
                       onChange={(e) => setCards((all) => all.map((x) =>
                         x.id === c.id ? { ...x, title: e.target.value } : x))}
                       onBlur={(e) => edit(c, { title: e.target.value })} />
                <span className={`len${(c.title ?? '').length > 80 ? ' bad' : ''}`}>
                  {(c.title ?? '').length}
                </span>
                {c.title_locked && (
                  <button className="btn sm" title="Let the attributes rebuild it again"
                          onClick={() => edit(c, { title_locked: false })}>
                    🔒 edited
                  </button>
                )}
              </div>

              <div className="attr-label">Card attributes — change one and the title follows</div>
              <div className="hop-fields">
                <label className={flag(unsure, 'year')}>Year
                  <input defaultValue={c.year ?? ''} key={`y${c.id}`}
                         onBlur={(e) => edit(c, { year: e.target.value })} /></label>
                <label className={flag(unsure, 'set')} style={{ gridColumn: 'span 2' }}>Set
                  <input defaultValue={c.set_name ?? ''} key={`s${c.id}`}
                         onBlur={(e) => edit(c, { set_name: e.target.value })} /></label>
                <label className={flag(unsure, 'number')}>Card #
                  <input defaultValue={c.card_number ?? ''} key={`n${c.id}`}
                         onBlur={(e) => edit(c, { card_number: e.target.value })} /></label>
                <label className={flag(unsure, 'parallel')} style={{ gridColumn: 'span 2' }}>
                  Parallel
                  <input list="parallels" defaultValue={c.parallel ?? ''} key={`p${c.id}`}
                         placeholder="base — none printed"
                         onBlur={(e) => edit(c, { parallel: e.target.value })} /></label>
                <label className={flag(unsure, 'serial')}>Serial /
                  <input defaultValue={(c.serial ?? '').replace(/^\//, '')} key={`se${c.id}`}
                         placeholder="not numbered"
                         onBlur={(e) => edit(c, { serial: e.target.value })} /></label>
                <label className={flag(unsure, 'team')}>Team
                  <input defaultValue={c.team ?? ''} key={`t${c.id}`}
                         onBlur={(e) => edit(c, { team: e.target.value })} /></label>
                <label>Grade
                  <input defaultValue={[c.grader, c.grade].filter(Boolean).join(' ')} key={`g${c.id}`}
                         placeholder="raw"
                         onBlur={(e) => {
                           const [gr, ...rest] = e.target.value.trim().split(/\s+/);
                           edit(c, { grader: gr || '', grade: rest.join(' ') || '' });
                         }} /></label>
                <label>Sport
                  <input defaultValue={c.sport ?? ''} key={`sp${c.id}`}
                         onBlur={(e) => edit(c, { sport: e.target.value })} /></label>
                <label>Price $
                  <input defaultValue={price?.toFixed(2) ?? ''} key={`pr${c.id}`}
                         onBlur={(e) => edit(c, { price: e.target.value as any })} /></label>
              </div>

              <div className="chips2">
                {FEATURES.map((f) => {
                  const on = !!(c as any)[f.key];
                  return (
                    <button key={String(f.key)} className={`chip${on ? ' on' : ''}`}
                            onClick={() => edit(c, { [f.key]: !on } as any)}>
                      {f.label}{on ? ' ×' : ''}
                    </button>
                  );
                })}
              </div>

              <div className="hop-foot">
                <span className={`pill ${conf >= 0.8 ? 'fresh' : conf >= 0.5 ? 'watch' : 'stale'}`}>
                  {Math.round(conf * 100)}% sure
                </span>
                {num(c.fmv) !== null && <span className="muted">comp {usd(num(c.fmv)!)}</span>}
                {!!unsure.length && <span className="t-note">unsure: {unsure.join(', ')}</span>}
                <span className="spacer" />
                <a className="btn sm" target="_blank" rel="noreferrer"
                   href={soldSearch(c.title || '')}
                   title="eBay's sold and completed listings for this card">
                  What it sold for ↗
                </a>
                {c.status === 'ready'
                  ? <button className="btn sm" onClick={() => edit(c, { status: 'needs_review' })}>
                      Put back
                    </button>
                  : <button className="btn sm read" onClick={() => edit(c, { status: 'ready' })}>
                      ✓ Ready to list
                    </button>}
              </div>
            </div>
          </div>
        );
      })}

      <datalist id="parallels">
        {PARALLELS.map((p) => <option key={p} value={p} />)}
      </datalist>

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={zoom} alt="" onClick={(e) => e.stopPropagation()} />
          <button className="icon2" onClick={() => setZoom(null)} aria-label="Close">×</button>
          <div className="lb-note">Pinch or scroll to zoom · click outside to close</div>
        </div>
      )}

      {!read.length && !busy && (
        <div className="drop" style={{ cursor: 'default', marginTop: 14 }}>
          <b>Nothing read yet</b>
          <span className="muted">
            {list.length
              ? `${list.length} cards are photographed — press Read to identify them.`
              : 'Scan a stack on your phone, then come back.'}
          </span>
        </div>
      )}
    </>
  );
}
