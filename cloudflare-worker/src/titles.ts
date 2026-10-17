/**
 * Titles — Duane's format, applied without inventing anything.
 *
 *   [CAP_NAME] [YEAR] [BRAND] [PRODUCT] [VARIETY] [PARALLEL] [SERIAL]
 *   [GRADE] [ATTRIBUTES] [TEAM_NICK]
 *
 * Example: AIREONTAE ERSERY 2025 Panini Select #134 Purple Prizm Shock /699 PSA 10 Texans
 *
 * Three rules that cost rebuilds before and are enforced here:
 *
 *   1. Never inject a parallel the title does not already state. A card
 *      number is shared across parallels, so matching on it proves
 *      nothing about which one this is.
 *   2. Never guess a team. A wrong team is worse than no team, so a
 *      missing one is reported, not filled in.
 *   3. Player name in CAPS, everything else Title Case. An all-caps
 *      title reads as shouting and is harder to scan.
 *
 * When a title runs past 80 characters the sacrifice order is: filler
 * first, then the city, then the sport word. Never the parallel, the
 * card number, RC or AU.
 */

export const MAX_TITLE = 80;

/**
 * Filler. eBay has its own condition field, so these only eat space.
 *
 * Split in two on purpose: "EX" is a Pokémon card subtype (Empoleon ex)
 * as well as a condition grade, so it is only dropped when it trails the
 * title — which is where a condition sits and where a subtype never
 * does. Stripping it everywhere turned "EMPOLEON EX" into "EMPOLEON".
 */
const FILLER = /\b(EXMT|NRMT|NRMNT\+?|MINT|GEM MINT|VG|GOOD|FAIR|POOR|SHARP|CLEAN|HOT|INVEST|HOF Legend!?|Rookie ROY!?|L@@K|WOW)\b/gi;
const TRAILING_CONDITION = /\s+(EX|NM|NM-MT|VG-EX)\s*$/i;

/** Parallel and attribute shorthand buyers do not search for. */
const EXPAND: [RegExp, string][] = [
  [/\bRef\b/gi, 'Refractor'],
  [/\bIMG VAR\b/gi, 'Image Variation'],
  [/\bSSP\b/g, 'SSP'],
  [/\bAuto\b/gi, 'AU'],
  [/\bAutograph\b/gi, 'AU'],
  [/\bRookie\b/gi, 'RC'],
  [/\bNumbered\b/gi, ''],
];

const GRADERS = /\b(PSA|BGS|SGC|CGC|CSG|HGA)\s*\.?\s*(10|9\.5|9|8\.5|8|7|6|5|4|3|2|1)\b/i;
const SERIAL = /\/\s?(\d{1,5})\b/;
// A Pokémon number is "#070/094" — one identifier, not a number and a
// print run. Matched first so the slash half is not read as a serial.
const CARD_NO_SET = /#\s?(\d{1,3}\/\d{1,3})\b/;
const CARD_NO = /#\s?([A-Za-z0-9][A-Za-z0-9-]*)/;
const YEAR = /\b((?:19|20)\d{2}(?:-\d{2})?)\b/;

const CITIES = [
  'Los Angeles','New York','San Francisco','Kansas City','San Diego','St. Louis','St Louis',
  'Tampa Bay','Green Bay','New England','New Orleans','Las Vegas','Oklahoma City','Golden State',
  'Chicago','Boston','Houston','Dallas','Denver','Detroit','Miami','Atlanta','Seattle','Phoenix',
  'Portland','Toronto','Cleveland','Baltimore','Milwaukee','Minnesota','Philadelphia','Pittsburgh',
  'Cincinnati','Washington','Arizona','Colorado','Texas','Carolina','Indiana','Memphis','Orlando',
  'Sacramento','Charlotte','Brooklyn','Utah','Jacksonville','Tennessee','Buffalo',
];
const SPORT_WORD = /\b(Baseball|Basketball|Football|Hockey|Soccer|WWE|UFC)\s*(Card)?\b/i;

/**
 * Strips accents for comparison only.
 *
 * The catalogue returns "Nikola Vucevic" while the title says
 * "Nikola Vučević", so a literal match removed the first name and left
 * the surname stranded mid-title.
 */
const plain = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');

const titleCase = (s: string) =>
  s.replace(/\S+/g, (w) => {
    // A token starting with # is an identifier a buyer pastes, not a word.
    if (w.startsWith('#') || w.startsWith('/')) return w;
    if (/^(RC|AU|SP|SSP|MEM|GU|TTT|UEFA|FIFA|MLB|NBA|NFL|NHL|WNBA|PSA|BGS|SGC|CGC)$/i.test(w))
      return w.toUpperCase();
    if (/\d/.test(w)) return w;                       // 1st, 2026-27, /699
    // Every part of a hyphenated or slashed word, so "Mini-Diamond" keeps
    // its D and "Red/White/Blue" stays a readable parallel name.
    const cap = (x: string) => x.charAt(0).toUpperCase() + x.slice(1).toLowerCase();
    return w.split('/').map((seg) => seg.split('-').map(cap).join('-')).join('/');
  });

export type TitleParts = {
  name: string; year: string; number: string; serial: string;
  grade: string; attrs: string[]; team: string; rest: string;
};

/**
 * Pulls the fixed slots out of a title.
 *
 * `player` comes from the catalogue when we have a confident match —
 * reading a name out of a title is guesswork, and the catalogue knows.
 */
export function readTitle(title: string, player?: string): TitleParts {
  let t = ` ${title.replace(/\s+/g, ' ').replace(TRAILING_CONDITION, '').trim()} `;

  const grade = (t.match(GRADERS) || [''])[0].trim().replace(/\s*\.?\s*/, ' ');
  if (grade) t = t.replace(GRADERS, ' ');

  // Pokémon-style "#070/094" first, so its slash is not taken as a serial.
  // "#/99" is a print run written with a stray hash, not a card number.
  t = t.replace(/#\s*(?=\/\d)/g, ' ');

  let number = (t.match(CARD_NO_SET) || ['', ''])[1];
  if (number) t = t.replace(CARD_NO_SET, ' ');

  let serial = '';
  if (!number) {
    serial = (t.match(SERIAL) || ['', ''])[1];
    if (serial) t = t.replace(SERIAL, ' ');
    number = (t.match(CARD_NO) || ['', ''])[1];
    if (number) t = t.replace(CARD_NO, ' ');
  }

  const year = (t.match(YEAR) || ['', ''])[1];
  if (year) t = t.replace(YEAR, ' ');

  const attrs: string[] = [];
  for (const a of ['RC', 'AU', 'SP', 'SSP', 'MEM', 'GU']) {
    const rx = new RegExp(`\\b${a}\\b`, 'i');
    if (rx.test(t)) { attrs.push(a); t = t.replace(new RegExp(`\\b${a}\\b`, 'gi'), ' '); }
  }

  t = t.replace(FILLER, ' ');
  for (const [rx, to] of EXPAND) t = t.replace(rx, to);

  // The name: the catalogue's if we have it, else a leading all-caps run.
  let name = (player || '').trim();
  if (!name) {
    // \p{Lu} rather than A-Z: "RONALD ACUÑA JR." and "JESÚS LUZARDO"
    // stop dead at the accent otherwise, and the rest of the surname is
    // left stranded in the middle of the title.
    const caps = title.match(/^(\p{Lu}[\p{Lu}\p{M}.'-]*(?:\s+\p{Lu}[\p{Lu}\p{M}.'-]*){0,3})\s/u);
    if (caps) name = caps[1].trim();
  }
  if (name) {
    // Compare without accents, then cut the same span out of the original.
    const flat = plain(t);
    const needle = plain(name).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
    const hit = flat.match(new RegExp(needle, 'i'));
    if (hit && hit.index !== undefined) {
      // Keep HIS spelling, not the catalogue's. CardHedger returns
      // "Jeremy Pena"; the listing says "JEREMY PEÑA" and that is the
      // one buyers see — replacing it would be a quiet downgrade.
      name = t.slice(hit.index, hit.index + hit[0].length).trim();
      t = t.slice(0, hit.index) + ' ' + t.slice(hit.index + hit[0].length);
    }
  }

  // The team belongs in its own slot at the end. Left in the middle too
  // it comes out twice — "Topps Chrome Refractor Cubs #30 Cubs".
  const team = teamIn(t, NICKNAMES);
  if (team) {
    // Take the city with the nickname. "Chicago Bulls" moving to the end
    // as "Bulls" otherwise leaves "Chicago" stranded mid-title.
    for (const city of CITIES) {
      t = t.replace(new RegExp(`\\b${city}\\s+(?=${team}\\b)`, 'gi'), ' ');
    }
    t = t.replace(new RegExp(`\\b${team}\\b`, 'gi'), ' ');
  }

  // And the catalogue's player name can appear again inside the set
  // description; strip every occurrence, not just the first.
  if (name) {
    for (const word of name.split(/\s+/)) {
      if (word.length <= 2) continue;
      const flat = plain(t);
      const hit = flat.match(new RegExp(`\\b${plain(word)}\\b`, 'i'));
      if (hit && hit.index !== undefined) {
        t = t.slice(0, hit.index) + ' ' + t.slice(hit.index + hit[0].length);
      }
    }
  }

  return {
    name: name.toUpperCase(),
    year, number: number ? `#${number}` : '', serial: serial ? `/${serial}` : '',
    grade: grade.toUpperCase(), attrs,
    team,                                       // only ever read, never guessed
    // A lone '#' or '/' left behind by the slot extraction above is
    // noise in a title and a buyer never types it.
    rest: titleCase(t.replace(/(^|\s)[#/]+(\s|$)/g, ' ').replace(/\s+/g, ' ').trim()),
  };
}

/** Assembles the slots, trimming in the agreed order when over 80. */
export function buildTitle(p: TitleParts, keepTeam: string): { title: string; trimmed: string[] } {
  const trimmed: string[] = [];
  let rest = p.rest;

  const join = (r: string, team: string) => [
    p.name, p.year, r, p.number, p.serial, p.grade, ...p.attrs, team,
  ].filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();

  let out = join(rest, keepTeam);
  if (out.length <= MAX_TITLE) return { title: out, trimmed };

  // 1. the sport word
  if (SPORT_WORD.test(rest)) {
    rest = rest.replace(SPORT_WORD, ' ').replace(/\s+/g, ' ').trim();
    trimmed.push('sport word');
    out = join(rest, keepTeam);
    if (out.length <= MAX_TITLE) return { title: out, trimmed };
  }
  // 2. the city — nobody searches it, the nickname is the search term
  for (const city of CITIES) {
    if (out.includes(city)) {
      rest = rest.replace(city, '').replace(/\s+/g, ' ').trim();
      const team2 = keepTeam.replace(city, '').trim();
      trimmed.push(`city "${city}"`);
      out = join(rest, team2 || keepTeam);
      if (out.length <= MAX_TITLE) return { title: out, trimmed };
    }
  }
  // 3. words off the end of the set description — never the protected slots
  const words = rest.split(' ');
  while (words.length > 1 && join(words.join(' '), keepTeam).length > MAX_TITLE) {
    trimmed.push(`"${words.pop()}"`);
  }
  return { title: join(words.join(' '), keepTeam).slice(0, MAX_TITLE).trim(), trimmed };
}

/** The team already in a title, if it names one. Nickname only. */
export function teamIn(title: string, nicknames: string[]): string {
  for (const n of nicknames) {
    if (new RegExp(`\\b${n}\\b`, 'i').test(title)) return n;
  }
  return '';
}

export const NICKNAMES = [
  'Yankees','Red Sox','Blue Jays','Orioles','Rays','Guardians','Tigers','Twins','White Sox',
  'Royals','Astros','Angels','Athletics','Mariners','Rangers','Braves','Marlins','Mets',
  'Phillies','Nationals','Cubs','Reds','Brewers','Pirates','Cardinals','Diamondbacks','Rockies',
  'Dodgers','Padres','Giants',
  'Celtics','Nets','Knicks','76ers','Raptors','Bulls','Cavaliers','Pistons','Pacers','Bucks',
  'Hawks','Hornets','Heat','Magic','Wizards','Nuggets','Timberwolves','Thunder','Trail Blazers',
  'Jazz','Warriors','Clippers','Lakers','Suns','Kings','Mavericks','Rockets','Grizzlies',
  'Pelicans','Spurs',
  'Bills','Dolphins','Patriots','Jets','Ravens','Bengals','Browns','Steelers','Texans','Jaguars',
  'Titans','Broncos','Chiefs','Raiders','Chargers','Cowboys','Eagles','Commanders','Bears',
  'Lions','Packers','Vikings','Falcons','Panthers','Saints','Buccaneers','Rams','49ers',
  'Seahawks','Colts',
];
