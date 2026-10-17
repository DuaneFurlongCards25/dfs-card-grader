import { useMemo, useRef, useState, useEffect } from 'react';
import { type Listing, num, text } from './api';

/* ------------------------------------------------------------------ *
 * Inventory — the one screen that is the app.
 *
 * Every listing is already in the browser, so filtering, searching and
 * sorting happen in memory with nothing to wait for. That is the whole
 * difference from Streamlit, where each of these was a server round trip.
 *
 * Rows are windowed: 4,500 <div>s would make scrolling stutter, so only
 * the visible slice is rendered.
 * ------------------------------------------------------------------ */

const ROW = 44;
const money = (n: number | null) =>
  n === null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
const money0 = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

/**
 * Days since the listing went up. eBay renews monthly; start_date is the
 * original, which is the number that actually tells you a card is stuck.
 *
 * Postgres hands back "2025-05-31 19:53:06+00". Date.parse needs a T, and it
 * rejects a two-digit offset — "+00" has to become "+00:00" or the whole
 * thing is NaN and every card silently lands in no age bucket at all.
 */
function daysListed(l: Listing): number | null {
  const s = l.start_date;
  if (!s) return null;
  const iso = s.replace(' ', 'T').replace(/([+-]\d{2})$/, '$1:00');
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  return Math.floor((Date.now() - t) / 86_400_000);
}

type Bucket = 'all' | 'fresh' | 'd31' | 'd61' | 'stale';
const BUCKETS: { key: Bucket; label: string; tone: string; lo: number; hi: number }[] = [
  { key: 'fresh', label: '0–30 days',  tone: 'fresh', lo: 0,  hi: 30 },
  { key: 'd31',   label: '31–60 days', tone: 'cool',  lo: 31, hi: 60 },
  { key: 'd61',   label: '61–90 days', tone: 'watch', lo: 61, hi: 90 },
  { key: 'stale', label: '90+ days',   tone: 'stale', lo: 91, hi: 1e9 },
];

type SortKey = 'days' | 'price' | 'title' | 'watchers' | 'added';

export default function Inventory({ rows }: { rows: Listing[] }) {
  const [q, setQ] = useState('');
  const [bucket, setBucket] = useState<Bucket>('all');
  const [sport, setSport] = useState('');
  const [sort, setSort] = useState<SortKey>('days');
  const [desc, setDesc] = useState(true);
  const [sel, setSel] = useState<Set<string>>(new Set());

  /* ---- derived once per row, not per render of a cell ---- */
  const enriched = useMemo(
    () => rows.map((l) => ({
      l,
      days: daysListed(l),
      price: num(l.current_price) ?? 0,
      title: text(l.title),
      sku: text(l.sku),
      sport: text(l.sport),
      grade: [text(l.grader), text(l.grade)].filter(Boolean).join(' '),
    })),
    [rows],
  );

  const sports = useMemo(
    () => [...new Set(enriched.map((e) => e.sport).filter(Boolean))].sort(),
    [enriched],
  );

  const buckets = useMemo(() => {
    const out: Record<string, { n: number; value: number }> = {};
    for (const b of BUCKETS) out[b.key] = { n: 0, value: 0 };
    for (const e of enriched) {
      if (e.days === null) continue;
      const b = BUCKETS.find((x) => e.days! >= x.lo && e.days! <= x.hi);
      if (b) { out[b.key].n++; out[b.key].value += e.price; }
    }
    return out;
  }, [enriched]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const b = BUCKETS.find((x) => x.key === bucket);
    let out = enriched;
    if (needle) {
      out = out.filter((e) =>
        e.title.toLowerCase().includes(needle) ||
        e.sku.toLowerCase().includes(needle) ||
        e.l.item_number?.includes(needle));
    }
    if (b) out = out.filter((e) => e.days !== null && e.days >= b.lo && e.days <= b.hi);
    if (sport) out = out.filter((e) => e.sport === sport);

    const dir = desc ? -1 : 1;
    return [...out].sort((a, z) => {
      switch (sort) {
        case 'price':    return (a.price - z.price) * dir;
        case 'title':    return a.title.localeCompare(z.title) * dir;
        case 'watchers': return ((a.l.watchers ?? 0) - (z.l.watchers ?? 0)) * dir;
        case 'added':    return ((a.days ?? -1) - (z.days ?? -1)) * dir;
        default:         return ((a.days ?? -1) - (z.days ?? -1)) * dir;
      }
    });
  }, [enriched, q, bucket, sport, sort, desc]);

  const totals = useMemo(() => {
    let value = 0, withComp = 0, compDelta = 0;
    for (const e of filtered) {
      value += e.price;
      const c = num(e.l.comp_avg);
      if (c !== null) { withComp++; compDelta += c - e.price; }
    }
    return { value, withComp, compDelta };
  }, [filtered]);

  /* ---- windowing ---- */
  const scroller = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  const [height, setHeight] = useState(600);
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const measure = () => setHeight(el.clientHeight);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const first = Math.max(0, Math.floor(top / ROW) - 6);
  const count = Math.ceil(height / ROW) + 12;
  const slice = filtered.slice(first, first + count);

  // Selection survives filtering — tick rows, narrow the filter, tick more.
  const toggle = (id: string) =>
    setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allShown = filtered.length > 0 && filtered.every((e) => sel.has(e.l.item_number));
  const toggleAll = () =>
    setSel((s) => {
      const n = new Set(s);
      if (allShown) filtered.forEach((e) => n.delete(e.l.item_number));
      else filtered.forEach((e) => n.add(e.l.item_number));
      return n;
    });

  const sortBy = (k: SortKey) => {
    if (k === sort) setDesc((d) => !d);
    else { setSort(k); setDesc(true); }
  };
  const caret = (k: SortKey) => (sort === k ? (desc ? ' ↓' : ' ↑') : '');

  return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Listings</h1>
      <p className="sub">
        {rows.length.toLocaleString()} active listings · {money0(enriched.reduce((a, e) => a + e.price, 0))} listed value
      </p>

      <div className="legend">
        <span><b className="r">Teal</b> reads your data.</span>
        <span><b className="w">Gold</b> changes a live listing — you always confirm first.</span>
        <span><b className="d">Red</b> removes.</span>
      </div>

      {/* Age buckets carry the money, because "1,752 listings" does not
          tell you anything until you know it is $7,437 sitting still. */}
      <div className="stats">
        {BUCKETS.map((b) => (
          <button
            key={b.key}
            className={`stat ${b.tone}`}
            style={{ textAlign: 'left', cursor: 'pointer',
                     outline: bucket === b.key ? '2px solid var(--brand)' : 'none' }}
            onClick={() => setBucket(bucket === b.key ? 'all' : b.key)}
          >
            <div className="k">{b.label}</div>
            <div className="v">{money0(buckets[b.key].value)}</div>
            <div className="n">{buckets[b.key].n.toLocaleString()} listings</div>
          </button>
        ))}
      </div>

      <div className="toolbar">
        <input
          className="search"
          placeholder="Search title, SKU or item number…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select className="pick" value={sport} onChange={(e) => setSport(e.target.value)}>
          <option value="">All sports</option>
          {sports.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="pick" value={bucket} onChange={(e) => setBucket(e.target.value as Bucket)}>
          <option value="all">Any age</option>
          {BUCKETS.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
        </select>
        {(q || sport || bucket !== 'all') && (
          <button className="btn sm" onClick={() => { setQ(''); setSport(''); setBucket('all'); }}>
            Clear
          </button>
        )}
        <span className="spacer" />
        <span className="muted">
          {filtered.length.toLocaleString()} shown · {money0(totals.value)}
        </span>
      </div>

      {sel.size > 0 && (
        <div className="selbar">
          <span className="n">{sel.size.toLocaleString()} selected</span>
          <span className="muted">
            {money0(enriched.filter((e) => sel.has(e.l.item_number))
                            .reduce((a, e) => a + e.price, 0))} listed value
          </span>
          <span className="spacer" />
          {/* Slice 2 wires these up. They are visible now, and disabled,
              so the shape of the screen is settled before the actions
              behind it can touch a live listing. */}
          <button className="btn sm" disabled>⬆ Export for Card Luma</button>
          <button className="btn sm" disabled>$ Reprice</button>
          <button className="btn sm write" disabled>⟳ End &amp; relist</button>
          <button className="btn sm" onClick={() => setSel(new Set())}>Clear</button>
        </div>
      )}

      <div className="tablewrap">
        <div className="thead">
          <input type="checkbox" checked={allShown} onChange={toggleAll}
                 aria-label="Select everything shown" />
          <div className="hide-sm">SKU</div>
          <button onClick={() => sortBy('title')}>Title{caret('title')}</button>
          <div className="hide-sm">Grade</div>
          <button className="right" onClick={() => sortBy('price')}>Price{caret('price')}</button>
          <button className="right hide-sm" onClick={() => sortBy('days')}>Days{caret('days')}</button>
          <div className="right hide-sm">Comp</div>
          <button className="right hide-sm" onClick={() => sortBy('watchers')}>Watch{caret('watchers')}</button>
          <div className="hide-sm">Age</div>
        </div>

        <div
          ref={scroller}
          className="scroller"
          style={{ height: 'min(62vh, 760px)' }}
          onScroll={(e) => setTop((e.target as HTMLDivElement).scrollTop)}
        >
          <div style={{ height: filtered.length * ROW, position: 'relative' }}>
            <div style={{ transform: `translateY(${first * ROW}px)` }}>
              {slice.map((e) => {
                const b = e.days === null ? null
                        : BUCKETS.find((x) => e.days! >= x.lo && e.days! <= x.hi);
                const comp = num(e.l.comp_avg);
                return (
                  <div
                    key={e.l.item_number}
                    className={`trow${sel.has(e.l.item_number) ? ' sel' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={sel.has(e.l.item_number)}
                      onChange={() => toggle(e.l.item_number)}
                      aria-label={e.title}
                    />
                    <div className="sku hide-sm">{e.sku || '—'}</div>
                    <div className="cell-title" title={e.title}>{e.title}</div>
                    <div className="hide-sm muted">{e.grade || '—'}</div>
                    <div className="right">{money(e.price)}</div>
                    <div className="right hide-sm">{e.days ?? '—'}</div>
                    <div className="right hide-sm muted">{money(comp)}</div>
                    <div className="right hide-sm muted">{e.l.watchers || '—'}</div>
                    <div className="hide-sm">
                      {b ? <span className={`pill ${b.tone}`}>{b.label.split(' ')[0]}</span> : '—'}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <p className="note">
        <b>Days</b> counts from the date a listing first went up, not from its last eBay renewal —
        so a card that has quietly renewed six times still reads 180 days, which is the number
        that matters. <b>Comp</b> is the CardHedger average where we have one
        {totals.withComp > 0 && <> — {totals.withComp.toLocaleString()} of the cards shown</>}.
        Nothing on this screen can change a listing.
      </p>
    </>
  );
}
