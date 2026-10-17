import { useState } from 'react';
import { post, type Listing, text } from './api';
import { download, fileExchangeRevise, stamp, toCsv } from './exports';

/* ------------------------------------------------------------------ *
 * Titles — your format, applied to the cards you pick.
 *
 *   [CAP_NAME] [YEAR] [BRAND] [PRODUCT] [VARIETY] [PARALLEL] [SERIAL]
 *   [GRADE] [ATTRIBUTES] [TEAM_NICK]
 *
 * Nothing is written and nothing is uploaded. Every row is shown before
 * and after; you untick what you disagree with and the file carries only
 * what is left. A title is the search hook on a listing, so a bad one
 * applied in bulk is expensive to undo.
 * ------------------------------------------------------------------ */

type Suggestion = {
  item_number: string; sku: string; before: string; after: string;
  changed: boolean; length: number; trimmed: string[];
  confidence: number; player: string | null; needs_team: boolean; note: string;
};

export default function Titles({ rows, selected }: { rows: Listing[]; selected: Set<string> }) {
  const [out, setOut] = useState<Suggestion[]>([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [skip, setSkip] = useState<Set<string>>(new Set());

  const picked = rows.filter((l) => selected.has(l.item_number) && !l.ended_at);

  const run = async () => {
    setError(''); setOut([]); setSkip(new Set());
    const ids = picked.map((l) => l.item_number);
    const found: Suggestion[] = [];
    try {
      for (let i = 0; i < ids.length; i += 25) {
        const chunk = ids.slice(i, i + 25);
        setBusy(`Working through ${i + 1}–${i + chunk.length} of ${ids.length}…`);
        const r = await post('/api/titles/suggest', { item_numbers: chunk });
        found.push(...(r.suggestions ?? []));
        setOut([...found]);
      }
      setBusy('');
    } catch (e: any) { setError(e.message || String(e)); setBusy(''); }
  };

  const changed = out.filter((s) => s.changed && !skip.has(s.item_number));
  const tooLong = changed.filter((s) => s.length > 80);
  const noTeam = changed.filter((s) => s.needs_team);
  const unsure = changed.filter((s) => s.confidence < 0.7);

  const toggle = (id: string) =>
    setSkip((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  if (!picked.length) return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Titles</h1>
      <p className="sub">Tick some cards on Listings, then come back.</p>
      <p className="note" style={{ maxWidth: 580 }}>
        Rewrites a title into your slot order — name in caps first, then year, set, card number,
        parallel, serial, grade, RC/AU, team nickname — trims to 80 characters by sacrificing
        filler, then the city, then the sport word, and never the parallel or the card number.
      </p>
    </>
  );

  return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Titles</h1>
      <p className="sub">{picked.length.toLocaleString()} cards picked</p>

      <div className="legend">
        <span><b className="r">Blue</b> proposes.</span>
        <span><b className="w">Gold</b> makes a file for eBay — you upload it yourself.</span>
      </div>

      <div className="toolbar">
        <button className="btn read" onClick={run} disabled={!!busy}>
          {busy ? 'Working…' : `Suggest titles for ${picked.length}`}
        </button>
        {busy && <span className="muted">{busy}</span>}
        {error && <span style={{ color: 'var(--danger)' }}>{error}</span>}
      </div>

      {!!out.length && (
        <>
          <div className="stats">
            <div className="stat"><div className="k">Would change</div>
              <div className="v">{changed.length}</div>
              <div className="n">of {out.length} looked at</div></div>
            <div className="stat watch"><div className="k">No team</div>
              <div className="v">{noTeam.length}</div>
              <div className="n">a team is never guessed</div></div>
            <div className="stat cool"><div className="k">Catalogue unsure</div>
              <div className="v">{unsure.length}</div>
              <div className="n">reformatted from the title only</div></div>
            <div className="stat stale"><div className="k">Still over 80</div>
              <div className="v">{tooLong.length}</div>
              <div className="n">eBay will reject these</div></div>
          </div>

          <div className="selbar">
            <span className="n">{changed.length} ready</span>
            <span className="spacer" />
            <button className="btn" disabled={!changed.length}
              onClick={() => download(`titles-review-${stamp()}.csv`,
                toCsv(['SKU', 'Item number', 'Before', 'After', 'Length', 'Needs team', 'Confidence'],
                  changed.map((s) => [s.sku, s.item_number, s.before, s.after,
                    s.length, s.needs_team ? 'yes' : '', s.confidence.toFixed(2)])))}>
              ⬇ Review file
            </button>
            <button className="btn write" disabled={!changed.length || !!tooLong.length}
              onClick={() => {
                const head = 'Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)';
                download(`ebay-titles-${stamp()}.csv`,
                  toCsv([head, 'ItemID', 'Title'],
                    changed.map((s) => ['Revise', s.item_number, s.after])));
              }}>
              ⬆ eBay title file ({changed.length})
            </button>
          </div>

          {!!tooLong.length && (
            <div className="legend" style={{ borderColor: 'var(--danger)' }}>
              <span style={{ color: 'var(--danger)' }}>
                {tooLong.length} would still be over 80 characters — eBay rejects those rows.
              </span>
              <span className="muted">Untick them, or shorten the set name by hand first.</span>
            </div>
          )}

          <div className="tablewrap">
            <div className="scroller" style={{ maxHeight: 560 }}>
              {out.filter((s) => s.changed).map((s) => {
                const off = skip.has(s.item_number);
                return (
                  <div key={s.item_number} className={`tit${off ? ' off' : ''}`}>
                    <input type="checkbox" checked={!off}
                           onChange={() => toggle(s.item_number)}
                           aria-label={`Use the new title for ${s.sku}`} />
                    <div>
                      <div className="t-before">{s.before}</div>
                      <div className="t-after">
                        {s.after}
                        <span className={`len${s.length > 80 ? ' bad' : ''}`}>{s.length}</span>
                      </div>
                      {(s.note || s.trimmed.length > 0) && (
                        <div className="t-note">
                          {s.note}
                          {s.trimmed.length > 0 &&
                            `${s.note ? ' · ' : ''}dropped to fit: ${s.trimmed.join(', ')}`}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {!out.some((s) => s.changed) &&
                <p className="note" style={{ padding: 14 }}>
                  Nothing to change — those titles are already in your format.
                </p>}
            </div>
          </div>
        </>
      )}

      <p className="note">
        <b>What this will not do.</b> It never invents a parallel the title did not already
        state — a card number is shared across parallels, so matching on it proves nothing about
        which one you hold. It never guesses a team: a wrong team is worse than no team, so a
        missing one is flagged for you instead. And it keeps your spelling of a player's name,
        accents and all, rather than the catalogue's plainer version.
      </p>
    </>
  );
}
