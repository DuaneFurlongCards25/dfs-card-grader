import { useEffect, useMemo, useState } from 'react';
import { API, getToken, post } from './api';
import { usd } from './pricing';
import { download, stamp, toCsv } from './exports';

/* ------------------------------------------------------------------ *
 * Lots — did the box earn its money back?
 *
 * The only screen that can answer that, because it is the only place a
 * cost lives. Cards join a lot by SKU prefix, which is how he already
 * names them, so nothing has to be assigned by hand.
 *
 * "Made back" counts money actually taken, not what the rest is listed
 * at. Unsold stock is shown beside it, clearly marked as hope rather
 * than cash — that distinction is the whole point of the screen.
 * ------------------------------------------------------------------ */

type Lot = {
  id: number; lot_prefix: string; source: string | null;
  purchase_date: string | null; is_break: boolean; product: string | null;
  cost: string; card_count: number;
  still_listed: number; listed_value: string; gone: number;
  sales: number; revenue: string; fees: string;
};

const n = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? x : 0; };
const money0 = (v: number) =>
  v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

export default function Lots() {
  const [lots, setLots] = useState<Lot[] | null>(null);
  const [error, setError] = useState('');
  const [sort, setSort] = useState<'date' | 'profit' | 'cost'>('date');
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ lot_prefix: '', source: '', purchase_date: '', total_cost: '', ship_cost: '', notes: '' });

  const load = async () => {
    setError('');
    try {
      const r = await fetch(`${API}/api/lots`, { headers: { Authorization: `Bearer ${getToken()}` } });
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error || `HTTP ${r.status}`);
      setLots(d.lots ?? []);
    } catch (e: any) { setError(e.message || String(e)); setLots([]); }
  };
  useEffect(() => { load(); }, []);

  const rows = useMemo(() => {
    const out = (lots ?? []).map((l) => {
      const cost = n(l.cost), revenue = n(l.revenue), listed = n(l.listed_value);
      return { l, cost, revenue, listed, profit: revenue - cost,
               back: cost > 0 ? (revenue / cost) * 100 : null };
    });
    return out.sort((a, z) => {
      if (sort === 'profit') return z.profit - a.profit;
      if (sort === 'cost') return z.cost - a.cost;
      return (z.l.purchase_date || '').localeCompare(a.l.purchase_date || '');
    });
  }, [lots, sort]);

  const t = rows.reduce((a, r) => ({
    cost: a.cost + r.cost, revenue: a.revenue + r.revenue, listed: a.listed + r.listed,
  }), { cost: 0, revenue: 0, listed: 0 });
  const inProfit = rows.filter((r) => r.cost > 0 && r.profit > 0).length;
  const priced = rows.filter((r) => r.cost > 0).length;

  const save = async () => {
    if (!form.lot_prefix.trim()) return;
    try {
      await post('/api/lots', { ...form, total_cost: Number(form.total_cost) || 0,
                                ship_cost: Number(form.ship_cost) || 0 });
      setAdding(false);
      setForm({ lot_prefix: '', source: '', purchase_date: '', total_cost: '', ship_cost: '', notes: '' });
      load();
    } catch (e: any) { setError(e.message || String(e)); }
  };

  return (
    <>
      <div className="eyebrow">Money</div>
      <h1 className="title">Lots</h1>
      <p className="sub">What each box cost, and what it has made back</p>

      {error && (
        <div className="legend" style={{ borderColor: 'var(--danger)' }}>
          <span style={{ color: 'var(--danger)' }}>{error}</span>
          <span className="spacer" /><button className="btn sm" onClick={load}>Try again</button>
        </div>
      )}

      <div className="stats">
        <div className="stat stale"><div className="k">Put in</div>
          <div className="v">{money0(t.cost)}</div>
          <div className="n">across {priced} lots with a cost recorded</div></div>
        <div className="stat fresh"><div className="k">Taken back</div>
          <div className="v">{money0(t.revenue)}</div>
          <div className="n">money actually received</div></div>
        <div className="stat cool"><div className="k">Still on the shelf</div>
          <div className="v">{money0(t.listed)}</div>
          <div className="n">asking prices, not money yet</div></div>
        <div className="stat"><div className="k">Lots in profit</div>
          <div className="v">{inProfit}<span style={{ fontSize: 16, color: 'var(--text-dim)' }}> / {priced}</span></div>
          <div className="n">already back past what they cost</div></div>
      </div>

      <p className="note" style={{ marginTop: 0 }}>
        <b>Taken back</b> is cash received against that lot's SKUs. <b>Still on the shelf</b> is
        what the unsold cards are listed at, which is a hope and not a number you can spend —
        kept apart on purpose.
      </p>

      <div className="toolbar">
        <select className="pick" value={sort} onChange={(e) => setSort(e.target.value as any)}>
          <option value="date">Newest first</option>
          <option value="profit">Best return first</option>
          <option value="cost">Biggest spend first</option>
        </select>
        <button className="btn read" onClick={() => setAdding(!adding)}>
          {adding ? 'Cancel' : '+ Record a lot'}
        </button>
        <button className="btn write" onClick={async () => {
          try {
            const r = await post('/api/lots/spread-cost', {});
            setError('');
            alert(`${r.priced.toLocaleString()} cards now carry a cost — ` +
                  `${r.live_with_cost.toLocaleString()} of ${r.live_total.toLocaleString()} live cards.\n\n` +
                  `Each lot's cost is split evenly over the cards carrying its prefix.`);
          } catch (e: any) { setError(e.message || String(e)); }
        }}>↺ Spread lot costs onto cards</button>
        <span className="spacer" />
        <button className="btn sm" onClick={() => download(`lots-${stamp()}.csv`,
          toCsv(['Lot', 'Bought', 'Source', 'Cost', 'Taken back', 'Profit', 'Still listed', 'Cards left'],
            rows.map((r) => [r.l.lot_prefix, r.l.purchase_date ?? '', r.l.source ?? '',
              r.cost.toFixed(2), r.revenue.toFixed(2), r.profit.toFixed(2),
              r.listed.toFixed(2), r.l.still_listed])))}>⬇ Export</button>
      </div>

      {adding && (
        <div className="card2">
          <div className="rulerow">
            <label>SKU prefix
              <input value={form.lot_prefix} placeholder="RBLOT3_10-17-26"
                     onChange={(e) => setForm({ ...form, lot_prefix: e.target.value })} />
              <small>Cards whose SKU starts with this belong to the lot.</small>
            </label>
            <label>What it cost
              <input type="number" step="0.01" value={form.total_cost}
                     onChange={(e) => setForm({ ...form, total_cost: e.target.value })} />
              <small>What you paid, before shipping.</small>
            </label>
            <label>Shipping
              <input type="number" step="0.01" value={form.ship_cost}
                     onChange={(e) => setForm({ ...form, ship_cost: e.target.value })} />
              <small>Added to the cost.</small>
            </label>
            <label>Bought on
              <input type="date" value={form.purchase_date}
                     onChange={(e) => setForm({ ...form, purchase_date: e.target.value })} />
            </label>
            <label>Where from
              <input value={form.source} placeholder="Whatnot, eBay, show…"
                     onChange={(e) => setForm({ ...form, source: e.target.value })} />
            </label>
          </div>
          <button className="btn read" onClick={save} disabled={!form.lot_prefix.trim()}>
            Save lot
          </button>
        </div>
      )}

      <div className="tablewrap">
        <div className="thead lot">
          <div>Lot</div><div>Bought</div><div className="right">Cost</div>
          <div className="right">Taken back</div><div className="right">Profit</div>
          <div className="right">Still listed</div><div>How it is going</div>
        </div>
        <div className="scroller" style={{ maxHeight: 560 }}>
          {rows.map((r) => {
            const done = r.back !== null && r.back >= 100;
            return (
              <div key={r.l.id} className="trow lot">
                <div className="sku" title={r.l.lot_prefix}>
                  {r.l.lot_prefix}{r.l.is_break && <span className="pill cool" style={{ marginLeft: 6 }}>break</span>}
                </div>
                <div className="muted">{r.l.purchase_date ?? '—'}</div>
                <div className="right">{r.cost ? usd(r.cost) : <span className="faint">not recorded</span>}</div>
                <div className="right">{usd(r.revenue)}</div>
                <div className="right" style={{ color: !r.cost ? 'var(--text-faint)'
                      : r.profit >= 0 ? 'var(--fresh)' : 'var(--stale)' }}>
                  {r.cost ? (r.profit >= 0 ? '+' : '') + usd(r.profit) : '—'}
                </div>
                <div className="right muted">
                  {usd(r.listed)}{r.l.still_listed ? ` · ${r.l.still_listed}` : ''}
                </div>
                <div>
                  {r.back === null ? <span className="faint">add a cost to see</span> : (
                    <div className="backbar" title={`${r.back.toFixed(0)}% of the cost recovered`}>
                      <div style={{ width: `${Math.min(100, r.back)}%`,
                                    background: done ? 'var(--fresh)' : 'var(--watch)' }} />
                      <span>{r.back.toFixed(0)}%</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {lots !== null && !rows.length &&
            <p className="note" style={{ padding: 14 }}>No lots recorded yet.</p>}
        </div>
      </div>

      <p className="note">
        A lot is paid off once <b>Taken back</b> passes <b>Cost</b> — the bar turns green.
        Everything after that is profit, and whatever is still listed is on top of it.
      </p>
    </>
  );
}
