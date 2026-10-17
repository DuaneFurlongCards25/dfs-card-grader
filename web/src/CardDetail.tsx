import { useEffect, useState } from 'react';
import { API, getToken, type Listing, num, text } from './api';
import { usd } from './pricing';

/* ------------------------------------------------------------------ *
 * One card, everything known about it.
 *
 * Opens over the table rather than navigating away, because the job is
 * nearly always "check this one thing and carry on down the list".
 *
 * What it will not do is show a margin it cannot stand behind: with no
 * cost recorded the line says so, rather than printing the sale price
 * as if it were all profit.
 * ------------------------------------------------------------------ */

type Sale = {
  sale_date: string | null; sale_price: string | null;
  gross_revenue: string | null; platform_fee: string | null; source: string | null;
};

function days(from: string | null): number | null {
  if (!from) return null;
  const t = Date.parse(from.replace(' ', 'T').replace(/([+-]\d{2})$/, '$1:00'));
  return Number.isFinite(t) ? Math.floor((Date.now() - t) / 86_400_000) : null;
}

export default function CardDetail({ card, onClose }: { card: Listing; onClose: () => void }) {
  const [sales, setSales] = useState<Sale[] | null>(null);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onClose]);

  useEffect(() => {
    let live = true;
    const id = card.item_number;
    // Old sales rows carry a trailing '.0' on the item number, so ask for
    // both spellings rather than quietly finding nothing.
    fetch(`${API}/api/db/sales_records?item_number=in.(${id},${id}.0)&limit=20`,
      { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.json())
      .then((d) => live && setSales(d?.data ?? []))
      .catch(() => live && setSales([]));
    return () => { live = false; };
  }, [card.item_number]);

  const price = num(card.current_price);
  const comp = num(card.comp_avg);
  const cost = num(card.cost_basis);
  const d = days(card.start_date);
  const grade = [text(card.grader), text(card.grade)].filter(Boolean).join(' ');
  const margin = price !== null && cost !== null ? price - cost : null;
  const vsComp = price !== null && comp !== null ? ((price - comp) / comp) * 100 : null;

  return (
    <div className="sheetwrap" onClick={onClose}>
      <aside className="sheet2" onClick={(e) => e.stopPropagation()}>
        <div className="s2-head">
          <div>
            <div className="eyebrow">{text(card.sport) || 'Card'}</div>
            <h2 className="s2-title">{text(card.title)}</h2>
          </div>
          <button className="icon2" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="s2-rows">
          <div><span>SKU</span><b className="mono">{text(card.sku) || '—'}</b></div>
          <div><span>Item number</span><b className="mono">{card.item_number}</b></div>
          <div><span>Listed at</span><b>{price !== null ? usd(price) : '—'}</b></div>
          <div>
            <span>Comp</span>
            <b>
              {comp !== null ? usd(comp) : <i className="faint">none — nothing has a price for this card</i>}
              {vsComp !== null && (
                <span className="muted" style={{ marginLeft: 8, fontWeight: 400 }}>
                  you are {vsComp >= 0 ? `${vsComp.toFixed(0)}% above` : `${Math.abs(vsComp).toFixed(0)}% below`} it
                </span>
              )}
            </b>
          </div>
          <div>
            <span>What it cost</span>
            <b>
              {cost !== null ? usd(cost) : <i className="faint">not recorded — add its lot cost</i>}
              {margin !== null && (
                <span style={{ marginLeft: 8, fontWeight: 600,
                               color: margin >= 0 ? 'var(--fresh)' : 'var(--stale)' }}>
                  {margin >= 0 ? '+' : ''}{usd(margin)} if it sells at the asking price
                </span>
              )}
            </b>
          </div>
          <div><span>Days listed</span>
            <b>{d ?? '—'}{d !== null && d > 90 && <span className="pill stale" style={{ marginLeft: 8 }}>stale</span>}</b></div>
          <div><span>Watchers</span><b>{card.watchers ?? 0}</b></div>
          <div><span>Grade</span><b>{grade || <i className="faint">raw</i>}</b></div>
          {text(card.cert_number) && (
            <div><span>Cert</span><b className="mono">{text(card.cert_number)}</b></div>)}
          <div><span>Status</span>
            <b>{card.ended_at
              ? <span className="pill stale">sold or ended</span>
              : <span className="pill fresh">live on eBay</span>}</b></div>
        </div>

        <h3 className="s2-h">Sales of this card</h3>
        {sales === null && <p className="note" style={{ marginTop: 0 }}>Looking…</p>}
        {sales?.length === 0 && (
          <p className="note" style={{ marginTop: 0 }}>
            No sale recorded against this item number.
            {card.ended_at && ' It is marked ended, so it either sold before orders were imported, or was pulled.'}
          </p>
        )}
        {!!sales?.length && (
          <div className="tablewrap">
            {sales.map((s, i) => (
              <div key={i} className="trow simple">
                <div className="sku">{s.sale_date ?? '—'}</div>
                <div className="cell-title muted">{s.source ?? 'eBay'}</div>
                <div className="right">{usd(num(s.gross_revenue) ?? num(s.sale_price) ?? 0)}</div>
              </div>
            ))}
          </div>
        )}

        <div className="s2-foot">
          <a className="btn" target="_blank" rel="noreferrer"
             href={`https://www.ebay.com/itm/${card.item_number}`}>Open on eBay ↗</a>
          <button className="btn" onClick={() => {
            navigator.clipboard?.writeText(text(card.sku) || card.item_number);
          }}>Copy SKU</button>
          <a className="btn" target="_blank" rel="noreferrer"
             href={`https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(text(card.title))}&_sacat=261328&LH_Sold=1&LH_Complete=1`}>
            What it sold for ↗
          </a>
        </div>
      </aside>
    </div>
  );
}
