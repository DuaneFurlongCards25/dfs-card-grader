import { useState } from 'react';
import { type Listing, num, post, text } from './api';

/* ------------------------------------------------------------------ *
 * Refresh from the eBay active-listings report.
 *
 * There is no eBay API and there never will be, so this file IS the sync.
 * The whole point of the screen is the middle column: cards in CardPulse
 * that are NOT in the report have sold or been ended. Catching those is
 * what stops a sold card going back up for sale, and it is the one thing
 * that must never happen silently — so nothing is removed until he has
 * seen the list and pressed the button.
 * ------------------------------------------------------------------ */

const money = (n: number | null) =>
  n === null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });

/** eBay writes "May-31-25 19:56:24 PDT". Postgres will not take that. */
function ebayDate(s: string): string {
  const m = s.match(/^([A-Za-z]{3})-(\d{2})-(\d{2})\s+(\d{2}:\d{2}:\d{2})\s*([A-Z]{3})?$/);
  if (!m) return '';
  const months: Record<string, string> = {
    jan: '01', feb: '02', mar: '03', apr: '04', may: '05', jun: '06',
    jul: '07', aug: '08', sep: '09', oct: '10', nov: '11', dec: '12',
  };
  const mo = months[m[1].toLowerCase()];
  if (!mo) return '';
  // PDT/PST are the only zones eBay writes for this account.
  const off = m[5] === 'PDT' ? '-07:00' : m[5] === 'PST' ? '-08:00' : '+00:00';
  return `20${m[3]}-${mo}-${m[2]}T${m[4]}${off}`;
}

/** A CSV parser that copes with quoted commas, which card titles are full of. */
function parseCsv(input: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = '', quoted = false;
  const s = input.replace(/^﻿/, '');
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quoted) {
      if (c === '"') {
        if (s[i + 1] === '"') { cell += '"'; i++; } else quoted = false;
      } else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((x) => x.trim()));
}

type Parsed = {
  item_number: string; title: string; sku: string;
  current_price: number | null; start_date: string; end_date: string;
  watchers: number; sold_qty: number; condition: string;
  grader: string; grade: string; cert_number: string;
};

function readReport(csv: string): { rows: Parsed[]; problem?: string } {
  const table = parseCsv(csv);
  if (table.length < 2) return { rows: [], problem: 'that file has no rows in it' };
  const head = table[0].map((h) => h.trim().toLowerCase());
  const at = (...names: string[]) => {
    for (const n of names) {
      const i = head.findIndex((h) => h === n || h.startsWith(n));
      if (i >= 0) return i;
    }
    return -1;
  };
  const cItem = at('item number');
  const cTitle = at('title');
  if (cItem < 0 || cTitle < 0)
    return { rows: [], problem: 'this does not look like an eBay active-listings report — no "Item number" column' };

  const cSku = at('custom label');
  const cPrice = at('current price', 'start price');
  const cStart = at('start date');
  const cEnd = at('end date');
  const cWatch = at('watchers');
  const cSold = at('sold quantity');
  const cCond = at('condition');
  const cGrader = at('cd:professional grader');
  const cGrade = at('cd:grade');
  const cCert = at('cda:certification number');

  const get = (r: string[], i: number) => (i >= 0 ? (r[i] ?? '').trim() : '');
  const rows = table.slice(1).map((r) => ({
    item_number: get(r, cItem),
    title: get(r, cTitle),
    sku: get(r, cSku),
    current_price: num(get(r, cPrice)),
    start_date: ebayDate(get(r, cStart)),
    end_date: ebayDate(get(r, cEnd)),
    watchers: num(get(r, cWatch)) ?? 0,
    sold_qty: num(get(r, cSold)) ?? 0,
    condition: get(r, cCond),
    grader: get(r, cGrader),
    grade: get(r, cGrade),
    cert_number: get(r, cCert),
  })).filter((x) => x.item_number);

  return { rows };
}

type Diff = {
  fresh: Parsed[];
  added: Parsed[];
  priced: { row: Parsed; was: number | null }[];
  gone: Listing[];
};

export default function Refresh({ rows, onDone }: { rows: Listing[]; onDone: () => void }) {
  const [diff, setDiff] = useState<Diff | null>(null);
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState('');
  const [result, setResult] = useState('');

  const onFile = async (file: File) => {
    setProblem(''); setDiff(null); setResult('');
    const { rows: parsed, problem: p } = readReport(await file.text());
    if (p) return setProblem(p);
    if (!parsed.length) return setProblem('no listings found in that file');

    const have = new Map(rows.map((l) => [l.item_number, l]));
    const inFile = new Set(parsed.map((r) => r.item_number));
    setDiff({
      fresh: parsed,
      added: parsed.filter((r) => !have.has(r.item_number)),
      priced: parsed.flatMap((r) => {
        const old = have.get(r.item_number);
        if (!old) return [];
        const was = num(old.current_price);
        return was !== null && r.current_price !== null && Math.abs(was - r.current_price) > 0.004
          ? [{ row: r, was }] : [];
      }),
      gone: rows.filter((l) => !inFile.has(l.item_number)),
    });
  };

  const apply = async () => {
    if (!diff) return;
    setBusy('Writing the report into CardPulse…');
    try {
      // 4,500 rows is well inside one request, but chunk anyway so a big
      // report cannot hit a body limit and fail after a partial write.
      let sent = 0;
      for (let i = 0; i < diff.fresh.length; i += 2000) {
        const chunk = diff.fresh.slice(i, i + 2000);
        await post('/api/listings/refresh', { rows: chunk });
        sent += chunk.length;
        setBusy(`Written ${sent.toLocaleString()} of ${diff.fresh.length.toLocaleString()}…`);
      }
      setResult(`${sent.toLocaleString()} listings are now current.`);
      setDiff({ ...diff, added: [], priced: [] });
      onDone();
    } catch (e: any) {
      setProblem(e.message || String(e));
    } finally { setBusy(''); }
  };

  const retire = async () => {
    if (!diff?.gone.length) return;
    if (!confirm(
      `Remove ${diff.gone.length} listings from CardPulse?\n\n` +
      `These are not in the eBay report, so they have sold or been ended. ` +
      `Removing them here is what stops them being relisted. ` +
      `Nothing on eBay is touched.`)) return;
    setBusy('Removing…');
    try {
      const ids = diff.gone.map((l) => l.item_number);
      const r = await post('/api/listings/retire', { item_numbers: ids });
      setResult(`${r.removed} listings removed. They can no longer be exported or relisted.`);
      setDiff({ ...diff, gone: [] });
      onDone();
    } catch (e: any) {
      setProblem(e.message || String(e));
    } finally { setBusy(''); }
  };

  const goneValue = (diff?.gone ?? []).reduce((a, l) => a + (num(l.current_price) ?? 0), 0);

  return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Refresh from eBay</h1>
      <p className="sub">
        Seller Hub → Listings → Active → Download. Drop that file here.
      </p>

      <label className="drop">
        <input
          type="file" accept=".csv,text/csv" style={{ display: 'none' }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ''; }}
        />
        <b>Choose your active-listings report</b>
        <span className="muted">Read here in your browser. Nothing is saved until you say so.</span>
      </label>

      {problem && <div className="legend" style={{ borderColor: 'var(--danger)', marginTop: 16 }}>
        <span style={{ color: 'var(--danger)' }}>{problem}</span>
      </div>}

      {busy && <p className="note">{busy}</p>}
      {result && <div className="legend" style={{ borderColor: 'var(--read)', marginTop: 16 }}>
        <span style={{ color: 'var(--read)' }}>{result}</span>
      </div>}

      {diff && (
        <>
          <div className="stats" style={{ marginTop: 18 }}>
            <div className="stat"><div className="k">In the report</div>
              <div className="v">{diff.fresh.length.toLocaleString()}</div>
              <div className="n">live on eBay right now</div></div>
            <div className="stat fresh"><div className="k">New to CardPulse</div>
              <div className="v">{diff.added.length.toLocaleString()}</div>
              <div className="n">listed since the last refresh</div></div>
            <div className="stat cool"><div className="k">Price changed</div>
              <div className="v">{diff.priced.length.toLocaleString()}</div>
              <div className="n">different from what we hold</div></div>
            <div className="stat stale"><div className="k">Sold or ended</div>
              <div className="v">{diff.gone.length.toLocaleString()}</div>
              <div className="n">{money(goneValue)} — not on eBay any more</div></div>
          </div>

          <div className="selbar">
            <span className="n">Nothing has changed yet.</span>
            <span className="spacer" />
            <button className="btn read" onClick={apply} disabled={!!busy}>
              Make CardPulse match the report
            </button>
            {diff.gone.length > 0 && (
              <button className="btn write" onClick={retire} disabled={!!busy}>
                Remove the {diff.gone.length} sold or ended
              </button>
            )}
          </div>

          {diff.gone.length > 0 && (
            <>
              <h2 className="h2">Sold or ended — {diff.gone.length}</h2>
              <p className="note" style={{ marginTop: 0 }}>
                These are in CardPulse but not in the report. Until they are removed they can
                still be exported to Card Luma or the website, which is how a sold card gets
                listed twice.
              </p>
              <div className="tablewrap">
                <div className="scroller" style={{ maxHeight: 320 }}>
                  {diff.gone.slice(0, 400).map((l) => (
                    <div key={l.item_number} className="trow simple">
                      <div className="sku">{text(l.sku) || l.item_number}</div>
                      <div className="cell-title">{text(l.title)}</div>
                      <div className="right">{money(num(l.current_price))}</div>
                    </div>
                  ))}
                </div>
              </div>
              {diff.gone.length > 400 &&
                <p className="note">Showing the first 400 of {diff.gone.length}.</p>}
            </>
          )}

          {diff.priced.length > 0 && (
            <>
              <h2 className="h2">Price changed on eBay — {diff.priced.length}</h2>
              <div className="tablewrap">
                <div className="scroller" style={{ maxHeight: 280 }}>
                  {diff.priced.slice(0, 400).map(({ row, was }) => (
                    <div key={row.item_number} className="trow simple">
                      <div className="sku">{row.sku || row.item_number}</div>
                      <div className="cell-title">{row.title}</div>
                      <div className="right">
                        <span className="muted">{money(was)}</span>
                        {' → '}
                        <b>{money(row.current_price)}</b>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </>
      )}

      <p className="note">
        eBay does not give this account an API, so this report is the sync — there is no live
        connection to be out of date with. The report is the truth about what is listed;
        everything else on a card (what it cost, its comp, its suggested price) is ours and is
        never overwritten by a refresh.
      </p>
    </>
  );
}
