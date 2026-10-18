/**
 * Builds a title out of card attributes, in Duane's slot order:
 *
 *   [CAP_NAME] [YEAR] [BRAND/SET] [#NUMBER] [PARALLEL] [/SERIAL]
 *   [GRADE] [RC] [AU] [TEAM]
 *
 * Lives in the browser so changing a parallel rewrites the title as you
 * type, with no round trip. The same order the Worker uses — one shape
 * in two places is a risk, so if one changes the other must.
 */

export type Attrs = {
  player?: string | null; year?: string | null; set_name?: string | null;
  card_number?: string | null; parallel?: string | null; serial?: string | null;
  grader?: string | null; grade?: string | null; team?: string | null;
  is_rookie?: boolean | null; is_auto?: boolean | null;
  is_memorabilia?: boolean | null; is_sp?: boolean | null;
};

/**
 * "Base" means a card with no parallel, not a parallel called Base.
 * It was ending up in titles: "#BCP-MS Base RC AU Nationals".
 */
const NOT_A_VALUE = /^(base|base card|none|n\/a|na|null|standard|regular|raw|not numbered)$/i;
const clean = (v: unknown) => {
  const x = (v ?? '').toString().trim();
  return NOT_A_VALUE.test(x) ? '' : x;
};

export function buildCardTitle(a: Attrs): string {
  const num = clean(a.card_number);
  const ser = clean(a.serial);
  const grader = clean(a.grader);
  const grade = clean(a.grade);

  const bits = [
    clean(a.player).toUpperCase(),
    clean(a.year),
    clean(a.set_name),
    num ? (num.startsWith('#') ? num : `#${num}`) : '',
    clean(a.parallel),
    ser ? (ser.startsWith('/') ? ser : `/${ser.replace(/^\/+/, '')}`) : '',
    grader && grade ? `${grader.toUpperCase()} ${grade}` : '',
    a.is_rookie ? 'RC' : '',
    a.is_auto ? 'AU' : '',
    a.is_memorabilia ? 'MEM' : '',
    a.is_sp ? 'SP' : '',
    clean(a.team),
  ].filter(Boolean);

  let title = bits.join(' ').replace(/\s+/g, ' ').trim();
  if (title.length <= 80) return title;

  // Over 80: shorten the set name a word at a time. Never the parallel,
  // the card number, the serial, RC or AU — those are what buyers search.
  const setIdx = bits.findIndex((b) => b === clean(a.set_name));
  if (setIdx >= 0) {
    const words = bits[setIdx].split(' ');
    while (words.length > 1 && title.length > 80) {
      words.pop();
      bits[setIdx] = words.join(' ');
      title = bits.join(' ').replace(/\s+/g, ' ').trim();
    }
  }
  return title.slice(0, 80).trim();
}

/** Common parallels, offered as suggestions — never forced. */
export const PARALLELS = [
  'Refractor', 'X-Fractor', 'Atomic Refractor', 'Mojo Refractor',
  'Purple Refractor', 'Orange Refractor', 'Green Refractor', 'Blue Refractor',
  'Red Refractor', 'Gold Refractor', 'Black Refractor', 'Aqua Refractor',
  'Orange Wave Refractor', 'Blue Wave Refractor', 'Green Wave Refractor',
  'Purple Pulsar Refractor', 'Purple Geometric Refractor', 'Speckle Refractor',
  'Mini-Diamond Refractor', 'Sapphire', 'Shimmer', 'Image Variation',
  'Silver Prizm', 'Green Prizm', 'Purple Prizm', 'Orange Prizm', 'Red Prizm',
  'Mojo Prizm', 'Hyper Prizm', 'Disco Prizm', 'Pink Prizm',
  'Holo', 'Reverse Holo', 'Negative', 'Gold Vinyl', 'SSP', 'Short Print',
];

/** The feature chips, mapped to the fields they set. */
export const FEATURES: { key: keyof Attrs; label: string }[] = [
  { key: 'is_rookie', label: 'Rookie (RC)' },
  { key: 'is_auto', label: 'Autograph (AU)' },
  { key: 'is_memorabilia', label: 'Memorabilia' },
  { key: 'is_sp', label: 'Short Print' },
];
