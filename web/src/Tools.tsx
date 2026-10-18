import { useEffect, useState } from 'react';
import { API, getToken, num, post, text } from './api';
import { usd } from './pricing';
import { download, stamp, toCsv } from './exports';

/* ------------------------------------------------------------------ *
 * Tools.
 *
 * Built for sports cards, not TCG. Leumas's buckets are commons,
 * uncommons, rares and holos; none of those mean anything on a Bowman
 * auto. The buckets here are the ones a sports buyer actually sorts
 * into — base, rookies, parallels, autos, relics, graded, vintage.
 * ------------------------------------------------------------------ */

type Tab = 'buylist' | 'filing' | 'search' | 'dupes' | 'team';

type BuyRow = {
  bucket: string; priced_as: string; amount: number | string;
  at_least: number | string; note: string; sort: number;
};
type FileRow = { matches: string; field: string; category: string; sort: number };
type TeamRow = { email: string; name: string; areas: string; active: boolean };

/** What a sports buyer sorts a box into. */
const SPORT_BUCKETS: BuyRow[] = [
  { bucket: 'Base cards',          priced_as: 'per1000', amount: 0, at_least: 0, note: '', sort: 0 },
  { bucket: 'Rookies',             priced_as: 'percent', amount: 0, at_least: 0, note: '', sort: 1 },
  { bucket: 'Numbered parallels',  priced_as: 'percent', amount: 0, at_least: 0, note: '', sort: 2 },
  { bucket: 'Autographs',          priced_as: 'percent', amount: 0, at_least: 0, note: '', sort: 3 },
  { bucket: 'Patches & relics',    priced_as: 'percent', amount: 0, at_least: 0, note: '', sort: 4 },
  { bucket: 'Graded slabs',        priced_as: 'percent', amount: 0, at_least: 0, note: '', sort: 5 },
  { bucket: 'Vintage (pre-1980)',  priced_as: 'percent', amount: 0, at_least: 0, note: '', sort: 6 },
];

const api = (p: string) =>
  fetch(API + p, { headers: { Authorization: `Bearer ${getToken()}` } }).then((r) => r.json());

export default function Tools() {
  const [tab, setTab] = useState<Tab>('search');
  return (
    <>
      <div className="eyebrow">Tools</div>
      <h1 className="title">Tools</h1>
      <p className="sub">The jobs that are not inventory, pricing or money</p>

      <div className="chips">
        {([['search', 'Card search'], ['dupes', 'Duplicates'], ['buylist', 'Buylist'],
           ['filing', 'Store categories'], ['team', 'Team access']] as [Tab, string][])
          .map(([k, label]) => (
            <button key={k} className={`chip${tab === k ? ' on' : ''}`}
                    onClick={() => setTab(k)}>{label}</button>
          ))}
      </div>

      {tab === 'search' && <Search />}
      {tab === 'dupes' && <Dupes />}
      {tab === 'buylist' && <Buylist />}
      {tab === 'filing' && <Filing />}
      {tab === 'team' && <Team />}
    </>
  );
}

/* ---------------- card search ---------------- */
function Search() {
  const [q, setQ] = useState('');
  const [r, setR] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.trim().length < 2) { setR(null); return; }
    const t = setTimeout(() => {
      setBusy(true);
      api(`/api/search?q=${encodeURIComponent(q.trim())}`)
        .then(setR).finally(() => setBusy(false));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>
        One box across everything — what is listed, what has sold, and what is waiting in the
        Hopper. Useful when a buyer asks "do you still have…".
      </p>
      <input className="search" style={{ width: '100%', fontSize: 16, padding: '12px 14px' }}
             placeholder="Player, set, SKU or item number…"
             value={q} onChange={(e) => setQ(e.target.value)} autoFocus />

      {busy && <p className="note">Looking…</p>}
      {r && (
        <>
          <h2 className="h2">Listed — {r.listings.length}</h2>
          <div className="tablewrap">
            {r.listings.slice(0, 40).map((l: any) => (
              <div key={l.item_number} className="trow simple">
                <div className="sku">{text(l.sku) || l.item_number}</div>
                <div className="cell-title">
                  {text(l.title)}
                  {l.ended_at && <span className="pill stale" style={{ marginLeft: 8 }}>ended</span>}
                </div>
                <div className="right">{usd(num(l.current_price) ?? 0)}</div>
              </div>
            ))}
            {!r.listings.length && <p className="note" style={{ padding: 14 }}>Nothing listed.</p>}
          </div>

          <h2 className="h2">Sold — {r.sales.length}</h2>
          <div className="tablewrap">
            {r.sales.slice(0, 25).map((s: any, i: number) => (
              <div key={i} className="trow simple">
                <div className="sku">{s.sale_date}</div>
                <div className="cell-title muted">{text(s.title)}</div>
                <div className="right">{usd(num(s.gross_revenue) ?? 0)}</div>
              </div>
            ))}
            {!r.sales.length && <p className="note" style={{ padding: 14 }}>No sales.</p>}
          </div>

          {!!r.scans?.length && (
            <>
              <h2 className="h2">In the Hopper — {r.scans.length}</h2>
              <div className="tablewrap">
                {r.scans.map((s: any) => (
                  <div key={s.id} className="trow simple">
                    <div className="sku">{text(s.sku) || `${s.stack_name}-${s.idx}`}</div>
                    <div className="cell-title">{text(s.title)}</div>
                    <div className="right muted">{s.status}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}

/* ---------------- duplicates ---------------- */
function Dupes() {
  const [groups, setGroups] = useState<any[] | null>(null);
  const [busy, setBusy] = useState(false);

  const scan = () => {
    setBusy(true);
    api('/api/duplicates').then((d) => setGroups(d.groups ?? [])).finally(() => setBusy(false));
  };

  const total = (groups ?? []).reduce((a, g) => a + (g.copies - 1), 0);

  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>
        The same card listed more than once. Matched on the title, because two listings of one
        card were made separately and have different SKUs by definition.
        <b> Graded slabs are left out</b> — two PSA 10s of a card are genuinely two listings.
      </p>
      <div className="toolbar">
        <button className="btn read" onClick={scan} disabled={busy}>
          {busy ? 'Looking…' : 'Find duplicates'}
        </button>
        {groups && (
          <>
            <span className="muted">
              {groups.length} cards listed twice or more · {total} extra listings
            </span>
            <span className="spacer" />
            <button className="btn sm" onClick={() => download(`duplicates-${stamp()}.csv`,
              toCsv(['Title', 'Copies', 'SKUs', 'Item numbers', 'Prices'],
                groups.map((g) => [
                  g.cards[0].title, g.copies,
                  g.cards.map((c: any) => c.sku).join(' | '),
                  g.cards.map((c: any) => c.item_number).join(' | '),
                  g.cards.map((c: any) => c.price).join(' | '),
                ])))}>⬇ Export</button>
          </>
        )}
      </div>

      {groups?.map((g, i) => (
        <div key={i} className="card2">
          <div className="lab">{g.cards[0].title} <span className="pill watch">{g.copies} listings</span></div>
          <div className="tablewrap" style={{ marginTop: 8 }}>
            {g.cards.map((c: any) => (
              <div key={c.item_number} className="trow simple">
                <div className="sku">{c.sku || c.item_number}</div>
                <div className="cell-title muted">{(c.listed || '').slice(0, 10)}</div>
                <div className="right">{usd(num(c.price) ?? 0)}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {groups && !groups.length &&
        <p className="note">No duplicates — every live card is listed once.</p>}
    </>
  );
}

/* ---------------- buylist ---------------- */
function Buylist() {
  const [rows, setRows] = useState<BuyRow[] | null>(null);
  const [msg, setMsg] = useState('');

  useEffect(() => { api('/api/tools/buylist').then((d) => setRows(d.rows ?? [])); }, []);
  const save = async () => {
    await post('/api/tools/buylist', { rows });
    setMsg('Saved.');
  };

  if (!rows) return <p className="note">Loading…</p>;

  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>
        What you pay, by the kind of card. Buckets are the ones a sports buyer sorts into —
        not the commons and holos a Pokémon list uses. <b>Dollars per 1,000</b> is for base
        bulk; <b>percent of comp</b> pays a share of what CardHedger says the card is worth,
        with a floor beside it.
      </p>

      <div className="toolbar">
        <button className="btn sm" onClick={() => setRows([...rows, {
          bucket: '', priced_as: 'percent', amount: 0, at_least: 0, note: '', sort: rows.length,
        }])}>+ Add a bucket</button>
        {!rows.length && (
          <button className="btn sm" onClick={() => setRows(SPORT_BUCKETS)}>
            Start with the usual sports buckets
          </button>
        )}
        <span className="spacer" />
        <span className="muted">{msg}</span>
        <button className="btn read" onClick={save}>Save buylist</button>
      </div>

      <div className="tablewrap">
        <div className="thead buy">
          <div>Bucket</div><div>Priced as</div><div className="right">Amount</div>
          <div className="right">At least each</div><div>Note</div><div />
        </div>
        {rows.map((r, i) => {
          const upd = (patch: Partial<BuyRow>) =>
            setRows(rows.map((x, j) => (j === i ? { ...x, ...patch } : x)));
          return (
            <div key={i} className="trow buy">
              <input value={r.bucket} placeholder="Rookies"
                     onChange={(e) => upd({ bucket: e.target.value })} />
              <select value={r.priced_as} onChange={(e) => upd({ priced_as: e.target.value })}>
                <option value="percent">% of comp</option>
                <option value="per1000">$ per 1,000</option>
                <option value="flat">$ each</option>
              </select>
              <input className="right" type="number" step="0.01" value={String(r.amount ?? '')}
                     onChange={(e) => upd({ amount: e.target.value })} />
              <input className="right" type="number" step="0.01" value={String(r.at_least ?? '')}
                     onChange={(e) => upd({ at_least: e.target.value })} />
              <input value={r.note ?? ''} placeholder="optional"
                     onChange={(e) => upd({ note: e.target.value })} />
              <button className="btn sm"
                      onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
            </div>
          );
        })}
        {!rows.length && <p className="note" style={{ padding: 14 }}>No buckets yet.</p>}
      </div>
    </>
  );
}

/* ---------------- store categories ---------------- */
function Filing() {
  const [rows, setRows] = useState<FileRow[] | null>(null);
  const [msg, setMsg] = useState('');
  useEffect(() => { api('/api/tools/filing_rules').then((d) => setRows(d.rows ?? [])); }, []);

  if (!rows) return <p className="note">Loading…</p>;
  const save = async () => { await post('/api/tools/filing_rules', { rows }); setMsg('Saved.'); };

  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>
        Which eBay store category a card is filed under. Checked top to bottom — the first rule
        that matches wins, so put the narrow ones first. Your store has Baseball Cards,
        Basketball Cards, Football Cards, Soccer Cards, TCG/Pokemon, Vintage and Other.
      </p>
      <div className="toolbar">
        <button className="btn sm" onClick={() => setRows([...rows,
          { matches: '', field: 'sport', category: '', sort: rows.length }])}>+ Add a rule</button>
        {!rows.length && (
          <button className="btn sm" onClick={() => setRows([
            { matches: 'pre-1980',   field: 'year',  category: 'Vintage', sort: 0 },
            { matches: 'Baseball',   field: 'sport', category: 'Baseball Cards', sort: 1 },
            { matches: 'Basketball', field: 'sport', category: 'Basketball Cards', sort: 2 },
            { matches: 'Football',   field: 'sport', category: 'Football Cards', sort: 3 },
            { matches: 'Soccer',     field: 'sport', category: 'Soccer Cards', sort: 4 },
            { matches: 'Pokemon',    field: 'sport', category: 'TCG/Pokemon', sort: 5 },
          ])}>Start with your store's categories</button>
        )}
        <span className="spacer" />
        <span className="muted">{msg}</span>
        <button className="btn read" onClick={save}>Save rules</button>
      </div>

      <div className="tablewrap">
        <div className="thead buy">
          <div>When the</div><div>is / contains</div><div className="right" /><div className="right" />
          <div>file under</div><div />
        </div>
        {rows.map((r, i) => {
          const upd = (p: Partial<FileRow>) =>
            setRows(rows.map((x, j) => (j === i ? { ...x, ...p } : x)));
          return (
            <div key={i} className="trow buy">
              <select value={r.field} onChange={(e) => upd({ field: e.target.value })}>
                <option value="sport">sport</option>
                <option value="year">year</option>
                <option value="title">title</option>
                <option value="set_name">set</option>
              </select>
              <input value={r.matches} placeholder="Baseball"
                     onChange={(e) => upd({ matches: e.target.value })} />
              <div /><div />
              <input value={r.category} placeholder="Baseball Cards"
                     onChange={(e) => upd({ category: e.target.value })} />
              <button className="btn sm"
                      onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
            </div>
          );
        })}
        {!rows.length && <p className="note" style={{ padding: 14 }}>No rules yet.</p>}
      </div>
    </>
  );
}

/* ---------------- team access ---------------- */
function Team() {
  const [rows, setRows] = useState<TeamRow[] | null>(null);
  const [msg, setMsg] = useState('');
  useEffect(() => { api('/api/tools/team_access').then((d) => setRows(d.rows ?? [])); }, []);
  if (!rows) return <p className="note">Loading…</p>;
  const save = async () => { await post('/api/tools/team_access', { rows }); setMsg('Saved.'); };

  const AREAS = ['Inventory', 'Hopper', 'Pricing', 'Orders', 'Money'];

  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>
        Who else can work in here, and on what. <b>Money is off by default</b> — someone
        scanning cards does not need to see what the business made.
      </p>
      <div className="toolbar">
        <button className="btn sm" onClick={() => setRows([...rows,
          { email: '', name: '', areas: 'Inventory,Hopper', active: true }])}>
          + Add someone
        </button>
        <span className="spacer" />
        <span className="muted">{msg}</span>
        <button className="btn read" onClick={save}>Save access</button>
      </div>

      {rows.map((r, i) => {
        const upd = (p: Partial<TeamRow>) =>
          setRows(rows.map((x, j) => (j === i ? { ...x, ...p } : x)));
        const has = (a: string) => (r.areas || '').split(',').includes(a);
        return (
          <div key={i} className="card2">
            <div className="rulerow">
              <label className="rulerow-item" style={{ flex: '1 1 240px' }}>Email
                <input value={r.email} onChange={(e) => upd({ email: e.target.value })} /></label>
              <label className="rulerow-item">Name
                <input value={r.name ?? ''} onChange={(e) => upd({ name: e.target.value })} /></label>
              <label className="rulerow-item">
                <span><input type="checkbox" checked={r.active !== false}
                             onChange={(e) => upd({ active: e.target.checked })} /> Active</span>
              </label>
              <button className="btn sm danger"
                      onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button>
            </div>
            <div className="chips2">
              {AREAS.map((a) => (
                <button key={a} className={`chip${has(a) ? ' on' : ''}`}
                        onClick={() => {
                          const set = new Set((r.areas || '').split(',').filter(Boolean));
                          has(a) ? set.delete(a) : set.add(a);
                          upd({ areas: [...set].join(',') });
                        }}>{a}</button>
              ))}
            </div>
          </div>
        );
      })}
      {!rows.length && <p className="note">Nobody else has access.</p>}

      <p className="note">
        <b>Not wired to sign-in yet.</b> This records who should have what; access codes are
        still issued the old way. Say the word and I will connect the two.
      </p>
    </>
  );
}
