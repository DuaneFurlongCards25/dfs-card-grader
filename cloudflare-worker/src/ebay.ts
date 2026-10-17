/**
 * eBay — the real connection.
 *
 * ## Why this is possible, having been told for months that it was not
 *
 * eBay has two API families and only one of them is gated:
 *
 *   Sell  (Inventory, Fulfillment, Account) — list, revise, end, read your
 *         own orders. Open to any registered developer acting on their own
 *         seller account. THIS FILE.
 *   Buy   (Browse, Marketplace Insights) — sold prices, market data.
 *         Partner only, approval not guaranteed, and the reason every card
 *         app prices off TCGplayer or CardHedger instead.
 *
 * Heystack, Card Luma and Leumas Live all have a "list to eBay" button for
 * exactly this reason, and none of them can price off eBay.
 *
 * ## The one secret that matters
 *
 * The refresh token lets this app act on his account for 18 months. It is
 * stored in the database, read only by the Worker, and never sent to a
 * browser. The access token it mints lasts two hours and is cached so a
 * run of 300 listings does not ask for 300 tokens.
 */

const EBAY = {
  auth: 'https://auth.ebay.com/oauth2/authorize',
  token: 'https://api.ebay.com/identity/v1/oauth2/token',
  api: 'https://api.ebay.com',
  trading: 'https://api.ebay.com/ws/api.dll',
};

/** What the app asks permission to do. Listing and reading his own orders. */
export const EBAY_SCOPES = [
  'https://api.ebay.com/oauth/api_scope',
  'https://api.ebay.com/oauth/api_scope/sell.inventory',
  'https://api.ebay.com/oauth/api_scope/sell.account',
  'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
].join(' ');

export type EbayEnv = {
  EBAY_APP_ID?: string;       // Client ID
  EBAY_CERT_ID?: string;      // Client Secret
  EBAY_RU_NAME?: string;      // the redirect name eBay issues
};

const basic = (e: EbayEnv) => btoa(`${e.EBAY_APP_ID}:${e.EBAY_CERT_ID}`);

export function ebayConsentUrl(e: EbayEnv, state: string): string {
  const p = new URLSearchParams({
    client_id: e.EBAY_APP_ID || '',
    redirect_uri: e.EBAY_RU_NAME || '',
    response_type: 'code',
    scope: EBAY_SCOPES,
    state,
  });
  return `${EBAY.auth}?${p}`;
}

/** Trades the one-time code from the consent redirect for a refresh token. */
export async function ebayExchangeCode(e: EbayEnv, code: string) {
  const r = await fetch(EBAY.token, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${basic(e)}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: e.EBAY_RU_NAME || '',
    }),
  });
  const body = await r.json() as any;
  if (!r.ok) throw new Error(body?.error_description || body?.error || `HTTP ${r.status}`);
  return body as { refresh_token: string; access_token: string; expires_in: number };
}

/**
 * A usable access token.
 *
 * Cached in the row until two minutes before it expires. Refresh tokens
 * last 18 months; when one finally dies eBay says so clearly, and that
 * message is passed through rather than swallowed, because "connect eBay
 * again" is a thing he can act on and "500" is not.
 */
export async function ebayAccessToken(e: EbayEnv, sql: any, schema: string): Promise<string> {
  const [row] = await sql.unsafe(
    `SELECT refresh_token, access_token, access_expires
       FROM "${schema}"."marketplace_tokens" WHERE marketplace = 'ebay'`);
  if (!row) throw new Error('eBay is not connected — open Settings and connect it');

  if (row.access_token && row.access_expires &&
      new Date(row.access_expires).getTime() > Date.now() + 120_000) {
    return row.access_token;
  }

  const r = await fetch(EBAY.token, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${basic(e)}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: row.refresh_token,
      scope: EBAY_SCOPES,
    }),
  });
  const body = await r.json() as any;
  if (!r.ok) {
    throw new Error(body?.error_description === 'the refresh token is expired'
      ? 'the eBay connection has expired — connect it again'
      : (body?.error_description || body?.error || `eBay refused the refresh (HTTP ${r.status})`));
  }
  const expires = new Date(Date.now() + (body.expires_in ?? 7200) * 1000).toISOString();
  await sql.unsafe(
    `UPDATE "${schema}"."marketplace_tokens"
        SET access_token = $1, access_expires = $2, updated_at = now()
      WHERE marketplace = 'ebay'`, [body.access_token, expires]);
  return body.access_token as string;
}

export async function ebayCall(
  token: string, path: string, init: RequestInit = {},
): Promise<{ ok: boolean; status: number; body: any }> {
  const r = await fetch(EBAY.api + path, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'Content-Language': 'en-US',
      'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
      ...(init.headers || {}),
    },
  });
  const text = await r.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text.slice(0, 400) }; }
  return { ok: r.ok, status: r.status, body };
}

/**
 * The message eBay actually gave, in one line.
 *
 * eBay nests its complaints several levels down and returns 200 with an
 * error inside often enough that pulling this out properly is the
 * difference between "it failed" and "title is over 80 characters".
 */
export function ebayWhy(body: any): string {
  const errs = body?.errors || body?.warnings ||
               body?.responses?.flatMap?.((x: any) => x?.errors ?? []) || [];
  if (Array.isArray(errs) && errs.length) {
    return errs.map((x: any) =>
      [x?.message, x?.longMessage, x?.parameters?.map?.((p: any) => `${p.name}=${p.value}`).join(' ')]
        .filter(Boolean).join(' — ')).join(' | ').slice(0, 400);
  }
  return typeof body === 'string' ? body.slice(0, 300) : JSON.stringify(body ?? {}).slice(0, 300);
}

/** Price change on a live listing — the Sunday job, without a CSV. */
export async function ebayRevisePrice(token: string, offerId: string, price: number) {
  return ebayCall(token, `/sell/inventory/v1/offer/${encodeURIComponent(offerId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ pricingSummary: { price: { value: price.toFixed(2), currency: 'USD' } } }),
  });
}

export async function ebayEndOffer(token: string, offerId: string) {
  return ebayCall(token, `/sell/inventory/v1/offer/${encodeURIComponent(offerId)}/withdraw`,
                  { method: 'POST' });
}

/** Orders since a date — replaces downloading the orders report by hand. */
export async function ebayOrders(token: string, sinceIso: string, limit = 200) {
  const p = new URLSearchParams({
    filter: `creationdate:[${sinceIso}..]`,
    limit: String(limit),
  });
  return ebayCall(token, `/sell/fulfillment/v1/order?${p}`);
}
