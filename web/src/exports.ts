/* ------------------------------------------------------------------ *
 * Files out.
 *
 * eBay gives this account no API, so every change to a live listing
 * leaves here as a file he uploads himself. That is not a workaround to
 * be apologised for — File Exchange revises thousands of listings in one
 * go, and it is the same loop a seller with API access would run, minus
 * the API.
 * ------------------------------------------------------------------ */

function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(headers: string[], rows: unknown[][]): string {
  return [headers, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n';
}

export function download(name: string, body: string, type = 'text/csv;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export const stamp = () => {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

/**
 * eBay File Exchange — revise price.
 *
 * The header line matters: File Exchange needs the Action column first
 * and the version banner on row one, or it rejects the whole file.
 */
export function fileExchangeRevise(
  rows: { item_number: string; price: number }[],
): string {
  const head = 'Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)';
  const body = toCsv([head, 'ItemID', 'StartPrice'],
    rows.map((r) => ['Revise', r.item_number, r.price.toFixed(2)]));
  return body;
}

/** eBay File Exchange — end listings (sold elsewhere, or pulling stock). */
export function fileExchangeEnd(itemNumbers: string[]): string {
  const head = 'Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)';
  return toCsv([head, 'ItemID', 'EndCode'],
    itemNumbers.map((id) => ['End', id, 'NotAvailable']));
}

/** A plain review file — what changed and why, for reading before uploading. */
export function reviewCsv(
  rows: { sku: string; item_number: string; title: string;
          was: number | null; now: number | null; comp: number | null; why: string }[],
): string {
  return toCsv(
    ['SKU', 'Item number', 'Title', 'Current price', 'New price', 'Change', 'Comp', 'Why'],
    rows.map((r) => [
      r.sku, r.item_number, r.title,
      r.was?.toFixed(2) ?? '', r.now?.toFixed(2) ?? '',
      r.was !== null && r.now !== null ? (r.now - r.was).toFixed(2) : '',
      r.comp?.toFixed(2) ?? '', r.why,
    ]));
}

/**
 * A working file for Card Luma / Heystack / the website.
 *
 * Deliberately plain columns rather than one vendor's shape: every
 * scanner he uses exports eBay File Exchange anyway, and the thing that
 * changes between them is which columns they fill, not what they are
 * called. One readable file beats three half-right ones.
 */
export function workingCsv(
  rows: { sku: string; item_number: string; title: string; price: number | null;
          sport: string; grade: string; cert: string; days: number | null;
          comp: number | null; watchers: number | null }[],
): string {
  return toCsv(
    ['SKU', 'Item number', 'Title', 'Price', 'Sport', 'Grade',
     'Cert number', 'Days listed', 'Comp', 'Watchers'],
    rows.map((r) => [
      r.sku, r.item_number, r.title, r.price?.toFixed(2) ?? '',
      r.sport, r.grade, r.cert, r.days ?? '', r.comp?.toFixed(2) ?? '',
      r.watchers ?? '',
    ]));
}
