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
  bestOffer: boolean;
  duration: string;
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

export type AddCard = {
  sku: string;
  title: string;
  price: number | null;
  sport: string;
  grader: string;
  grade: string;
  cert: string;
  picUrl?: string;
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
    const f = fromTitle(c.title);
    const graded = c.grader && c.grade ? 'Yes' : 'No';
    const cell: Record<string, string> = Object.fromEntries(ADD_HEADER.map((h) => [h, '']));
    Object.assign(cell, {
      [ADD_HEADER[0]]: 'Add',
      CustomLabel: c.sku,
      '*Category': d.category,
      StoreCategory: '0',
      '*Title': c.title.slice(0, 80),
      '*ConditionID': graded === 'Yes' ? '2750' : '4000',
      '*C:Graded': graded,
      '*C:Sport': c.sport || '',
      '*C:Player/Athlete': f.player,
      '*C:Manufacturer': f.mfr,
      'C:Season': f.year,
      '*C:League': LEAGUE[c.sport] || '',
      '*C:Autographed': f.auto,
      '*C:Card Name': f.player,
      '*C:Card Number': f.number,
      '*C:Type': 'Sports Trading Card',
      'C:Year Manufactured': f.year,
      'CD:Grade - (ID: 27502)': graded === 'Yes' ? c.grade : '',
      'CD:Professional Grader - (ID: 27501)': graded === 'Yes' ? c.grader : '',
      'CDA:Certification Number - (ID: 27503)': graded === 'Yes' ? c.cert : '',
      'CD:Card Condition - (ID: 40001)': graded === 'Yes' ? '' : '400011',
      PicURL: c.picUrl || '',
      GalleryType: c.picUrl ? 'Gallery' : '',
      '*Description': `${c.title}<br><br>Ships in a penny sleeve and top loader.`,
      '*Format': 'FixedPrice',
      '*Duration': d.duration,
      '*StartPrice': c.price?.toFixed(2) ?? '',
      '*Quantity': '1',
      ImmediatePayRequired: '1',
      '*Location': d.location,
      PostalCode: d.postalCode,
      WeightMajor: '0',
      WeightMinor: '4',
      '*DispatchTimeMax': d.dispatchDays,
      '*ReturnsAcceptedOption': 'ReturnsNotAccepted',
      ShippingProfileName: d.shippingProfile,
      ReturnProfileName: d.returnProfile,
      PaymentProfileName: d.paymentProfile,
      BestOfferEnabled: d.bestOffer ? '1' : '0',
      '*C:Rookie': f.rookie,
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
export function addProblems(cards: AddCard[]): { sku: string; why: string }[] {
  const out: { sku: string; why: string }[] = [];
  for (const c of cards) {
    const f = fromTitle(c.title);
    const miss: string[] = [];
    if (!c.title.trim()) miss.push('no title');
    if (c.title.length > 80) miss.push(`title is ${c.title.length} characters, eBay allows 80`);
    if (c.price === null || c.price <= 0) miss.push('no price');
    if (!c.sport) miss.push('no sport');
    if (!f.player) miss.push('player not readable from the title');
    if (!f.year) miss.push('no year in the title');
    if (miss.length) out.push({ sku: c.sku || c.title.slice(0, 30), why: miss.join(' · ') });
  }
  return out;
}
