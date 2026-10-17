import { useMemo, useState } from 'react';
import { type Listing, num, text } from './api';
import { DEFAULT_RULES, nudge, priceOne, type Rules, usd } from './pricing';
import { download, fileExchangeEnd, fileExchangeRevise, reviewCsv, stamp, workingCsv } from './exports';

/* ------------------------------------------------------------------ *
 * Reprice — the Sunday job, on one screen.
 *
 * Nothing here touches eBay. It works out what every ticked card should
 * list for, shows the move next to the reason in plain words, and hands
 * back a File Exchange file to upload. The review file comes with it so
 * the numbers can be read before anything goes live.
 * ------------------------------------------------------------------ */

const money = (n: number | null) => (n === null ? '—' : usd(n));

export default function Reprice({
  rows, selected, onClear,
}: { rows: Listing[]; selected: Set<string>; onClear: () => void }) {
  const [rules, setRules] = useState<Rules>(DEFAULT_RULES);
  const [flat, setFlat] = useState<number | null>(null);

  const picked = useMemo(
    () => rows.filter((l) => selected.has(l.item_number) && !l.ended_at),
    [rows, selected]);

  const priced = useMemo(() => picked.map((l) => {
    const current = num(l.current_price);
    const comp = num(l.comp_avg);
    const cost = num(l.cost_basis);
    if (flat !== null) {
      const p = nudge(current, flat, rules);
      return { l, current, comp,
        now: p, why: `${flat}% off what it is listed at now`,
        moved: p !== null && current !== null && Math.abs(p - current) > 0.004 };
    }
    const r = priceOne({ current, market: comp, cost }, rules);
    return { l, current, comp, now: r.price, why: r.why, moved: r.moved };
  }), [picked, rules, flat]);

  const movers = priced.filter((p) => p.moved && p.now !== null);
  const noComp = priced.filter((p) => p.comp === null).length;
  const up = movers.filter((p) => p.now! > (p.current ?? 0));
  const down = movers.filter((p) => p.now! < (p.current ?? 0));
  const delta = movers.reduce((a, p) => a + (p.now! - (p.current ?? 0)), 0);

  const set = (k: keyof Rules, v: any) => { setFlat(null); setRules({ ...rules, [k]: v }); };

  if (!picked.length) return (
    <>
      <div className="eyebrow">Pricing</div>
      <h1 className="title">Reprice</h1>
      <p className="sub">Tick some cards on the Listings tab, then come back.</p>
      <p className="note" style={{ maxWidth: 560 }}>
        Everything here is worked out in your browser and handed back as a file you
        upload to eBay yourself. Nothing on this screen can change a live listing.
      </p>
    </>
  );

  return (
    <>
      <div className="eyebrow">Pricing</div>
      <h1 className="title">Reprice</h1>
      <p className="sub">{picked.length.toLocaleString()} cards picked · priced off the CardHedger comp</p>

      <div className="legend">
        <span><b className="r">Blue</b> reads your data.</span>
        <span><b className="w">Gold</b> makes a file for eBay — you upload it yourself.</span>
      </div>

      <div className="stats">
        <div className="stat"><div className="k">Would move</div>
          <div className="v">{movers.length.toLocaleString()}</div>
          <div className="n">of {picked.length.toLocaleString()} picked</div></div>
        <div className="stat fresh"><div className="k">Going up</div>
          <div className="v">{up.length.toLocaleString()}</div>
          <div className="n">comp is above the list price</div></div>
        <div className="stat watch"><div className="k">Coming down</div>
          <div className="v">{down.length.toLocaleString()}</div>
          <div className="n">comp is below the list price</div></div>
        <div className="stat cool"><div className="k">Change in listed value</div>
          <div className="v">{delta >= 0 ? '+' : ''}{usd(delta)}</div>
          <div className="n">across everything that moves</div></div>
      </div>

      {/* The quick way — what he actually does to stale stock. */}
      <div className="toolbar">
        <span className="muted">Quick cut:</span>
        {[-5, -10, -20, -30].map((p) => (
          <button key={p} className={`chip${flat === p ? ' on' : ''}`}
                  onClick={() => setFlat(flat === p ? null : p)}>{p}%</button>
        ))}
        <span className="spacer" />
        <span className="muted">
          {flat !== null ? 'Flat cut off the current price — comps ignored.' : 'Using your rules below.'}
        </span>
      </div>

      <details className="rules" open={flat === null}>
        <summary>Rules — market price in, list price out</summary>

        <div className="rulerow">
          <label>Floor
            <input type="number" step="0.01" value={rules.floor ?? ''}
                   onChange={(e) => set('floor', e.target.value === '' ? null : +e.target.value)} />
            <small>Never list below this, however low the comp goes.</small>
          </label>
          <label>Round to
            <select value={rules.rounding} onChange={(e) => set('rounding', e.target.value)}>
              <option value="none">exact</option>
              <option value="99">.99</option>
              <option value="49">.49</option>
              <option value="quarter">next 25¢</option>
              <option value="dollar">whole dollar</option>
            </select>
            <small>Applied before the movement cap.</small>
          </label>
          <label>Biggest move
            <input type="number" step="1" value={rules.maxMovePct ?? ''}
                   onChange={(e) => set('maxMovePct', e.target.value === '' ? null : +e.target.value)} />
            <small>% a price may move in one go. Checked last — nothing gets past it.</small>
          </label>
          <label>Edge stickiness
            <input type="number" step="1" value={rules.stickinessPct ?? ''}
                   onChange={(e) => set('stickinessPct', e.target.value === '' ? null : +e.target.value)} />
            <small>Holds a card still when its comp hovers on a band edge, so it moves on a trend and not on noise.</small>
          </label>
        </div>

        <div className="rulerow">
          <label className="wide">
            <span>
              <input type="checkbox" checked={rules.neverBelowCost}
                     onChange={(e) => set('neverBelowCost', e.target.checked)} />
              {' '}Never price under what you paid
            </span>
            <small>Only bites on cards where a cost is recorded.</small>
          </label>
        </div>

        <table className="bands">
          <thead><tr><th>Comp from</th><th>to</th><th>lists at</th><th /></tr></thead>
          <tbody>
            {rules.bands.map((b, i) => (
              <tr key={i}>
                <td><input type="number" step="0.01" value={b.min}
                     onChange={(e) => { const n = [...rules.bands]; n[i] = { ...b, min: +e.target.value }; set('bands', n); }} /></td>
                <td><input type="number" step="0.01" value={b.max}
                     onChange={(e) => { const n = [...rules.bands]; n[i] = { ...b, max: +e.target.value }; set('bands', n); }} /></td>
                <td>
                  <select value={b.kind}
                    onChange={(e) => { const n = [...rules.bands]; n[i] = { ...b, kind: e.target.value as any }; set('bands', n); }}>
                    <option value="fixed">$ fixed</option>
                    <option value="pct">% of comp</option>
                    <option value="off">$ off comp</option>
                  </select>
                  <input type="number" step="0.01" value={b.value}
                     onChange={(e) => { const n = [...rules.bands]; n[i] = { ...b, value: +e.target.value }; set('bands', n); }} />
                </td>
                <td><button className="btn sm"
                     onClick={() => set('bands', rules.bands.filter((_, j) => j !== i))}>×</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="btn sm" onClick={() => set('bands',
          [...rules.bands, { min: 0, max: 0, kind: 'pct', value: 0 }])}>+ Add a band</button>
      </details>

      <div className="selbar">
        <span className="n">{movers.length.toLocaleString()} price changes ready</span>
        <span className="spacer" />
        <button className="btn" disabled={!movers.length}
          onClick={() => download(`reprice-review-${stamp()}.csv`, reviewCsv(movers.map((p) => ({
            sku: text(p.l.sku), item_number: p.l.item_number, title: text(p.l.title),
            was: p.current, now: p.now, comp: p.comp, why: p.why,
          }))))}>⬇ Review file</button>
        <button className="btn write" disabled={!movers.length}
          onClick={() => download(`ebay-revise-${stamp()}.csv`, fileExchangeRevise(
            movers.map((p) => ({ item_number: p.l.item_number, price: p.now! }))))}>
          ⬆ eBay File Exchange ({movers.length})
        </button>
        <button className="btn" onClick={onClear}>Clear pick</button>
      </div>

      {noComp > 0 && (
        <p className="note" style={{ marginTop: 0 }}>
          <b>{noComp.toLocaleString()} of the picked cards have no comp</b>, so they are left exactly
          as they are rather than guessed at. Run them through CardHedger in Streamlit first if you
          want them priced.
        </p>
      )}

      <div className="tablewrap" style={{ marginTop: 14 }}>
        <div className="thead rp">
          <div>SKU</div><div>Title</div><div className="right">Comp</div>
          <div className="right">Now</div><div className="right">Becomes</div><div>Why</div>
        </div>
        <div className="scroller" style={{ maxHeight: 460 }}>
          {priced.slice(0, 500).map((p) => (
            <div key={p.l.item_number} className={`trow rp${p.moved ? '' : ' dim'}`}>
              <div className="sku">{text(p.l.sku) || p.l.item_number}</div>
              <div className="cell-title" title={text(p.l.title)}>{text(p.l.title)}</div>
              <div className="right muted">{money(p.comp)}</div>
              <div className="right">{money(p.current)}</div>
              <div className="right">
                {p.now === null ? '—' : (
                  <b style={{ color: !p.moved ? 'var(--text-faint)'
                    : p.now > (p.current ?? 0) ? 'var(--fresh)' : 'var(--watch)' }}>
                    {money(p.now)}
                  </b>
                )}
              </div>
              <div className="why">{p.why}</div>
            </div>
          ))}
        </div>
      </div>
      {priced.length > 500 &&
        <p className="note">Showing the first 500 of {priced.length.toLocaleString()} — the file has them all.</p>}

      <div className="selbar" style={{ marginTop: 16 }}>
        <span className="muted">Other files for this pick:</span>
        <span className="spacer" />
        <button className="btn" onClick={() => download(`cards-${stamp()}.csv`, workingCsv(
          picked.map((l) => ({
            sku: text(l.sku), item_number: l.item_number, title: text(l.title),
            price: num(l.current_price), sport: text(l.sport),
            grade: [text(l.grader), text(l.grade)].filter(Boolean).join(' '),
            cert: text(l.cert_number),
            days: null, comp: num(l.comp_avg), watchers: l.watchers ?? null,
          }))))}>⬇ Working file (Card Luma / website)</button>
        <button className="btn danger"
          onClick={() => { if (confirm(
            `Make a File Exchange file that ENDS ${picked.length} listings on eBay?\n\n` +
            `The file is only downloaded — nothing ends until you upload it to eBay yourself.`))
            download(`ebay-end-${stamp()}.csv`, fileExchangeEnd(picked.map((l) => l.item_number))); }}>
          ⬆ End-listings file
        </button>
      </div>
    </>
  );
}
