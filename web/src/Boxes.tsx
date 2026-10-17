import { useMemo, useState } from 'react';
import { type Listing, num, text } from './api';
import { usd } from './pricing';
import { download, stamp, toCsv } from './exports';

/* ------------------------------------------------------------------ *
 * Boxes — where the cards actually are.
 *
 * Nobody typed a storage map. The SKUs already carry one: FBrelist,
 * RBLOT2_10-13-26-229, KKCARD-09-13-26-00037. The prefix is the box, so
 * this reads the shelf that already exists rather than asking him to
 * build a second one by hand and keep the two in step.
 * ------------------------------------------------------------------ */

const money0 = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

/**
 * The box a SKU belongs to.
 *
 * His SKUs run <box>-<date>-<n> or <box>_<date>-<n>. Taking everything
 * before the first date-looking part keeps "RBLOT2" and "KKCARD"
 * together instead of splitting one box into a hundred of one card.
 */
export function boxOf(sku: string): string {
  const s = (sku || '').trim();
  if (!s) return '(no SKU)';
  const cut = s.search(/[-_](?:\d{2}-\d{2}-\d{2}|\d{4,})/);
  const head = (cut > 0 ? s.slice(0, cut) : s.split(/[-_]/)[0]).trim();
  return head || '(no SKU)';
}

export default function Boxes({ rows }: { rows: Listing[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const [q, setQ] = useState('');

  const boxes = useMemo(() => {
    const m = new Map<string, { cards: Listing[]; value: number }>();
    for (const l of rows) {
      if (l.ended_at) continue;
      const b = boxOf(text(l.sku));
      const v = m.get(b) ?? { cards: [], value: 0 };
      v.cards.push(l);
      v.value += num(l.current_price) ?? 0;
      m.set(b, v);
    }
    return [...m.entries()]
      .map(([name, v]) => ({ name, n: v.cards.length, value: v.value, cards: v.cards }))
      .sort((a, z) => z.value - a.value);
  }, [rows]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return boxes;
    return boxes.filter((b) =>
      b.name.toLowerCase().includes(needle) ||
      b.cards.some((c) => text(c.title).toLowerCase().includes(needle)));
  }, [boxes, q]);

  const live = rows.filter((l) => !l.ended_at);
  const totalValue = live.reduce((a, l) => a + (num(l.current_price) ?? 0), 0);
  const noSku = boxes.find((b) => b.name === '(no SKU)');

  const openBox = boxes.find((b) => b.name === open);

  return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Boxes</h1>
      <p className="sub">
        {boxes.length.toLocaleString()} boxes · {live.length.toLocaleString()} cards · {money0(totalValue)}
      </p>

      <div className="stats">
        <div className="stat"><div className="k">Boxes</div>
          <div className="v">{boxes.length.toLocaleString()}</div>
          <div className="n">read from your SKU prefixes</div></div>
        <div className="stat cool"><div className="k">Biggest box</div>
          <div className="v">{boxes[0]?.n.toLocaleString() ?? '—'}</div>
          <div className="n">{boxes[0]?.name ?? ''}</div></div>
        <div className="stat fresh"><div className="k">Most valuable</div>
          <div className="v">{boxes[0] ? money0(boxes[0].value) : '—'}</div>
          <div className="n">{boxes[0]?.name ?? ''}</div></div>
        <div className="stat watch"><div className="k">No SKU</div>
          <div className="v">{noSku?.n.toLocaleString() ?? '0'}</div>
          <div className="n">cards with nowhere recorded</div></div>
      </div>

      <div className="toolbar">
        <input className="search" placeholder="Find a box, or a card inside one…"
               value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn sm" onClick={() => download(`boxes-${stamp()}.csv`,
          toCsv(['Box', 'Cards', 'Listed value'],
            boxes.map((b) => [b.name, b.n, b.value.toFixed(2)])))}>⬇ Box list</button>
      </div>

      <div className="boxgrid">
        {shown.map((b) => (
          <button key={b.name}
                  className={`boxcard${open === b.name ? ' on' : ''}`}
                  onClick={() => setOpen(open === b.name ? null : b.name)}>
            <div className="bn">{b.name}</div>
            <div className="bc">{b.n.toLocaleString()}<span> cards</span></div>
            <div className="bv">{money0(b.value)}</div>
          </button>
        ))}
        {!shown.length && <p className="note">No box matches that.</p>}
      </div>

      {openBox && (
        <>
          <h2 className="h2">{openBox.name} — {openBox.n.toLocaleString()} cards · {money0(openBox.value)}</h2>
          <div className="toolbar">
            <button className="btn sm" onClick={() => download(
              `box-${openBox.name.replace(/[^A-Za-z0-9]+/g, '-')}-${stamp()}.csv`,
              toCsv(['SKU', 'Title', 'Price', 'Sport', 'Item number'],
                openBox.cards.map((c) => [text(c.sku), text(c.title),
                  num(c.current_price)?.toFixed(2) ?? '', text(c.sport), c.item_number])))}>
              ⬇ Everything in this box
            </button>
            <span className="muted">Pull sheet for counting the box by hand.</span>
          </div>
          <div className="tablewrap">
            <div className="scroller" style={{ maxHeight: 420 }}>
              {openBox.cards
                .slice()
                .sort((a, z) => text(a.sku).localeCompare(text(z.sku), undefined, { numeric: true }))
                .slice(0, 600)
                .map((c) => (
                  <div key={c.item_number} className="trow simple">
                    <div className="sku">{text(c.sku)}</div>
                    <div className="cell-title">{text(c.title)}</div>
                    <div className="right">{usd(num(c.current_price) ?? 0)}</div>
                  </div>
                ))}
            </div>
          </div>
          {openBox.n > 600 &&
            <p className="note">Showing 600 of {openBox.n.toLocaleString()} — the file has them all.</p>}
        </>
      )}

      <p className="note">
        <b>Where these come from.</b> The box is the part of a SKU before its date — so
        <code> RBLOT2_10-13-26-229</code> lives in <code>RBLOT2</code>. Nothing here was typed
        in and nothing can drift out of step with the cards, because it IS the cards. Only
        what is live on eBay is counted; sold cards have left the box.
      </p>
    </>
  );
}
