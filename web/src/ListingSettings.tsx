import { useEffect, useState } from 'react';
import { API, getToken, post } from './api';
import { CARD_CONDITIONS } from './ebayAdd';

/* ------------------------------------------------------------------ *
 * Listing settings — everything eBay needs that is the same on every card.
 *
 * These used to be constants in the code, which meant changing a
 * shipping policy meant changing software. They are his, so they live
 * here and the listing file reads them.
 *
 * File Exchange takes business policies by NAME, not by id. A name
 * survives a policy being edited on eBay; the numeric id does not, and a
 * stale id rejects the whole upload.
 * ------------------------------------------------------------------ */

type S = {
  category: string; categoryTcg: string;
  location: string; postalCode: string; dispatchDays: string;
  duration: string; quantity: string;
  bestOffer: boolean; immediatePay: boolean;
  shippingProfile: string; paymentProfile: string; returnProfile: string;
  returnsAccepted: string; weightMajor: string; weightMinor: string;
  conditionDefault: string; description: string;
  storeCategories: Record<string, string>;
  shippingBands: { upTo: number; profile: string; profileId?: string }[];
  shippingProfileId?: string; paymentProfileId?: string; returnProfileId?: string;
  /** The policy list, pasted once from eBay, so these become dropdowns. */
  policyList?: { name: string; id: string; kind: string }[];
};

/**
 * Reads a pasted policy list.
 *
 * eBay writes them as "Flat: US_eBayStandardEnvelope $0.99, 2 busines
 * (332312490021)" — the id is right there in the brackets, which is why
 * pasting the list is as good as an API call for this one job.
 */
function parsePolicies(text: string, kind: string) {
  const out: { name: string; id: string; kind: string }[] = [];
  for (const raw of text.split('\n')) {
    const line = raw.trim().replace(/^[✓•\-\s]+/, '');
    if (!line || /^—?\s*select/i.test(line)) continue;
    const m = line.match(/^(.*?)\s*\((\d{6,})\)\s*$/);
    // A policy with no id in brackets is still usable by name.
    out.push(m ? { name: m[1].trim(), id: m[2], kind }
               : { name: line, id: '', kind });
  }
  return out;
}

const SPORTS = ['Baseball', 'Basketball', 'Football', 'Soccer', 'Hockey', 'Pokemon', 'Other'];

/** Paste box for the policy list. */
function PolicyPaste({ onParsed }: { onParsed: (r: ReturnType<typeof parsePolicies>) => void }) {
  const [text, setText] = useState('');
  const [kind, setKind] = useState('shipping');
  return (
    <div>
      <div className="rulerow" style={{ marginBottom: 6 }}>
        <label className="rulerow-item">These are
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="shipping">shipping policies</option>
            <option value="payment">payment policies</option>
            <option value="return">return policies</option>
          </select>
        </label>
        <button className="btn sm read" disabled={!text.trim()}
          onClick={() => { onParsed(parsePolicies(text, kind)); setText(''); }}>
          Read {parsePolicies(text, kind).length || ''} policies
        </button>
      </div>
      <textarea className="descbox" rows={4} value={text}
                placeholder={'Flat: US_eBayStandardEnvelope $0.99, 2 busines (332312490021)\n' +
                             'Up to $15\n$15 to $50 Ground\n…'}
                onChange={(e) => setText(e.target.value)} />
    </div>
  );
}

/** A policy menu once the list is known, a text box before that. */
function PolicyPick({ label, s, set, nameKey, idKey }: {
  label: string; s: S; set: (k: keyof S, v: any) => void;
  nameKey: keyof S; idKey: keyof S;
}) {
  const list = (s.policyList ?? []);
  if (!list.length) {
    return (
      <label className="rulerow-item" style={{ flex: '1 1 300px' }}>{label}
        <input value={String(s[nameKey] ?? '')}
               onChange={(e) => set(nameKey, e.target.value)} />
        <small>Paste your list above to pick from a menu instead.</small>
      </label>
    );
  }
  const current = String(s[idKey] || s[nameKey] || '');
  return (
    <label className="rulerow-item" style={{ flex: '1 1 300px' }}>{label}
      <select value={current} onChange={(e) => {
        const hit = list.find((p) => (p.id || p.name) === e.target.value);
        set(nameKey, hit?.name ?? '');
        set(idKey, hit?.id ?? '');
      }}>
        <option value="">— pick one —</option>
        {list.map((p) => (
          <option key={(p.id || p.name) + p.kind} value={p.id || p.name}>
            {p.name}{p.id ? ` (${p.id})` : ''}
          </option>
        ))}
      </select>
      {s[idKey] ? <small>Sent by id — safe against duplicate names.</small>
                : <small>No id known; sent by name.</small>}
    </label>
  );
}

export default function ListingSettings() {
  const [s, setS] = useState<S | null>(null);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${API}/api/listing-settings`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.json())
      .then((d) => setS(d.settings))
      .catch((e) => setError(e.message || String(e)));
  }, []);

  const save = async () => {
    if (!s) return;
    setMsg(''); setError('');
    try { await post('/api/listing-settings', s); setMsg('Saved. New listing files use these.'); }
    catch (e: any) { setError(e.message || String(e)); }
  };

  if (error) return (
    <><div className="eyebrow">Settings</div><h1 className="title">Listing defaults</h1>
    <div className="legend" style={{ borderColor: 'var(--danger)' }}>
      <span style={{ color: 'var(--danger)' }}>{error}</span></div></>
  );
  if (!s) return (
    <><div className="eyebrow">Settings</div><h1 className="title">Listing defaults</h1>
    <p className="sub">Loading…</p></>
  );

  const set = (k: keyof S, v: any) => setS({ ...s, [k]: v });
  const field = (k: keyof S, label: string, hint?: string, wide = false) => (
    <label className="rulerow-item" style={wide ? { flex: '1 1 100%' } : undefined}>
      {label}
      <input value={String(s[k] ?? '')} onChange={(e) => set(k, e.target.value)} />
      {hint && <small>{hint}</small>}
    </label>
  );

  return (
    <>
      <div className="eyebrow">Settings</div>
      <h1 className="title">Listing defaults</h1>
      <p className="sub">What goes on every card, so it is not typed on each one</p>

      <div className="legend">
        <span>
          eBay takes business policies by <b>name</b>, not by number — a name survives the
          policy being edited, a stale id rejects the whole upload.
        </span>
      </div>

      <div className="card2">
        <div className="lab">Business policies</div>
        <div className="sub2">
          Paste your policy list once and these become menus. In eBay → Account → Business
          policies, or from any policy dropdown, select the list and copy it — the id in
          brackets comes with it.
        </div>

        <PolicyPaste onParsed={(rows) =>
          set('policyList', [
            ...(s.policyList ?? []).filter((p) => !rows.some((r) => r.id && r.id === p.id)),
            ...rows,
          ])} />

        {!!(s.policyList ?? []).length && (
          <div className="muted" style={{ margin: '8px 0 12px' }}>
            {s.policyList!.length} policies known ·{' '}
            <button className="linkish" onClick={() => set('policyList', [])}>forget them</button>
          </div>
        )}

        <div className="rulerow">
          <PolicyPick label="Shipping policy" s={s} set={set}
                      nameKey="shippingProfile" idKey="shippingProfileId" />
          <PolicyPick label="Payment policy" s={s} set={set}
                      nameKey="paymentProfile" idKey="paymentProfileId" />
          <PolicyPick label="Return policy" s={s} set={set}
                      nameKey="returnProfile" idKey="returnProfileId" />
          <label className="rulerow-item">Returns
            <select value={s.returnsAccepted}
                    onChange={(e) => set('returnsAccepted', e.target.value)}>
              <option value="ReturnsNotAccepted">not accepted</option>
              <option value="ReturnsAccepted">accepted</option>
            </select>
          </label>
        </div>

        <p className="note" style={{ marginTop: 6 }}>
          Two of your policies read <b>Flat: US_eBayStandardEnvelope $0.99, 2 busines</b> —
          332312490021 and 332312496021. A duplicate name either rejects the upload or picks
          the wrong one, so the file sends the <b>id</b> wherever one is known.
        </p>
      </div>

      <div className="card2">
        <div className="lab">Shipping by price</div>
        <div className="sub2">
          eBay Standard Envelope is only valid up to $20 — a card above that needs a tracked
          policy, or the listing is rejected. Lowest band first; anything above every band
          uses the policy above.
        </div>
        {(s.shippingBands ?? []).map((b, i) => (
          <div className="rulerow" key={i}>
            <label className="rulerow-item">Up to $
              <input type="number" step="0.01" value={b.upTo}
                     onChange={(e) => {
                       const n = [...s.shippingBands];
                       n[i] = { ...b, upTo: +e.target.value };
                       set('shippingBands', n);
                     }} />
            </label>
            <label className="rulerow-item" style={{ flex: '1 1 340px' }}>use policy
              {(s.policyList ?? []).length ? (
                <select value={b.profileId || b.profile}
                        onChange={(e) => {
                          const hit = (s.policyList ?? []).find(
                            (p) => (p.id || p.name) === e.target.value);
                          const n = [...s.shippingBands];
                          n[i] = { ...b, profile: hit?.name ?? e.target.value,
                                   profileId: hit?.id ?? '' };
                          set('shippingBands', n);
                        }}>
                  <option value="">— pick one —</option>
                  {(s.policyList ?? []).map((p) => (
                    <option key={(p.id || p.name) + p.kind} value={p.id || p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input value={b.profile}
                       onChange={(e) => {
                         const n = [...s.shippingBands];
                         n[i] = { ...b, profile: e.target.value };
                         set('shippingBands', n);
                       }} />
              )}
            </label>
            <button className="btn sm"
                    onClick={() => set('shippingBands',
                      s.shippingBands.filter((_, j) => j !== i))}>×</button>
          </div>
        ))}
        <button className="btn sm" onClick={() => set('shippingBands',
          [...(s.shippingBands ?? []), { upTo: 20, profile: '' }])}>
          + Add a price band
        </button>
      </div>

      <div className="card2">
        <div className="lab">Store categories</div>
        <div className="sub2">
          A card is filed by its sport. Leave one blank and that sport is filed nowhere,
          which is what eBay does by default.
        </div>
        <div className="rulerow">
          {SPORTS.map((sp) => (
            <label key={sp} className="rulerow-item">{sp}
              <input value={s.storeCategories[sp] ?? ''}
                     placeholder="none"
                     onChange={(e) => set('storeCategories',
                       { ...s.storeCategories, [sp]: e.target.value })} />
            </label>
          ))}
        </div>
      </div>

      <div className="card2">
        <div className="lab">Where it ships from</div>
        <div className="rulerow">
          {field('location', 'Location', 'City, State')}
          {field('postalCode', 'ZIP')}
          {field('dispatchDays', 'Handling days')}
          {field('weightMajor', 'Weight lb')}
          {field('weightMinor', 'Weight oz')}
        </div>
      </div>

      <div className="card2">
        <div className="lab">The listing itself</div>
        <div className="rulerow">
          {field('category', 'Sports category ID', 'eBay 261328 = sports singles')}
          {field('categoryTcg', 'TCG category ID', '183454 = non-sport singles')}
          <label className="rulerow-item">Duration
            <select value={s.duration} onChange={(e) => set('duration', e.target.value)}>
              <option value="GTC">Good til cancelled</option>
              <option value="Days_30">30 days</option>
              <option value="Days_7">7 days</option>
            </select>
          </label>
          <label className="rulerow-item">Condition when ungraded
            <select value={s.conditionDefault}
                    onChange={(e) => set('conditionDefault', e.target.value)}>
              {CARD_CONDITIONS.map((c) => (
                <option key={c.id} value={c.id}>{c.label}</option>
              ))}
            </select>
            <small>eBay rejects an ungraded card without one.</small>
          </label>
          <label className="rulerow-item">
            <span>
              <input type="checkbox" checked={s.bestOffer}
                     onChange={(e) => set('bestOffer', e.target.checked)} /> Accept offers
            </span>
          </label>
          <label className="rulerow-item">
            <span>
              <input type="checkbox" checked={s.immediatePay}
                     onChange={(e) => set('immediatePay', e.target.checked)} /> Immediate payment
            </span>
          </label>
        </div>
      </div>

      <div className="card2">
        <div className="lab">Description</div>
        <div className="sub2">
          <code>{'{title}'}</code> is replaced per card. Plain HTML.
        </div>
        <textarea className="descbox" rows={5} value={s.description}
                  onChange={(e) => set('description', e.target.value)} />
      </div>

      <div className="selbar">
        <span className="muted">{msg || 'Not saved yet.'}</span>
        <span className="spacer" />
        <button className="btn read" onClick={save}>Save listing defaults</button>
      </div>

      <p className="note">
        <b>What this does not cover.</b> eBay needs the policy names to exist on your account
        already — these settings name them, they do not create them. If an upload is rejected
        for an unknown policy, the name here does not match the one on eBay exactly.
      </p>
    </>
  );
}
