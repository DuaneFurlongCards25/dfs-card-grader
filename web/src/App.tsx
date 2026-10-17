import { useEffect, useState } from 'react';
import { Expired, fetchListings, getWho, signIn, signOut, type Listing, type Who } from './api';
import Inventory from './Inventory';

const TABS = ['Inventory', 'Orders', 'Pricing', 'Intake', 'Posts'] as const;
type Tab = (typeof TABS)[number];

export default function App() {
  const [who, setWho] = useState<Who | null>(getWho());
  const [tab, setTab] = useState<Tab>('Inventory');
  const [rows, setRows] = useState<Listing[] | null>(null);
  const [loaded, setLoaded] = useState(0);
  const [error, setError] = useState('');
  const [theme, setTheme] = useState(localStorage.getItem('cp_theme') || 'dark');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('cp_theme', theme);
  }, [theme]);

  useEffect(() => {
    if (!who) return;
    let live = true;
    setError('');
    fetchListings((n) => live && setLoaded(n))
      .then((r) => live && setRows(r))
      .catch((e) => {
        if (!live) return;
        // A dead session should say so and offer the way back, not hang.
        if (e instanceof Expired) { setWho(null); signOut(); return; }
        setError(e.message || String(e));
      });
    return () => { live = false; };
  }, [who]);

  if (!who) return <SignIn onIn={setWho} />;

  return (
    <div className="app">
      <header className="topbar">
        <div className="wordmark">CARD<b>PULSE</b></div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t} className={`tab${t === tab ? ' on' : ''}`} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        <button className="btn sm" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                title="Switch light / dark">
          {theme === 'dark' ? '☀' : '☾'}
        </button>
        <span className="muted hide-sm">{who.name || who.slug}</span>
        <button className="btn sm" onClick={signOut}>Sign out</button>
      </header>

      <main className="page">
        {error && (
          <div className="legend" style={{ borderColor: 'var(--danger)' }}>
            <span style={{ color: 'var(--danger)' }}>Could not load your listings: {error}</span>
            <span className="spacer" />
            <button className="btn sm" onClick={() => location.reload()}>Try again</button>
          </div>
        )}

        {tab === 'Inventory' && (
          rows
            ? <Inventory rows={rows} />
            : <Loading n={loaded} />
        )}

        {tab !== 'Inventory' && <Soon tab={tab} />}
      </main>
    </div>
  );
}

function Loading({ n }: { n: number }) {
  return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Listings</h1>
      <p className="sub">
        {n ? `${n.toLocaleString()} listings loaded…` : 'Reading your listings…'}
      </p>
      <p className="note" style={{ maxWidth: 540 }}>
        This is the only wait. Everything loads once, then searching, filtering
        and sorting happen here in the browser with nothing to wait for.
      </p>
    </>
  );
}

function Soon({ tab }: { tab: string }) {
  const what: Record<string, string> = {
    Orders:  'Daily sales, the sold-card detector and margins by lot.',
    Pricing: 'Bands, floors, rounding and a move cap, priced off CardHedger.',
    Intake:  'The phone scanner feeding straight into a draft listing.',
    Posts:   'Instagram and Facebook graphics from a picked card.',
  };
  return (
    <>
      <div className="eyebrow">{tab}</div>
      <h1 className="title">Not moved over yet</h1>
      <p className="sub">{what[tab]}</p>
      <p className="note" style={{ maxWidth: 560 }}>
        Still in CardPulse on Streamlit, and still working — nothing was switched
        off to build this. Tabs arrive here one at a time, and this one becomes
        real when its slice lands.
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
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="DFS-XXXX-XXXX"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          autoFocus
        />
        <button className="btn read" disabled={busy || !code.trim()}>
          {busy ? 'Checking…' : 'Sign in'}
        </button>
        {err && <div className="err">{err}</div>}
      </form>
    </div>
  );
}
