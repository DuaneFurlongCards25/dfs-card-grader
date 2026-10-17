import { useEffect, useState } from 'react';
import { API, getToken } from './api';
import { usd } from './pricing';

/* ------------------------------------------------------------------ *
 * Dashboard — how the business is doing, in one screen.
 *
 * Two rules, both borrowed from what works in Leumas Live:
 *   1. Every number says underneath where it came from.
 *   2. A number we cannot honestly compute is shown as missing, with
 *      what would fix it — not left out, and never estimated.
 *
 * The second one is why "true profit" is absent rather than wrong: no
 * card in the table has a cost against it yet.
 * ------------------------------------------------------------------ */

type Dash = {
  year: number;
  inventory: {
    live: number; ended: number; listed_value: string; with_comp: number;
    with_cost: number; no_sport: number; stale_value: string; stale_n: number;
    watchers: number;
  };
  sales: { lines: number; orders: number; gross: string; fees: string; with_fee: number };
  by_month: { m: string; gross: string; fees: string; n: number }[];
  by_channel: { source: string; n: number; gross: string }[];
  speed: { n: number; median_days: number | null };
  top_boxes: { box: string; n: number; value: string }[];
};

const n = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? x : 0; };
const money0 = (v: number) =>
  v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const CHANNEL: Record<string, string> = {
  ebay: 'eBay', dc_sports: 'DC Sports 87', collx: 'CollX', whatnot: 'Whatnot',
};

export default function Dashboard({ onGo }: { onGo: (tab: string) => void }) {
  const [d, setD] = useState<Dash | null>(null);
  const [year, setYear] = useState(new Date().getFullYear());
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    setD(null); setError('');
    fetch(`${API}/api/dashboard?year=${year}`,
      { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(async (r) => {
        const b = await r.json();
        if (!r.ok) throw new Error(b?.error || `HTTP ${r.status}`);
        if (live) setD(b);
      })
      .catch((e) => live && setError(e.message || String(e)));
    return () => { live = false; };
  }, [year]);

  if (error) return (
    <><div className="eyebrow">Dashboard</div><h1 className="title">Where things stand</h1>
    <div className="legend" style={{ borderColor: 'var(--danger)' }}>
      <span style={{ color: 'var(--danger)' }}>{error}</span></div></>
  );
  if (!d) return (
    <><div className="eyebrow">Dashboard</div><h1 className="title">Where things stand</h1>
    <p className="sub">Adding it up…</p></>
  );

  const gross = n(d.sales.gross);
  const fees = n(d.sales.fees);
  const kept = gross - fees;
  const listed = n(d.inventory.listed_value);
  const stale = n(d.inventory.stale_value);
  const feeRate = gross > 0 ? (fees / gross) * 100 : null;
  const noFee = d.sales.lines - d.sales.with_fee;
  const peak = Math.max(1, ...d.by_month.map((m) => n(m.gross)));

  return (
    <>
      <div className="eyebrow">Dashboard</div>
      <h1 className="title">Where things stand</h1>
      <p className="sub">
        {d.inventory.live.toLocaleString()} cards listed · {d.sales.orders.toLocaleString()} orders in {d.year}
      </p>

      {/* The headline: what came in and what was kept. Not called profit,
          because profit needs what the cards cost and that is not known. */}
      <div className="hero">
        <div>
          <div className="k">Kept in {d.year}, after marketplace fees</div>
          <div className="hero-v">{usd(kept)}</div>
          <div className="hero-n">
            {usd(gross)} taken in − {usd(fees)} in fees
            {feeRate !== null && <> · <b>{feeRate.toFixed(1)}%</b> of every sale goes to the marketplace</>}
          </div>
        </div>
        <select className="pick" value={year} onChange={(e) => setYear(+e.target.value)}>
          {[2026, 2025].map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>

      {d.inventory.with_cost === 0 && (
        <div className="legend" style={{ borderColor: 'var(--watch)' }}>
          <span style={{ color: 'var(--watch)' }}>This is not profit.</span>
          <span className="muted">
            No card has what you paid for it recorded, so there is nothing to subtract.
            Add cost against your lots and this becomes a real profit number.
          </span>
        </div>
      )}

      <div className="stats">
        <div className="stat"><div className="k">On the shelf</div>
          <div className="v">{money0(listed)}</div>
          <div className="n">{d.inventory.live.toLocaleString()} cards at your asking prices</div></div>
        <div className="stat stale"><div className="k">Sitting over 90 days</div>
          <div className="v">{money0(stale)}</div>
          <div className="n">{d.inventory.stale_n.toLocaleString()} cards · {listed > 0 ? Math.round((stale / listed) * 100) : 0}% of the shelf</div></div>
        <div className="stat cool"><div className="k">Typical time to sell</div>
          <div className="v">{d.speed.median_days ?? '—'}{d.speed.median_days ? ' days' : ''}</div>
          <div className="n">
            {d.speed.n ? `middle of ${d.speed.n.toLocaleString()} sales we can trace to a listing` : 'not enough matched sales yet'}
          </div></div>
        <div className="stat fresh"><div className="k">People watching</div>
          <div className="v">{d.inventory.watchers.toLocaleString()}</div>
          <div className="n">across everything listed</div></div>
      </div>

      <p className="note" style={{ marginTop: 0 }}>
        <b>Where these come from.</b> The shelf is your own asking prices × what is live on eBay
        right now. <b>Time to sell</b> counts from the day a card first went up to the day it
        sold, for sales we can match back to a listing — not from its last renewal.
        {noFee > 0 && <> Fees are missing on {noFee.toLocaleString()} of {d.sales.lines.toLocaleString()} sales,
          so what you kept is flattered; eBay's orders report carries no fee column.</>}
      </p>

      <h2 className="h2">Money in, month by month — {d.year}</h2>
      <div className="tablewrap">
        <div className="thead mo">
          <div>Month</div><div className="right">Taken in</div><div className="right">Fees</div>
          <div className="right">Kept</div><div className="right">Sales</div><div>Share</div>
        </div>
        {d.by_month.map((m) => (
          <div key={m.m} className="trow mo">
            <div>{MONTHS[+m.m - 1] ?? m.m}</div>
            <div className="right">{usd(n(m.gross))}</div>
            <div className="right muted">{usd(n(m.fees))}</div>
            <div className="right" style={{ color: 'var(--fresh)' }}>{usd(n(m.gross) - n(m.fees))}</div>
            <div className="right muted">{m.n}</div>
            <div><div className="bar" style={{ width: `${(n(m.gross) / peak) * 100}%` }} /></div>
          </div>
        ))}
        {!d.by_month.length && <p className="note" style={{ padding: 14 }}>No sales recorded in {d.year}.</p>}
      </div>

      <div className="two">
        <div>
          <h2 className="h2">Where it sold</h2>
          <div className="tablewrap">
            {d.by_channel.map((c) => (
              <div key={c.source} className="trow simple">
                <div className="sku">{CHANNEL[c.source] ?? c.source}</div>
                <div className="cell-title muted">{c.n.toLocaleString()} sales</div>
                <div className="right">{money0(n(c.gross))}</div>
              </div>
            ))}
            {!d.by_channel.length && <p className="note" style={{ padding: 14 }}>Nothing yet.</p>}
          </div>
        </div>
        <div>
          <h2 className="h2">Biggest boxes</h2>
          <div className="tablewrap">
            {d.top_boxes.map((b) => (
              <div key={b.box} className="trow simple">
                <div className="sku">{b.box}</div>
                <div className="cell-title muted">{b.n.toLocaleString()} cards</div>
                <div className="right">{money0(n(b.value))}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Not a nag list — each line is a job with a button that starts it. */}
      <h2 className="h2">Worth doing next</h2>
      <div className="todo">
        {d.inventory.stale_n > 0 && (
          <button className="todo-row" onClick={() => onGo('Inventory')}>
            <b>{d.inventory.stale_n.toLocaleString()} cards have sat over 90 days</b>
            <span>{money0(stale)} tied up. Cut the price or end them.</span>
          </button>
        )}
        {d.inventory.with_comp < d.inventory.live && (
          <button className="todo-row" onClick={() => onGo('Reprice')}>
            <b>{(d.inventory.live - d.inventory.with_comp).toLocaleString()} cards have no comp</b>
            <span>Pick them and press Get comps — about half will come back with a price.</span>
          </button>
        )}
        {d.inventory.with_cost === 0 && (
          <button className="todo-row" onClick={() => onGo('Boxes')}>
            <b>No card has a cost recorded</b>
            <span>Until a lot cost goes in, every profit figure here is really just revenue.</span>
          </button>
        )}
        {d.inventory.no_sport > 0 && (
          <button className="todo-row" onClick={() => onGo('Inventory')}>
            <b>{d.inventory.no_sport.toLocaleString()} cards have no sport</b>
            <span>They fall out of every sport filter. A comp lookup names them.</span>
          </button>
        )}
        <button className="todo-row" onClick={() => onGo('Refresh')}>
          <b>Pull today's eBay report</b>
          <span>Catches anything that sold, so it cannot be relisted by mistake.</span>
        </button>
      </div>
    </>
  );
}
