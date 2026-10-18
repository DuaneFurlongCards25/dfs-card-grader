import { useEffect, useMemo, useState } from 'react';
import { API, getToken, post } from './api';

/* ------------------------------------------------------------------ *
 * Listing templates — the title and the description, set once.
 *
 * The title generator is slot-based because that is how he specified it
 * in September: name in caps first, then year, set, card number,
 * parallel, serial, grade, RC/AU, team. Dragging the slots changes the
 * order for every card at once, with a real card previewing underneath
 * so the effect is visible rather than imagined.
 *
 * The description is his own, built in Haystack: card image on the left,
 * title and policy bullets on the right.
 * ------------------------------------------------------------------ */

type Slot = { key: string; label: string; caps?: boolean };

export const SLOTS: Slot[] = [
  { key: 'player',   label: 'Player',      caps: true },
  { key: 'year',     label: 'Year' },
  { key: 'set',      label: 'Set' },
  { key: 'number',   label: 'Card #' },
  { key: 'parallel', label: 'Parallel' },
  { key: 'serial',   label: 'Serial' },
  { key: 'grade',    label: 'Grade' },
  { key: 'rc',       label: 'RC' },
  { key: 'au',       label: 'AU' },
  { key: 'team',     label: 'Team' },
];

const DEFAULT_ORDER = SLOTS.map((s) => s.key);

/** His own template, as built in Haystack. */
const DEFAULT_DESC = `<div style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.6;">
  <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
    <tr>
      <td valign="top" style="width:180px;padding-right:20px;">
        <img src="{front_image}" alt="{title}" style="width:100%;max-width:180px;border-radius:12px;border:1px solid #e5e7eb;" />
      </td>
      <td valign="top">
        <h2 style="margin:0 0 12px;font-size:24px;text-transform:uppercase;">{title}</h2>
        <ol style="margin:0 0 20px;padding-left:20px;">
          <li style="margin-bottom:10px;">All cards are scanned. If you see any lines, if you want more pictures, just ask!</li>
          <li style="margin-bottom:10px;">I send all cards over $20 with tracking, and all mem patches are sent ground advantage to prevent damage.</li>
          <li style="margin-bottom:10px;">All cards valued over $100 will have insurance added, which protects you as the buyer.</li>
        </ol>
        <p style="margin:0;">
          My goal is to have you receive the card in tip-top shape. No Returns Accepted. Questions, please ask!!!
        </p>
      </td>
    </tr>
  </table>
</div>`;

/** A real card, so the preview shows what will actually happen. */
const SAMPLE: Record<string, string> = {
  player: 'Miguel Sime Jr.', year: '2025', set: 'Bowman Chrome Prospect Autographs',
  number: '#CPA-MS', parallel: '', serial: '', grade: '', rc: 'RC', au: 'AU',
  team: 'Nationals',
};

export function titleFromOrder(order: string[], v: Record<string, string>, maxLen = 80) {
  const bits = order.map((k) => {
    const slot = SLOTS.find((s) => s.key === k);
    const val = (v[k] ?? '').trim();
    if (!val) return '';
    return slot?.caps ? val.toUpperCase() : val;
  }).filter(Boolean);

  let t = bits.join(' ').replace(/\s+/g, ' ').trim();
  if (t.length <= maxLen) return t;
  // Shorten the set, never the parallel or the number — those are searched.
  const i = order.indexOf('set');
  if (i >= 0 && bits[i]) {
    const words = bits[i].split(' ');
    while (words.length > 1 && t.length > maxLen) {
      words.pop(); bits[i] = words.join(' ');
      t = bits.join(' ').replace(/\s+/g, ' ').trim();
    }
  }
  return t.slice(0, maxLen).trim();
}

export default function Templates() {
  const [order, setOrder] = useState<string[]>(DEFAULT_ORDER);
  const [desc, setDesc] = useState(DEFAULT_DESC);
  const [msg, setMsg] = useState('');
  const [drag, setDrag] = useState<number | null>(null);

  useEffect(() => {
    fetch(`${API}/api/listing-settings`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.json())
      .then((d) => {
        if (d?.settings?.titleOrder?.length) setOrder(d.settings.titleOrder);
        if (d?.settings?.description) setDesc(d.settings.description);
      }).catch(() => {});
  }, []);

  const save = async () => {
    setMsg('');
    try {
      const cur = await fetch(`${API}/api/listing-settings`,
        { headers: { Authorization: `Bearer ${getToken()}` } }).then((r) => r.json());
      await post('/api/listing-settings',
        { ...(cur.settings ?? {}), titleOrder: order, description: desc });
      setMsg('Saved. New listings use this.');
    } catch (e: any) { setMsg(e.message || String(e)); }
  };

  const preview = useMemo(() => titleFromOrder(order, SAMPLE), [order]);

  const move = (from: number, to: number) => {
    if (to < 0 || to >= order.length) return;
    const n = [...order];
    n.splice(to, 0, n.splice(from, 1)[0]);
    setOrder(n);
  };

  const descPreview = desc
    .replace(/\{title\}/g, preview)
    .replace(/\{front_image\}/g,
      'https://dfs-cards-api.duane-588.workers.dev/api/inventory/img/placeholder');

  return (
    <>
      <div className="eyebrow">Tools</div>
      <h1 className="title">Listing templates</h1>
      <p className="sub">How every title and description is built</p>

      <div className="card2">
        <div className="lab">Title order</div>
        <div className="sub2">
          Drag to reorder, or use the arrows. The player is always capitalised; everything else
          keeps its own case. Over 80 characters the <b>set name</b> is shortened a word at a
          time — never the parallel, the card number, RC or AU, because those are what buyers
          type.
        </div>

        <div className="slots">
          {order.map((k, i) => {
            const slot = SLOTS.find((s) => s.key === k)!;
            const empty = !SAMPLE[k];
            return (
              <div key={k}
                   className={`slot${drag === i ? ' dragging' : ''}${empty ? ' empty' : ''}`}
                   draggable
                   onDragStart={() => setDrag(i)}
                   onDragEnd={() => setDrag(null)}
                   onDragOver={(e) => { e.preventDefault(); if (drag !== null && drag !== i) { move(drag, i); setDrag(i); } }}
                   title={empty ? 'This card has nothing for that slot' : ''}>
                <button className="sl-arrow" onClick={() => move(i, i - 1)} aria-label="Earlier">‹</button>
                <span>{slot.label}{slot.caps ? ' (CAPS)' : ''}</span>
                <button className="sl-arrow" onClick={() => move(i, i + 1)} aria-label="Later">›</button>
              </div>
            );
          })}
        </div>

        <div className="tpreview">
          <div className="k">Preview, on a real card</div>
          <div className="tp-title">{preview}</div>
          <div className={`len${preview.length > 80 ? ' bad' : ''}`}>{preview.length} / 80</div>
        </div>

        <button className="btn sm" onClick={() => setOrder(DEFAULT_ORDER)}>
          Back to your September order
        </button>
      </div>

      <div className="card2">
        <div className="lab">Description</div>
        <div className="sub2">
          Your own layout from Haystack — card image left, title and policy bullets right.
          <code>{'{title}'}</code> and <code>{'{front_image}'}</code> are filled per card.
        </div>
        <textarea className="descbox" rows={14} value={desc}
                  onChange={(e) => setDesc(e.target.value)} />
        <div className="lab" style={{ marginTop: 14 }}>How it looks</div>
        <div className="descpreview"
             dangerouslySetInnerHTML={{ __html: descPreview }} />
      </div>

      <div className="selbar">
        <span className="muted">{msg || 'Not saved yet.'}</span>
        <span className="spacer" />
        <button className="btn read" onClick={save}>Save templates</button>
      </div>
    </>
  );
}
