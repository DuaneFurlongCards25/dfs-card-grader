/* ------------------------------------------------------------------ *
 * The pricing rules.
 *
 * Market price in → list price out, in a fixed order, with the safety
 * rails applied last so nothing can push past them. Written as pure
 * functions with no UI in them, because the thing that changes 4,000 live
 * prices should be testable on its own.
 *
 * The market value here is the CardHedger comp, not TCGplayer. For a
 * graded sports card TCGplayer has no number at all, which is exactly
 * the gap this app lives in.
 * ------------------------------------------------------------------ */

export type Band = { min: number; max: number; kind: 'fixed' | 'pct' | 'off'; value: number };

export type Rules = {
  source: 'comp' | 'current';
  bands: Band[];
  floor: number | null;
  multiplier: number | null;
  rounding: 'none' | '99' | '49' | 'quarter' | 'dollar';
  maxMovePct: number | null;
  stickinessPct: number | null;
  markup: number | null;
  neverBelowCost: boolean;
};

export const DEFAULT_RULES: Rules = {
  source: 'comp',
  // Starting bands mirror how he already prices: cheap cards at fixed
  // prices because the fee floor dominates, real cards off the comp.
  bands: [
    { min: 0,     max: 2.99,  kind: 'fixed', value: 2.49 },
    { min: 3,     max: 9.99,  kind: 'pct',   value: -10 },
    { min: 10,    max: 49.99, kind: 'pct',   value: -5 },
    { min: 50,    max: 1e9,   kind: 'pct',   value: 0 },
  ],
  floor: 0.99,
  multiplier: 1.0,
  rounding: '99',
  maxMovePct: 25,
  stickinessPct: 3,
  markup: null,
  neverBelowCost: true,
};

export type PriceInput = {
  current: number | null;
  market: number | null;
  cost: number | null;
};

export type PriceResult = {
  price: number | null;
  /** Plain English, shown next to the card. Never a rule number. */
  why: string;
  moved: boolean;
};

function round(n: number, how: Rules['rounding']): number {
  switch (how) {
    case '99':      return Math.max(0.99, Math.floor(n) + 0.99);
    case '49':      return Math.max(0.49, Math.floor(n) + 0.49);
    case 'quarter': return Math.ceil(n * 4) / 4;
    case 'dollar':  return Math.ceil(n);
    default:        return Math.round(n * 100) / 100;
  }
}

function bandFor(bands: Band[], market: number): Band | null {
  // First range containing the market price wins, top to bottom.
  return bands.find((b) => market >= b.min && market <= b.max) ?? null;
}

export function priceOne(input: PriceInput, r: Rules): PriceResult {
  const market = r.source === 'comp' ? input.market : input.current;
  const current = input.current;

  if (market === null || !Number.isFinite(market) || market <= 0)
    return { price: null, why: 'no comp — left alone', moved: false };

  const band = bandFor(r.bands, market);
  let price: number;
  let why: string;

  if (band) {
    if (band.kind === 'fixed') {
      price = band.value;
      why = `comp ${usd(market)} is in the ${usd(band.min)}–${usd(band.max)} band → ${usd(band.value)}`;

      // Band-edge stickiness. A comp hovering on a boundary would
      // otherwise swing the price every refresh; this makes it move on a
      // trend instead of on noise. Only fixed bands have an edge to fall
      // off — a % band has no step to ping-pong across.
      if (r.stickinessPct && current !== null) {
        const inner = bandFor(r.bands, market);
        const nearLow = Math.abs(market - band.min) / Math.max(band.min, 0.01) * 100;
        const nearHigh = Math.abs(band.max - market) / Math.max(band.max, 0.01) * 100;
        const onEdge = Math.min(nearLow, nearHigh) < r.stickinessPct;
        const currentBand = bandFor(r.bands, current);
        if (onEdge && inner && currentBand && currentBand !== band) {
          return { price: current, why:
            `comp ${usd(market)} is sitting on a band edge — held at ${usd(current)}`, moved: false };
        }
      }
    } else if (band.kind === 'pct') {
      price = market * (1 + band.value / 100);
      why = `${band.value >= 0 ? '+' : ''}${band.value}% of the ${usd(market)} comp`;
    } else {
      price = market + band.value;
      why = `${band.value >= 0 ? '+' : ''}${usd(Math.abs(band.value))} on the ${usd(market)} comp`;
    }
  } else {
    price = Math.max(r.floor ?? 0, market * (r.multiplier ?? 1));
    why = `outside every band → comp × ${r.multiplier ?? 1}`;
  }

  // --- safety rails, in order ---

  // A fixed-price band is a deliberate number; the floor does not raise it.
  if (r.floor !== null && band?.kind !== 'fixed' && price < r.floor) {
    price = r.floor;
    why += `, lifted to your ${usd(r.floor)} floor`;
  }

  if (r.markup) { price += r.markup; why += `, plus your ${usd(r.markup)} markup`; }

  price = round(price, r.rounding);

  if (r.neverBelowCost && input.cost !== null && price < input.cost) {
    price = round(input.cost, r.rounding);
    why = `would have gone under what you paid (${usd(input.cost)}) — held at cost`;
  }

  // Checked last so nothing above can push past it.
  if (r.maxMovePct !== null && current !== null && current > 0) {
    const cap = current * (r.maxMovePct / 100);
    if (Math.abs(price - current) > cap) {
      const capped = round(price > current ? current + cap : current - cap, r.rounding);
      why += `, capped at ${r.maxMovePct}% movement`;
      price = capped;
    }
  }

  const moved = current === null || Math.abs(price - current) > 0.004;
  return { price, why, moved };
}

export const usd = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });

/** A flat percentage change, for the −5 / −10 / −20 buttons. */
export function nudge(current: number | null, pct: number, r: Rules): number | null {
  if (current === null) return null;
  let p = current * (1 + pct / 100);
  if (r.floor !== null && p < r.floor) p = r.floor;
  return round(p, r.rounding);
}
