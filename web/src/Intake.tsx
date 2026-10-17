import { useEffect, useState } from 'react';
import { API, getToken } from './api';
import { download, stamp, toCsv } from './exports';

/* ------------------------------------------------------------------ *
 * Intake — what the phone has shot, waiting to become inventory.
 *
 * Leumas's Hopper takes images, matches them, and you review before
 * anything lists. Same three steps here, with one difference that is
 * ours and not his: the photos come from a scanner we built, so there is
 * no bridge app, no paired PC and no export step — the phone writes
 * straight into the same bucket this page reads.
 *
 * What it will not do is guess. A card is identified from its photo by a
 * person or by a catalogue lookup, never by filename alone.
 * ------------------------------------------------------------------ */

type Shot = { key: string; stack: string; name: string; bytes: number; uploaded: string };
type StackRow = { name: string; photos: number; bytes: number; newest: string };

const kb = (n: number) => `${Math.round(n / 1024)} KB`;

/** STACK-001-front.jpg → { card: 1, side: 'front' } */
function readName(name: string) {
  const m = name.match(/-(\d{3})-(front|back)\.jpe?g$/i);
  return m ? { card: +m[1], side: m[2].toLowerCase() } : { card: 0, side: '' };
}

export default function Intake() {
  const [stacks, setStacks] = useState<StackRow[] | null>(null);
  const [photos, setPhotos] = useState<Shot[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const r = await fetch(`${API}/api/scan/list`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) throw new Error((await r.json())?.error || `HTTP ${r.status}`);
      const d = await r.json();
      setStacks(d.stacks ?? []);
      setPhotos(d.photos ?? []);
    } catch (e: any) { setError(e.message || String(e)); setStacks([]); }
  };
  useEffect(() => { load(); }, []);

  const inStack = photos.filter((p) => p.stack === open);
  const cards = new Map<number, { front?: Shot; back?: Shot }>();
  for (const p of inStack) {
    const { card, side } = readName(p.name);
    const v = cards.get(card) ?? {};
    if (side === 'front') v.front = p; else if (side === 'back') v.back = p;
    cards.set(card, v);
  }
  const pairs = [...cards.entries()].sort((a, z) => a[0] - z[0]);
  const incomplete = pairs.filter(([, v]) => !v.front || !v.back).length;

  return (
    <>
      <div className="eyebrow">Inventory</div>
      <h1 className="title">Intake</h1>
      <p className="sub">Cards the phone has shot, not yet listed</p>

      {error && (
        <div className="legend" style={{ borderColor: 'var(--danger)' }}>
          <span style={{ color: 'var(--danger)' }}>{error}</span>
          <span className="spacer" />
          <button className="btn sm" onClick={load}>Try again</button>
        </div>
      )}

      {stacks === null && <p className="note">Looking for scanned stacks…</p>}

      {stacks !== null && !stacks.length && !error && (
        <>
          <div className="drop" style={{ cursor: 'default' }}>
            <b>Nothing scanned yet</b>
            <span className="muted">
              Open <code>dfs-cards-api.duane-588.workers.dev/scan</code> on your phone,
              name a stack and start shooting. Photos appear here as they upload.
            </span>
          </div>
          <p className="note">
            Front and back are paired automatically from the file name, so a card missing
            one side is flagged here rather than discovered halfway through listing.
          </p>
        </>
      )}

      {!!stacks?.length && (
        <>
          <div className="stats">
            <div className="stat"><div className="k">Stacks waiting</div>
              <div className="v">{stacks.length}</div>
              <div className="n">shot on the phone, not yet listed</div></div>
            <div className="stat cool"><div className="k">Photos</div>
              <div className="v">{photos.length.toLocaleString()}</div>
              <div className="n">{kb(photos.reduce((a, p) => a + p.bytes, 0))} in all</div></div>
            <div className="stat fresh"><div className="k">Newest</div>
              <div className="v" style={{ fontSize: 19 }}>
                {new Date(stacks[0].newest).toLocaleDateString()}
              </div>
              <div className="n">{stacks[0].name}</div></div>
            <div className="stat watch"><div className="k">Missing a side</div>
              <div className="v">{open ? incomplete : '—'}</div>
              <div className="n">{open ? `in ${open}` : 'open a stack to check'}</div></div>
          </div>

          <div className="boxgrid">
            {stacks.map((s) => (
              <button key={s.name}
                      className={`boxcard${open === s.name ? ' on' : ''}`}
                      onClick={() => setOpen(open === s.name ? null : s.name)}>
                <div className="bn">{s.name}</div>
                <div className="bc">{Math.ceil(s.photos / 2)}<span> cards</span></div>
                <div className="bv">{s.photos} photos</div>
              </button>
            ))}
          </div>

          <div className="toolbar">
            <button className="btn sm" onClick={load}>⟳ Check for new scans</button>
            {open && (
              <button className="btn sm" onClick={() => download(
                `intake-${open}-${stamp()}.csv`,
                toCsv(['Card', 'Front', 'Back', 'Front URL', 'Back URL'],
                  pairs.map(([n, v]) => [n, v.front?.name ?? '', v.back?.name ?? '',
                    v.front ? `${API}/api/scan/img/${encodeURIComponent(v.front.key)}` : '',
                    v.back ? `${API}/api/scan/img/${encodeURIComponent(v.back.key)}` : ''])))}>
                ⬇ {open} photo list
              </button>
            )}
            <span className="spacer" />
            <span className="muted">
              Photos stay on the phone and here until you clear them — nothing is deleted on upload.
            </span>
          </div>
        </>
      )}

      {open && !!pairs.length && (
        <>
          <h2 className="h2">{open} — {pairs.length} cards</h2>
          {incomplete > 0 && (
            <div className="legend" style={{ borderColor: 'var(--watch)' }}>
              <span style={{ color: 'var(--watch)' }}>
                {incomplete} {incomplete === 1 ? 'card is' : 'cards are'} missing a side.
              </span>
              <span className="spacer" />
              <span className="muted">Re-shoot those before listing — the website needs both.</span>
            </div>
          )}
          <div className="shotgrid">
            {pairs.map(([n, v]) => (
              <div key={n} className={`shotpair${!v.front || !v.back ? ' bad' : ''}`}>
                <div className="sp-n">#{n}</div>
                {(['front', 'back'] as const).map((side) => {
                  const p = side === 'front' ? v.front : v.back;
                  return p ? (
                    <img key={side} loading="lazy" alt={`${n} ${side}`}
                         src={`${API}/api/scan/img/${encodeURIComponent(p.key)}`} />
                  ) : <div key={side} className="sp-missing">no {side}</div>;
                })}
              </div>
            ))}
          </div>
        </>
      )}

      <p className="note">
        <b>How this is meant to run.</b> Shoot a stack on the phone; it uploads as you go.
        Front and back pair themselves from the file name. What is still manual is naming each
        card — that is the next piece, and it is the one worth doing properly rather than
        guessing a player from a photo.
      </p>
    </>
  );
}
