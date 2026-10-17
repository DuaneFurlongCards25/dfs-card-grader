import { useEffect, useState } from 'react';
import { API, getToken } from './api';

/* ------------------------------------------------------------------ *
 * Settings — connecting the marketplaces.
 *
 * The eBay part is the one that matters. It is the difference between
 * downloading a report and uploading a file, and the app doing it.
 * ------------------------------------------------------------------ */

type Status = {
  configured: boolean;
  connected: boolean;
  connected_at: string | null;
  recent_calls: number;
  recent_failures: number;
  next_step: string | null;
};

export default function Settings() {
  const [s, setS] = useState<Status | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const r = await fetch(`${API}/api/ebay/status`,
        { headers: { Authorization: `Bearer ${getToken()}` } });
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error || `HTTP ${r.status}`);
      setS(d);
    } catch (e: any) { setError(e.message || String(e)); }
  };
  useEffect(() => { load(); }, []);

  const connect = async () => {
    try {
      const r = await fetch(`${API}/api/ebay/connect`,
        { headers: { Authorization: `Bearer ${getToken()}` } });
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error || `HTTP ${r.status}`);
      // eBay's consent page, in a new tab so this one keeps its state.
      window.open(d.url, '_blank', 'noopener');
    } catch (e: any) { setError(e.message || String(e)); }
  };

  return (
    <>
      <div className="eyebrow">Settings</div>
      <h1 className="title">Connections</h1>
      <p className="sub">Where CardPulse can act for you, and where it still hands you a file</p>

      {error && (
        <div className="legend" style={{ borderColor: 'var(--danger)' }}>
          <span style={{ color: 'var(--danger)' }}>{error}</span>
          <span className="spacer" />
          <button className="btn sm" onClick={load}>Try again</button>
        </div>
      )}

      <div className="card2">
        <div className="row">
          <div style={{ flex: 1 }}>
            <div className="lab">
              eBay{' '}
              <span className={`pill ${s?.connected ? 'fresh' : s?.configured ? 'watch' : 'cool'}`}>
                {s?.connected ? 'connected' : s?.configured ? 'ready to connect' : 'not set up'}
              </span>
            </div>
            <div className="sub2">
              {s?.connected
                ? `Connected ${s.connected_at ? new Date(s.connected_at).toLocaleDateString() : ''} · ` +
                  `${s.recent_calls} calls this week` +
                  (s.recent_failures ? `, ${s.recent_failures} failed` : '')
                : 'Listing, repricing, ending and orders — straight onto eBay, no CSV.'}
            </div>
          </div>
          {s?.configured && (
            <button className="btn read" onClick={connect}>
              {s.connected ? 'Reconnect' : 'Connect eBay'}
            </button>
          )}
        </div>

        {s && !s.configured && (
          <div className="setup">
            <p className="note" style={{ marginTop: 10 }}>
              <b>This needs about ten minutes of your time, once.</b> I can write every line of
              code but not register the app — that happens under your eBay login.
            </p>
            <ol className="steps">
              <li>
                Go to <a href="https://developer.ebay.com/join" target="_blank" rel="noreferrer">
                developer.ebay.com/join</a> and sign up with your business email.
                Approval takes about a business day.
              </li>
              <li>
                Application Keys → create a <b>Production</b> keyset. It stays disabled until you
                either subscribe to, or <b>opt out of</b>, marketplace account-deletion
                notifications. Opting out is fine — CardPulse stores no eBay user data.
              </li>
              <li>
                On that keyset, add a redirect (eBay calls it an <b>RuName</b>) pointing at:<br />
                <code>{API}/api/ebay/callback</code>
              </li>
              <li>
                Send me the <b>App ID</b>, <b>Cert ID</b> and <b>RuName</b> and I will put them on
                the Worker as secrets. They never go in the browser.
              </li>
              <li>Come back here and press <b>Connect eBay</b>.</li>
            </ol>
            <p className="note">
              <b>What you are not applying for.</b> The Sell APIs — listing, revising, ending,
              reading your own orders — need no partner status. Only eBay's <i>Buy</i> APIs, the
              ones returning sold prices, are partner-gated, and nobody gets those: that is why
              every card app prices off TCGplayer or CardHedger instead.
            </p>
          </div>
        )}
      </div>

      <div className="card2">
        <div className="row">
          <div style={{ flex: 1 }}>
            <div className="lab">CardHedger <span className="pill fresh">connected</span></div>
            <div className="sub2">
              Comps for sports cards. About half of ordinary stock has a price; rare autos and
              patches have none anywhere, so those price on age instead.
            </div>
          </div>
        </div>
      </div>

      <div className="card2">
        <div className="row">
          <div style={{ flex: 1 }}>
            <div className="lab">Phone scanner <span className="pill fresh">connected</span></div>
            <div className="sub2">
              Shoot a stack at <code>{API.replace('https://', '')}/scan</code> — photos upload as
              you go and appear on the Intake tab.
            </div>
          </div>
        </div>
      </div>

      <div className="card2">
        <div className="row">
          <div style={{ flex: 1 }}>
            <div className="lab">
              DC Sports · CollX · Shopify <span className="pill cool">by file</span>
            </div>
            <div className="sub2">
              Still import and export by spreadsheet. Sales from all three already land in Money.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
