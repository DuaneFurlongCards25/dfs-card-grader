/**
 * The Hopper — a photographed card becomes a listable one.
 *
 * Scan a stack on the phone, and this reads each card, works out what it
 * is, prices it, and hands back a draft for review. It is the step that
 * sits between "I have photos" and "I have inventory", and the only
 * reason a third-party scanner is still needed today.
 *
 * ## Why a vision model and not OCR
 *
 * OCR returns the words on a card. What is needed is the card's identity
 * — which of the forty parallels in a set this is, whether /25 is a
 * print run or part of the design, whether the big name is the player or
 * the set. That is reading, not transcription.
 *
 * ## The rule everything here obeys
 *
 * A field it cannot read is left empty and named in `unsure`. Never
 * guessed. A wrong year or parallel produces a listing that looks right,
 * sells at the wrong price, and gets found weeks later — which is far
 * more expensive than an empty box someone fills in during review.
 */

/**
 * Meta's model needs its community licence accepted once per Cloudflare
 * account. That is the account owner's agreement to give, not this
 * software's, so it is behind a button in Settings rather than done here.
 */
export const VISION_MODEL = '@cf/meta/llama-3.2-11b-vision-instruct';

export type Env2 = {
  ANTHROPIC_API_KEY?: string;
  AI?: { run: (model: string, input: any) => Promise<any> };
};

/** Which reader answered, so the screen can say so rather than imply. */
export type ReadBy = 'claude' | 'basic';

export type Identified = {
  player: string; year: string; set_name: string; card_number: string;
  parallel: string; serial: string; grader: string; grade: string;
  team: string; sport: string; is_rookie: boolean; is_auto: boolean;
  confidence: number; unsure: string[];
  read_by: ReadBy;
  /** Set when the good reader was meant to run and could not. */
  degraded?: string;
};

const SYSTEM = `You identify trading cards from photographs for a card seller's inventory system.

You are given the front, and usually the back, of ONE card. Return what the card
actually shows. This feeds eBay listings, so a wrong field is worse than an empty one.

Rules:
- Read only what is printed. Never infer a parallel, a print run or a rookie flag
  that is not visible. A card number is shared across parallels, so the number
  alone never tells you which parallel this is.
- parallel: the colour or finish name as printed ("Purple Refractor", "Gold Mini-Diamond",
  "Image Variation"). Empty if the card shows no parallel name and looks like a base card.
- serial: the hand- or machine-numbered print run, as "/99". Empty if not numbered.
  Do not confuse a card number with a print run.
- grader/grade: only if the card is in a graded slab with a visible label
  (PSA, BGS, SGC, CGC). Empty for a raw card.
- team: the team NICKNAME only ("Padres", never "San Diego Padres"). For international
  soccer, the country. Empty if the card shows no team.
- is_rookie: only if the card itself carries an RC badge or the word Rookie.
- sport: Baseball, Basketball, Football, Hockey, Soccer, Pokemon, or Other.
- confidence: 0 to 1, your honest confidence in player + year + set together.
- unsure: name every field you could not read with certainty. Be generous here —
  a flagged field gets checked by a person, an unflagged wrong one does not.

Return ONLY a JSON object, no prose, with exactly these keys:
player, year, set_name, card_number, parallel, serial, grader, grade, team,
sport, is_rookie, is_auto, confidence, unsure`;

const bytesToB64 = (buf: ArrayBuffer) => {
  const b = new Uint8Array(buf);
  let s = '';
  // Chunked: a 700KB photo blows the argument limit in one spread call.
  for (let i = 0; i < b.length; i += 8192) {
    s += String.fromCharCode(...b.subarray(i, i + 8192));
  }
  return btoa(s);
};

/** Pulls the JSON object out of whatever prose a model wraps it in. */
function readJson(text: string): any {
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error('the model did not return a card');
  return JSON.parse(m[0]);
}

function shape(d: any): Identified {
  // Models write "none", "N/A" and "null" as strings when a field is
  // absent. Left alone they end up printed in the title — one came back
  // as "... /99 NONE None RC AU Royals".
  // "base" means no parallel, not a parallel called Base — it was being
  // printed into titles as "#CPA-MS base AU Nationals".
  const EMPTY = /^(none|n\/a|na|null|unknown|not visible|not specified|base|base card|standard|regular|-{1,2}|)$/i;
  const str = (v: unknown) => {
    const x = (v === null || v === undefined ? '' : String(v)).trim();
    return EMPTY.test(x) ? '' : x.slice(0, 120);
  };
  return {
    player: str(d.player), year: str(d.year), set_name: str(d.set_name),
    card_number: str(d.card_number), parallel: str(d.parallel), serial: str(d.serial),
    grader: str(d.grader), grade: str(d.grade), team: str(d.team), sport: str(d.sport),
    is_rookie: !!d.is_rookie, is_auto: !!d.is_auto,
    confidence: Number.isFinite(+d.confidence) ? Math.max(0, Math.min(1, +d.confidence)) : 0,
    unsure: Array.isArray(d.unsure) ? d.unsure.map(str).filter(Boolean).slice(0, 12) : [],
    read_by: 'claude',
  };
}

/**
 * Cloudflare's vision model, used when no Anthropic key is configured.
 *
 * Weaker at reading a card than Claude is, so what comes back is marked
 * down: confidence is capped and the source is recorded, which keeps a
 * cheap read from being trusted like an expensive one.
 */
async function identifyWithWorkersAI(
  env: Env2, front: ArrayBuffer,
): Promise<Identified> {
  if (!env.AI) throw new Error('no vision model is available on this Worker');
  const r = await env.AI.run(VISION_MODEL, {
    messages: [
      { role: 'system', content: SYSTEM },
      { role: 'user', content: 'Identify this trading card. Reply with JSON only.' },
    ],
    image: [...new Uint8Array(front)],
    max_tokens: 900,
  });
  // Workers AI hands back either a string of text or an already-parsed
  // object, depending on the model. Stringifying an object gave
  // "[object Object]", which then failed to parse as a card.
  const payload = (r as any)?.response ?? (r as any)?.result?.response ??
                  (r as any)?.description ?? (r as any)?.text ?? r;

  let out: Identified;
  if (payload && typeof payload === 'object') {
    out = shape(payload);
    out.read_by = 'basic';
  } else {
    const raw = String(payload ?? '');
    if (/must submit the prompt 'agree'/i.test(raw))
      throw new Error("Meta's licence has not been accepted — press Accept on the Hopper");
    if (!raw.trim())
      throw new Error(`the reader returned nothing: ${JSON.stringify(r).slice(0, 200)}`);
    try { out = shape(readJson(raw)); out.read_by = 'basic'; }
    catch { throw new Error(`the reader did not answer with a card: ${raw.slice(0, 220)}`); }
  }
  out.confidence = Math.min(out.confidence, 0.6);
  out.unsure = [...new Set([...out.unsure, 'read by the basic model — check it'])];
  return out;
}

/**
 * Reading a card is transcription, not reasoning, so the cheap model goes
 * first and the expensive one only sees the cards it struggled with.
 *
 * Measured on his own 2974x3960 scans, front and back: Haiku $0.0066 a
 * card against Opus at $0.0332. At one in five escalating that is about
 * $0.013 a card — 500 cards for roughly six dollars rather than sixteen.
 *
 * Anthropic scales anything over 1568px down before billing, so sending
 * the full-size photo costs the same as sending a resized one. Nothing
 * is resized here; it would only lose detail for no saving.
 */
const FIRST_MODEL  = 'claude-haiku-4-5';
const SECOND_MODEL = 'claude-opus-5';
/** Below this, the cheap read is not trusted and the good model re-reads. */
const ESCALATE_UNDER = 0.85;

export async function identifyCard(
  env: Env2, front: ArrayBuffer, back: ArrayBuffer | null, frontType = 'image/jpeg',
): Promise<Identified> {
  // A dead key must be loud. Falling back silently means cards keep
  // being read — worse — and nobody finds out until the listings are
  // wrong, which is the exact failure this whole screen exists to stop.
  if (!env.ANTHROPIC_API_KEY) {
    const out = await identifyWithWorkersAI(env, front);
    out.degraded = 'No Anthropic key is set, so the basic reader was used.';
    return out;
  }

  let first: Identified;
  try {
    first = await askClaude(env, FIRST_MODEL, front, back, frontType);
  } catch (e: any) {
    const why = String(e?.message || e);
    const out = await identifyWithWorkersAI(env, front);
    out.degraded = /api-key|authentication|credit|balance/i.test(why)
      ? `Claude refused the key — ${why.slice(0, 120)}. The basic reader was used instead.`
      : `Claude could not be reached — ${why.slice(0, 120)}. The basic reader was used instead.`;
    return out;
  }

  if (first.confidence >= ESCALATE_UNDER && first.unsure.length === 0) return first;

  // Worth the extra two and a half cents: a wrong parallel costs more.
  try {
    const second = await askClaude(env, SECOND_MODEL, front, back, frontType);
    return second.confidence >= first.confidence ? second : first;
  } catch {
    return first;                       // the cheap read is better than none
  }
}

async function askClaude(
  env: Env2, model: string, front: ArrayBuffer, back: ArrayBuffer | null, frontType: string,
): Promise<Identified> {
  const key = env.ANTHROPIC_API_KEY;
  if (!key) throw new Error('no Anthropic key');

  const content: any[] = [
    { type: 'text', text: 'Front of the card:' },
    { type: 'image', source: { type: 'base64', media_type: frontType, data: bytesToB64(front) } },
  ];
  if (back) {
    content.push({ type: 'text', text: 'Back of the same card:' });
    content.push({ type: 'image', source: { type: 'base64', media_type: frontType, data: bytesToB64(back) } });
  }
  content.push({ type: 'text', text: 'Identify this card. JSON only.' });

  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model,
      max_tokens: 1200,
      // No extended thinking: this is reading printed text off a card,
      // and thinking tokens bill at the output rate for no gain here.
      system: SYSTEM,
      messages: [{ role: 'user', content }],
    }),
  });

  const body = await r.json() as any;
  if (!r.ok) {
    // A dead or rejected key should not stop the Hopper — fall through
    // to the weaker model and say so, rather than failing the card.
    if (r.status === 401 || r.status === 403) return identifyWithWorkersAI(env, front);
    throw new Error(body?.error?.message || `Anthropic HTTP ${r.status}`);
  }

  const text = (body?.content ?? [])
    .filter((c: any) => c.type === 'text').map((c: any) => c.text).join('\n');
  return shape(readJson(text));
}

/** Builds a title in Duane's slot order from identified fields. */
export function titleFrom(c: Identified): string {
  const bits = [
    c.player.toUpperCase(),
    c.year,
    c.set_name,
    c.card_number ? (c.card_number.startsWith('#') ? c.card_number : `#${c.card_number}`) : '',
    c.parallel,
    c.serial ? (c.serial.startsWith('/') ? c.serial : `/${c.serial}`) : '',
    c.grader && c.grade ? `${c.grader.toUpperCase()} ${c.grade}` : '',
    c.is_rookie ? 'RC' : '',
    c.is_auto ? 'AU' : '',
    c.team,
  ].filter(Boolean);

  let title = bits.join(' ').replace(/\s+/g, ' ').trim();
  // Trim from the set description end, never the protected slots.
  while (title.length > 80 && bits.length > 2) {
    const i = bits.findIndex((b) => b === c.set_name);
    if (i < 0) break;
    const words = bits[i].split(' ');
    if (words.length <= 1) break;
    words.pop();
    bits[i] = words.join(' ');
    title = bits.join(' ').replace(/\s+/g, ' ').trim();
  }
  return title.slice(0, 80).trim();
}
