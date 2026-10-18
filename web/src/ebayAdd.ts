/* ------------------------------------------------------------------ *
 * The eBay listing file.
 *
 * This is the "list it" button, in the only shape eBay offers an account
 * without API access: File Exchange. One upload lists several hundred
 * cards at once, which is the same end result Heystack's button gives —
 * it just has an upload step in the middle.
 *
 * The 82-column shape and the defaults below are lifted from the
 * builder already proven in app.py (_AB_TCP_HEADER), because that one
 * has survived real uploads and a header eBay does not like is rejected
 * silently at row one.
 * ------------------------------------------------------------------ */

import { toCsv } from './exports';

export const ADD_HEADER = [
  '*Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)',
  'CustomLabel', '*Category', 'StoreCategory', '*Title', 'Subtitle', 'Relationship',
  '*ConditionID', '*C:Graded', '*C:Sport', '*C:Player/Athlete', '*C:Parallel/Variety',
  '*C:Manufacturer', 'C:Season', '*C:Features', '*C:Set', 'CD:Grade - (ID: 27502)',
  '*C:League', 'CD:Professional Grader - (ID: 27501)', '*C:Team', '*C:Autographed',
  'CD:Card Condition - (ID: 40001)', '*C:Card Name', '*C:Card Number',
  'CDA:Certification Number - (ID: 27503)', '*C:Type', 'C:Signed By',
  'C:Autograph Authentication', 'C:Year Manufactured', 'C:Card Size',
  'C:Country/Region of Manufacturer', 'C:Material', 'C:Autograph Format', 'C:Vintage',
  'C:Original/Licensed Reprint', 'C:Event/Tournament', 'C:Language',
  'C:Autograph Authentication Number', 'C:Bundle Description',
  'C:California Prop 65 Warning', 'C:Card Thickness', 'C:Custom Bundle',
  'C:Insert Set', 'C:Print Run', 'PicURL', 'GalleryType', '*Description', '*Format',
  '*Duration', '*StartPrice', 'BuyItNowPrice', '*Quantity', 'PayPalAccepted',
  'PayPalEmailAddress', 'ImmediatePayRequired', 'PaymentInstructions', '*Location',
  'PostalCode', 'WeightMajor', 'WeightMinor', 'ShippingType',
  'ShippingService-1:Option', 'ShippingService-1:FreeShipping',
  'ShippingService-1:Cost', 'ShippingService-1:AdditionalCost',
  'ShippingService-2:Option', 'ShippingService-2:Cost', '*DispatchTimeMax',
  'PromotionalShippingDiscount', 'ShippingDiscountProfileID',
  '*ReturnsAcceptedOption', 'ReturnsWithinOption', 'RefundOption',
  'ShippingCostPaidByOption', 'AdditionalDetails', 'ShippingProfileName',
  'ReturnProfileName', 'PaymentProfileName', 'TakeBackPolicyID',
  'ShippingProfileID', 'ReturnProfileID', 'PaymentProfileID',
  'ProductCompliancePolicyID', 'ScheduleTime', 'BestOfferEnabled',
  'MinimumBestOfferPrice', 'BestOfferAutoAcceptPrice', '*C:Rookie', '*C:Memorabilia',
];

export type AddDefaults = {
  category: string;
  location: string;
  postalCode: string;
  dispatchDays: string;
  shippingProfile: string;
  returnProfile: string;
  paymentProfile: string;
  /*
   * The numeric ids, preferred over the names.
   *
   * His account has TWO policies both called "Flat:
   * US_eBayStandardEnvelope $0.99, 2 busines" — 332312490021 and
   * 332312496021. A name that is not unique either rejects the upload or
   * quietly picks the wrong policy, so where an id is known it wins and
   * the name is left out entirely.
   */
  shippingProfileId?: string;
  returnProfileId?: string;
  paymentProfileId?: string;
  /** Lowest band first; a card above every band uses the policy above. */
  shippingBands?: { upTo: number; profile: string; profileId?: string }[];
  bestOffer: boolean;
  immediatePay?: boolean;
  duration: string;
  quantity?: string;
  weightMajor?: string;
  weightMinor?: string;
  returnsAccepted?: string;
  conditionDefault?: string;
  description?: string;
  storeCategories?: Record<string, string>;
};

export const ADD_DEFAULTS: AddDefaults = {
  category: '261328',              // Sports Trading Card Singles
  location: 'Scottsdale, AZ',
  postalCode: '85255',
  dispatchDays: '1',
  shippingProfile: 'Flat: US_eBayStandardEnvelope $0.99',
  returnProfile: 'Returns',
  paymentProfile: 'BIN',
  bestOffer: true,
  duration: 'GTC',
};

/**
 * eBay condition descriptor 40001 for category 261328 — the ungraded
 * card condition. eBay REJECTS an ungraded listing without it, which is
 * why it has to be a real field and not a default nobody sees.
 * Ids confirmed from the eBay template, Aug 2026.
 */
export const CARD_CONDITIONS: { id: string; label: string }[] = [
  { id: '400010', label: 'Near mint or better' },
  { id: '400011', label: 'Excellent' },
  { id: '400012', label: 'Very good' },
  { id: '400013', label: 'Poor' },
];
export const CONDITION_DEFAULT = '400011';

export type AddCard = {
  sku: string;
  title: string;
  price: number | null;
  sport: string;
  grader: string;
  grade: string;
  cert: string;
  /** Front first — eBay makes the first photo the gallery image. */
  picUrls?: string[];
  condition?: string;      // one of CARD_CONDITIONS ids, ungraded only
  manufacturer?: string;
  league?: string;
  parallel?: string;
  year?: string;
  cardNumber?: string;
  player?: string;
  team?: string;
  setName?: string;
  isRookie?: boolean;
  isAuto?: boolean;
  quantity?: number;
  description?: string;
};

/**
 * Pulls what eBay insists on out of a title.
 *
 * eBay rejects a listing missing a required specific, and a title is all
 * we hold for most cards. A guess is not written: a field it cannot read
 * is left blank so the upload names the row rather than listing a card
 * under the wrong player.
 */
export function fromTitle(title: string) {
  const t = title.replace(/\s+/g, ' ').trim();
  const year = (t.match(/\b(19|20)\d{2}(-\d{2})?\b/) || [''])[0];
  const number = (t.match(/#\s*([A-Za-z0-9-]+)/) || ['', ''])[1];
  const mfr = ['Topps', 'Panini', 'Bowman', 'Upper Deck', 'Leaf', 'Donruss', 'Fleer', 'Score']
    .find((m) => new RegExp(`\\b${m}\\b`, 'i').test(t)) || '';
  const rookie = /\b(RC|rookie)\b/i.test(t) ? 'Yes' : 'No';
  const auto = /\b(auto|autograph|signed)\b/i.test(t) ? 'Yes' : 'No';
  // Player: the run of words before the year, which is how his titles read.
  let player = '';
  if (year) {
    const before = t.slice(0, t.indexOf(year)).trim();
    if (before && before.split(' ').length <= 5) player = before;
  }
  return { year, number, mfr, rookie, auto, player: player.slice(0, 50) };
}

const LEAGUE: Record<string, string> = {
  Baseball: 'MLB', Basketball: 'NBA', Football: 'NFL',
  Hockey: 'NHL', Soccer: 'FIFA',
};

export function ebayAddCsv(cards: AddCard[], d: AddDefaults): string {
  const rows = cards.map((c) => {
    // A dearer card needs a tracked policy — eBay Standard Envelope is
    // only valid up to $20, and a $300 card posted in one is uninsured.
    const band = (d.shippingBands ?? [])
      .slice()
      .sort((a, b) => a.upTo - b.upTo)
      .find((b) => (c.price ?? 0) <= b.upTo);
    const shipName = band?.profile || d.shippingProfile;
    const shipId = band?.profileId || d.shippingProfileId;
    // Prefer what a person entered; fall back to reading the title.
    const f = fromTitle(c.title);
    const graded = c.grader && c.grade ? 'Yes' : 'No';
    const pics = (c.picUrls ?? []).filter(Boolean);
    const cell: Record<string, string> = Object.fromEntries(ADD_HEADER.map((h) => [h, '']));
    Object.assign(cell, {
      [ADD_HEADER[0]]: 'Add',
      CustomLabel: c.sku,
      '*Category': d.category,
      '*Title': c.title.slice(0, 80),
      '*ConditionID': graded === 'Yes' ? '2750' : '4000',
      '*C:Graded': graded,
      '*C:Sport': c.sport || '',
      '*C:Player/Athlete': (c.player || f.player).slice(0, 65),
      '*C:Manufacturer': c.manufacturer || f.mfr,
      'C:Season': c.year || f.year,
      '*C:League': c.league || LEAGUE[c.sport] || '',
      '*C:Autographed': c.isAuto ? 'Yes' : f.auto,
      '*C:Card Name': (c.player || f.player).slice(0, 65),
      '*C:Card Number': (c.cardNumber || f.number).replace(/^#/, ''),
      '*C:Parallel/Variety': c.parallel || '',
      '*C:Set': c.setName || '',
      '*C:Team': c.team || '',
      '*C:Type': 'Sports Trading Card',
      'C:Year Manufactured': c.year || f.year,
      'CD:Grade - (ID: 27502)': graded === 'Yes' ? c.grade : '',
      'CD:Professional Grader - (ID: 27501)': graded === 'Yes' ? c.grader : '',
      'CDA:Certification Number - (ID: 27503)': graded === 'Yes' ? c.cert : '',
      // eBay rejects an ungraded card with no condition descriptor.
      'CD:Card Condition - (ID: 40001)':
        graded === 'Yes' ? '' : (c.condition || d.conditionDefault || CONDITION_DEFAULT),
      // Front and back. eBay takes them pipe-separated and makes the
      // first one the gallery image.
      PicURL: pics.join('|'),
      GalleryType: pics.length ? 'Gallery' : '',
      '*Description': c.description ||
        (d.description || '{title}<br><br>Ships in a penny sleeve and top loader.')
          .replace(/\{title\}/g, c.title),
      '*Format': 'FixedPrice',
      '*Duration': d.duration,
      '*ReturnsAcceptedOption': d.returnsAccepted || 'ReturnsNotAccepted',
      WeightMajor: d.weightMajor ?? '0',
      WeightMinor: d.weightMinor ?? '4',
      ImmediatePayRequired: d.immediatePay === false ? '0' : '1',
      '*StartPrice': c.price?.toFixed(2) ?? '',
      '*Quantity': String(c.quantity ?? d.quantity ?? 1),
      '*Location': d.location,
      PostalCode: d.postalCode,
      '*DispatchTimeMax': d.dispatchDays,
      // Id where we have it, name only as a fallback — never both, or
      // eBay has two ways to resolve the same policy and may disagree.
      ShippingProfileID: shipId || '',
      ShippingProfileName: shipId ? '' : shipName,
      ReturnProfileID: d.returnProfileId || '',
      ReturnProfileName: d.returnProfileId ? '' : d.returnProfile,
      PaymentProfileID: d.paymentProfileId || '',
      PaymentProfileName: d.paymentProfileId ? '' : d.paymentProfile,
      StoreCategory: (d.storeCategories ?? {})[c.sport] || '0',
      BestOfferEnabled: d.bestOffer ? '1' : '0',
      '*C:Rookie': c.isRookie ? 'Yes' : f.rookie,
      '*C:Memorabilia': 'No',
    });
    return ADD_HEADER.map((h) => cell[h]);
  });

  // eBay wants its own banner on row one, before the header.
  const info = ['Info', 'Version=1.0.0', 'Template=fx_category_template_EBAY_US',
                ...Array(ADD_HEADER.length - 3).fill('')];
  return toCsv(info, [ADD_HEADER, ...rows]);
}

/** Rows eBay will reject, named before the upload rather than after. */
/**
 * What eBay will reject, named before the upload rather than after.
 *
 * Everything here is a field eBay actually requires for category 261328.
 * Finding out from a rejected File Exchange report is a slow way to
 * learn that a sport was blank.
 */
export function addProblems(cards: AddCard[]): { sku: string; why: string }[] {
  const out: { sku: string; why: string }[] = [];
  for (const c of cards) {
    const f = fromTitle(c.title);
    const miss: string[] = [];
    if (!c.title.trim()) miss.push('no title');
    if (c.title.length > 80) miss.push(`title is ${c.title.length} characters, eBay allows 80`);
    if (c.price === null || c.price <= 0) miss.push('no price');
    if (!c.sku) miss.push('no SKU — it cannot be found or costed later');
    if (!c.sport) miss.push('no sport');
    if (!(c.player || f.player)) miss.push('no player');
    if (!(c.year || f.year)) miss.push('no year');
    if (!(c.cardNumber || f.number)) miss.push('no card number');
    if (!(c.picUrls ?? []).length) miss.push('no photo');
    const graded = !!(c.grader && c.grade);
    if (graded && !c.cert) miss.push('graded but no certification number');
    if (!graded && !c.condition) miss.push('no card condition (eBay requires it for ungraded)');
    if (miss.length) out.push({ sku: c.sku || c.title.slice(0, 30), why: miss.join(' · ') });
  }
  return out;
}
