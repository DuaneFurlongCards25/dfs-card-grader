import { useEffect, useState } from 'react';
import { API, Expired, fetchListings, getWho, signIn, signOut, type Listing, type Who } from './api';
import Inventory from './Inventory';
import Refresh from './Refresh';
import Reprice from './Reprice';
import Money from './Money';
import Boxes from './Boxes';
import Intake from './Intake';
import Settings from './Settings';
import Dashboard from './Dashboard';
import Lots from './Lots';

/* ------------------------------------------------------------------ *
 * The shell.
 *
 * A sidebar, not a top strip: eight screens do not fit across the top
 * without scrolling, and a scrolling tab strip hides whichever one you
 * are reaching for. Sections stay put, the open one shows its screens,
 * and the phone gets a bottom bar instead.
 * ------------------------------------------------------------------ */

type Tab =
  | 'Home' | 'Inventory' | 'Boxes' | 'Intake' | 'Refresh'
  | 'Reprice' | 'Money' | 'Lots' | 'Settings';

const NAV: { section: string; items: { tab: Tab; label: string }[] }[] = [
  { section: 'Dashboard', items: [{ tab: 'Home', label: 'Overview' }] },
  { section: 'Inventory', items: [
      { tab: 'Inventory', label: 'Listings' },
      { tab: 'Boxes', label: 'Boxes' },
      { tab: 'Intake', label: 'Intake' },
      { tab: 'Refresh', label: 'Refresh from eBay' },
  ] },
  { section: 'Pricing', items: [{ tab: 'Reprice', label: 'Reprice' }] },
  { section: 'Money', items: [
      { tab: 'Money', label: 'Sales' },
      { tab: 'Lots', label: 'Lots' },
  ] },
  { section: 'Settings', items: [{ tab: 'Settings', label: 'Connections' }] },
];

const sectionOf = (t: Tab) =>
  NAV.find((s) => s.items.some((i) => i.tab === t))?.section ?? 'Dashboard';

export default function App() {
  const [who, setWho] = useState<Who | null>(getWho());
  const [tab, setTab] = useState<Tab>('Home');
  const [rows, setRows] = useState<Listing[] | null>(null);
  const [loaded, setLoaded] = useState(0);
  const [error, setError] = useState('');
  const [theme, setTheme] = useState(localStorage.getItem('cp_theme') || 'dark');
  const [nonce, setNonce] = useState(0);
  const [shut, setShut] = useState(localStorage.getItem('cp_nav') === 'shut');
  // Selection lives here so a pick survives moving between screens —
  // tick cards on Listings, price them on Reprice.
  const [sel, setSel] = useState<Set<string>>(new Set());
  const reload = () => { setRows(null); setLoaded(0); setNonce((n) => n + 1); };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('cp_theme', theme);
  }, [theme]);
  useEffect(() => { localStorage.setItem('cp_nav', shut ? 'shut' : 'open'); }, [shut]);

  useEffect(() => {
    if (!who) return;
    let live = true;
    setError('');
    fetchListings((n) => live && setLoaded(n))
      .then((r) => live && setRows(r))
      .catch((e) => {
        if (!live) return;
        if (e instanceof Expired) { setWho(null); signOut(); return; }
        setError(e.message || String(e));
      });
    return () => { live = false; };
  }, [who, nonce]);

  if (!who) return <SignIn onIn={setWho} />;

  const open = sectionOf(tab);

  return (
    <div className={`app${shut ? ' shut' : ''}`}>
      <aside className="side">
        <div className="brand">
          <div>
            <div className="wordmark">CARD<b>PULSE</b></div>
            <div className="brandsub">Inventory management</div>
          </div>
          <button className="collapse" onClick={() => setShut(!shut)}
                  title={shut ? 'Show the menu' : 'Hide the menu'}>
            {shut ? '»' : '«'}
          </button>
        </div>

        <nav className="sections">
          {NAV.map((s) => {
            const on = s.section === open;
            return (
              <div key={s.section}>
                <button className={`section${on ? ' on' : ''}`}
                        onClick={() => setTab(s.items[0].tab)}>
                  {s.section}
                </button>
                {on && s.items.length > 1 && (
                  <div className="subs">
                    {s.items.map((i) => (
                      <button key={i.tab}
                              className={`sub${i.tab === tab ? ' on' : ''}`}
                              onClick={() => setTab(i.tab)}>
                        {i.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="sidefoot">
          <div className="sf-label">Quick</div>
          <div className="sf-grid">
            <button className="btn sm" onClick={() => setTab('Refresh')}>⟳ eBay file</button>
            <button className="btn sm" onClick={() => setTab('Intake')}>📸 Scans</button>
            <a className="btn sm" href={`${API}/scan`} target="_blank" rel="noreferrer">📱 Phone</a>
            <button className="btn sm" onClick={reload}>↻ Reload</button>
          </div>
          <div className="sf-who">
            <span className="muted">{who.name || who.slug}</span>
            <span className="spacer" />
            <button className="btn sm" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
              {theme === 'dark' ? '☀' : '☾'}
            </button>
            <button className="btn sm" onClick={signOut}>Out</button>
          </div>
        </div>
      </aside>

      <main className="page">
        {error && (
          <div className="legend" style={{ borderColor: 'var(--danger)' }}>
            <span style={{ color: 'var(--danger)' }}>Could not load your listings: {error}</span>
            <span className="spacer" />
            <button className="btn sm" onClick={() => location.reload()}>Try again</button>
          </div>
        )}

        {tab === 'Home' && <Dashboard onGo={(t) => setTab(t as Tab)} />}
        {tab === 'Inventory' && (rows ? <Inventory rows={rows} sel={sel} setSel={setSel} /> : <Loading n={loaded} />)}
        {tab === 'Boxes' && (rows ? <Boxes rows={rows} /> : <Loading n={loaded} />)}
        {tab === 'Reprice' && (rows ? <Reprice rows={rows} selected={sel} onClear={() => setSel(new Set())} /> : <Loading n={loaded} />)}
        {tab === 'Refresh' && (rows ? <Refresh rows={rows} onDone={reload} /> : <Loading n={loaded} />)}
        {tab === 'Money' && <Money />}
        {tab === 'Lots' && <Lots />}
        {tab === 'Intake' && <Intake />}
        {tab === 'Settings' && <Settings />}
      </main>

      <nav className="bottombar">
        {(['Home', 'Inventory', 'Boxes', 'Reprice'] as Tab[]).map((t) => (
          <button key={t} className={`bb${t === tab ? ' on' : ''}`} onClick={() => setTab(t)}>
            <span className="bbi">{
              t === 'Home' ? '📊' : t === 'Inventory' ? '🗂' : t === 'Boxes' ? '📦' : '$'
            }</span>
            {t === 'Inventory' ? 'Cards' : t}
          </button>
        ))}
      </nav>
    </div>
  );
}

function Loading({ n }: { n: number }) {
  return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Loading</h1>
      <p className="sub">{n ? `${n.toLocaleString()} listings read…` : 'Reading your listings…'}</p>
      <p className="note" style={{ maxWidth: 540 }}>
        This is the only wait. Everything loads once, then searching, filtering and sorting
        happen here in the browser with nothing to wait for.
      </p>
    </>
  );
}

function SignIn({ onIn }: { onIn: (w: Who) => void }) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const go = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim() || busy) return;
    setBusy(true); setErr('');
    try { onIn(await signIn(code)); }
    catch (x: any) { setErr(x.message || 'that code will not sign in'); }
    finally { setBusy(false); }
  };

  return (
    <div className="signin">
      <form className="box" onSubmit={go}>
        <div className="wordmark" style={{ fontSize: 18 }}>CARD<b>PULSE</b></div>
        <h1>Sign in</h1>
        <p className="muted" style={{ margin: 0 }}>Your access code.</p>
        <input value={code} onChange={(e) => setCode(e.target.value)}
               placeholder="DFS-XXXX-XXXX" autoComplete="off"
               autoCapitalize="characters" spellCheck={false} autoFocus />
        <button className="btn read" disabled={busy || !code.trim()}>
          {busy ? 'Checking…' : 'Sign in'}
        </button>
        {err && <div className="err">{err}</div>}
      </form>
    </div>
  );
}
