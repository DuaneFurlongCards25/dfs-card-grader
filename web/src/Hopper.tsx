import { useEffect, useState } from 'react';
import { API, getToken, num, post } from './api';
import { usd } from './pricing';
import { download, stamp } from './exports';
import { ADD_DEFAULTS, ebayAddCsv } from './ebayAdd';

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
};

const img = (key: string) => `${API}/api/scan/img/${encodeURIComponent(key)}`;
const pairOf = (name: string) => {
  const m = name.match(/-(\d{3})-(front|back)\.jpe?g$/i);
  return m ? { n: +m[1], side: m[2].toLowerCase() } : { n: 0, side: '' };
};

export default function Hopper() {
  const [stacks, setStacks] = useState<{ name: string; photos: number }[]>([]);
  const [photos, setPhotos] = useState<Shot[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [stack, setStack] = useState<string | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [licence, setLicence] = useState('');
  const [degraded, setDegraded] = useState('');

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

  const edit = async (c: Card, field: string, value: string) => {
    try {
      const r = await post('/api/hopper/save', { id: c.id, [field]: value });
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
              <img src={img(c.r2_front)} alt="front" loading="lazy" />
              {c.r2_back && <img src={img(c.r2_back)} alt="back" loading="lazy" />}
            </div>
            <div className="hop-body">
              <input className="hop-title" value={c.title ?? ''}
                     onChange={(e) => setCards((all) => all.map((x) =>
                       x.id === c.id ? { ...x, title: e.target.value } : x))}
                     onBlur={(e) => edit(c, 'title', e.target.value)} />
              <div className="hop-fields">
                {([['year','Year'],['set_name','Set'],['card_number','Card #'],
                   ['parallel','Parallel'],['serial','Serial'],['team','Team'],
                   ['sport','Sport'],['grade','Grade']] as const).map(([f, label]) => (
                  <label key={f} className={unsure.some((u) => u.toLowerCase().includes(f.split('_')[0]))
                                            ? 'flagged' : ''}>
                    {label}
                    <input defaultValue={(c as any)[f] ?? ''}
                           onBlur={(e) => edit(c, f, e.target.value)} />
                  </label>
                ))}
                <label>Price
                  <input defaultValue={price?.toFixed(2) ?? ''}
                         onBlur={(e) => edit(c, 'price', e.target.value)} />
                </label>
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
                  ? <button className="btn sm" onClick={() => edit(c, 'status', 'needs_review')}>
                      Put back
                    </button>
                  : <button className="btn sm read" onClick={() => edit(c, 'status', 'ready')}>
                      ✓ Ready to list
                    </button>}
              </div>
            </div>
          </div>
        );
      })}

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
