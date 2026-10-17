import { useEffect, useMemo, useState } from 'react';
import { Expired, fetchSales, num, type Sale } from './api';
import { usd } from './pricing';
import { download, stamp, toCsv } from './exports';

/* ------------------------------------------------------------------ *
 * Money.
 *
 * Every number on this page has a sentence under it saying where it came
 * from, because a number you have to go and verify is a number you do
 * not use. The fee rate in particular is MEASURED from the fees eBay
 * actually charged on these orders — not eBay's published schedule,
 * which never matches what lands in the account.
 * ------------------------------------------------------------------ */

const money0 = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

export default function Money() {
  const [sales, setSales] = useState<Sale[] | null>(null);
  const [error, setError] = useState('');
  const [year, setYear] = useState<number | 'all'>(new Date().getFullYear());

  useEffect(() => {
    let live = true;
    fetchSales()
      .then((s) => live && setSales(s))
      .catch((e) => live && setError(e instanceof Expired ? 'session expired' : e.message));
    return () => { live = false; };
  }, []);

  const rows = useMemo(() => (sales ?? []).map((s) => {
    const d = (s.sale_date || '').slice(0, 10);
    return {
      s, date: d,
      year: +d.slice(0, 4) || 0,
      month: +d.slice(5, 7) || 0,
      gross: num(s.gross_revenue) ?? num(s.sale_price) ?? 0,
      fee: num(s.platform_fee) ?? 0,
      net: num(s.net_proceeds) ?? 0,
      ship: num(s.shipping_collected) ?? 0,
      qty: num(s.quantity) ?? 1,
    };
  }).filter((r) => r.year > 2000), [sales]);

  const years = useMemo(
    () => [...new Set(rows.map((r) => r.year))].sort((a, b) => b - a), [rows]);

  const inYear = useMemo(
    () => (year === 'all' ? rows : rows.filter((r) => r.year === year)), [rows, year]);

  const t = useMemo(() => {
    const gross = inYear.reduce((a, r) => a + r.gross, 0);
    const fee = inYear.reduce((a, r) => a + r.fee, 0);
    const net = inYear.reduce((a, r) => a + (r.net || r.gross - r.fee), 0);
    const units = inYear.reduce((a, r) => a + r.qty, 0);
    const withFee = inYear.filter((r) => r.fee > 0);
    const feeRate = withFee.length
      ? (withFee.reduce((a, r) => a + r.fee, 0) /
         withFee.reduce((a, r) => a + r.gross, 0)) * 100 : null;
    return { gross, fee, net, units, feeRate, feeRows: withFee.length,
             noFee: inYear.length - withFee.length, lines: inYear.length,
             orders: new Set(inYear.map((r) => r.s.order_id || r.s.id)).size };
  }, [inYear]);

  const byMonth = useMemo(() => {
    const m = new Map<string, { gross: number; fee: number; net: number; n: number }>();
    for (const r of inYear) {
      const k = year === 'all' ? `${r.year}-${String(r.month).padStart(2, '0')}`
                               : String(r.month).padStart(2, '0');
      const v = m.get(k) ?? { gross: 0, fee: 0, net: 0, n: 0 };
      v.gross += r.gross; v.fee += r.fee; v.net += r.net || r.gross - r.fee; v.n++;
      m.set(k, v);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [inYear, year]);

  const peak = Math.max(1, ...byMonth.map(([, v]) => v.gross));

  if (error) return (
    <><div className="eyebrow">Money</div><h1 className="title">Sales</h1>
    <div className="legend" style={{ borderColor: 'var(--danger)' }}>
      <span style={{ color: 'var(--danger)' }}>{error}</span></div></>
  );
  if (!sales) return (
    <><div className="eyebrow">Money</div><h1 className="title">Sales</h1>
    <p className="sub">Reading your sales records…</p></>
  );

  return (
    <>
      <div className="eyebrow">Money</div>
      <h1 className="title">Sales</h1>
      <p className="sub">
        {rows.length.toLocaleString()} sales recorded · what you sold and what you kept
      </p>

      <div className="toolbar">
        <select className="pick" value={String(year)}
                onChange={(e) => setYear(e.target.value === 'all' ? 'all' : +e.target.value)}>
          <option value="all">All years</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <span className="spacer" />
        <button className="btn sm" onClick={() => download(`sales-${stamp()}.csv`,
          toCsv(['Date','Title','Item number','Qty','Gross','Fee','Net','Source'],
            inYear.map((r) => [r.date, r.s.title, r.s.item_number, r.qty,
              r.gross.toFixed(2), r.fee.toFixed(2),
              (r.net || r.gross - r.fee).toFixed(2), r.s.source])))}>
          ⬇ Export these sales
        </button>
      </div>

      <div className="stats">
        <div className="stat"><div className="k">Gross sales</div>
          <div className="v">{money0(t.gross)}</div>
          <div className="n">what buyers paid, {t.orders.toLocaleString()} orders</div></div>
        <div className="stat stale"><div className="k">Fees</div>
          <div className="v">{money0(t.fee)}</div>
          <div className="n">what the marketplace took</div></div>
        <div className="stat fresh"><div className="k">Net kept</div>
          <div className="v">{money0(t.net)}</div>
          <div className="n">
            {t.noFee > 0
              ? `understated — no fees on ${t.noFee.toLocaleString()} of ${t.lines.toLocaleString()} sales`
              : 'gross minus fees, before card cost'}
          </div></div>
        <div className="stat cool"><div className="k">Your real fee rate</div>
          <div className="v">{t.feeRate === null ? '—' : t.feeRate.toFixed(1) + '%'}</div>
          <div className="n">measured on {t.feeRows.toLocaleString()} fee rows</div></div>
      </div>

      <p className="note" style={{ marginTop: 0 }}>
        <b>Where these come from.</b> Every row is a sale imported from an eBay orders report —
        no estimates. <b>Fees</b> are what eBay actually charged on these orders, so the rate above
        is yours and not the published schedule. <b>Net kept</b> is before what the cards cost you;
        that number lands once cost basis is filled in.
      </p>

      <h2 className="h2">By month{year === 'all' ? '' : ` — ${year}`}</h2>
      <div className="tablewrap">
        <div className="thead mo">
          <div>Month</div><div className="right">Gross</div><div className="right">Fees</div>
          <div className="right">Net</div><div className="right">Sales</div><div>Share</div>
        </div>
        <div className="scroller" style={{ maxHeight: 420 }}>
          {byMonth.map(([k, v]) => (
            <div key={k} className="trow mo">
              <div>{year === 'all' ? k : MONTHS[+k - 1] ?? k}</div>
              <div className="right">{usd(v.gross)}</div>
              <div className="right muted">{usd(v.fee)}</div>
              <div className="right" style={{ color: 'var(--fresh)' }}>{usd(v.net)}</div>
              <div className="right muted">{v.n}</div>
              <div><div className="bar" style={{ width: `${(v.gross / peak) * 100}%` }} /></div>
            </div>
          ))}
          {!byMonth.length && <p className="note" style={{ padding: 14 }}>No sales in that year.</p>}
        </div>
      </div>
    </>
  );
}
