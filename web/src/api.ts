/**
 * Everything that talks to the Worker.
 *
 * The browser holds a session token, never the API key — see the sign-in
 * comment in the Worker. A 401 anywhere means the session is gone, so it is
 * handled in one place rather than at every call site.
 */

export const API = 'https://dfs-cards-api.duane-588.workers.dev';

const TOKEN_KEY = 'cp_token';
const WHO_KEY = 'cp_who';

export type Who = { name: string | null; slug: string; is_owner: boolean };

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const getWho = (): Who | null => {
  try { return JSON.parse(localStorage.getItem(WHO_KEY) || 'null'); } catch { return null; }
};

export function signOut() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(WHO_KEY);
  location.reload();
}

export class Expired extends Error {}

async function call(path: string, init: RequestInit = {}): Promise<any> {
  const token = getToken();
  const r = await fetch(API + path, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  const text = await r.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { error: text.slice(0, 200) }; }
  if (r.status === 401) throw new Expired(body?.error || 'session expired');
  if (!r.ok) throw new Error(body?.error || `HTTP ${r.status}`);
  return body;
}

export async function signIn(code: string): Promise<Who> {
  const d = await call('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ code: code.trim().toUpperCase() }),
  });
  localStorage.setItem(TOKEN_KEY, d.token);
  const who: Who = { name: d.name, slug: d.slug, is_owner: d.is_owner };
  localStorage.setItem(WHO_KEY, JSON.stringify(who));
  return who;
}

export const me = () => call('/api/me');

/* ---------------- listings ---------------- */

export type Listing = {
  item_number: string;
  title: string;
  sku: string;
  current_price: string | number | null;
  start_date: string | null;
  end_date: string | null;
  watchers: number | null;
  sold_qty: number | null;
  condition: string | null;
  grader: string | null;
  grade: string | null;
  cert_number: string | null;
  sport: string | null;
  is_rookie: boolean | null;
  cost_basis: string | number | null;
  comp_avg: string | number | null;
  trend_dir: string | null;
  trend_pct: string | number | null;
  suggested_price: string | number | null;
  last_priced_at: string | null;
  created_at: string | null;
};

/**
 * The Worker returns numeric columns as strings (postgres.js default, kept
 * deliberately so CardPulse's own coercion keeps working). Anything that is
 * going to be compared or summed has to go through here first — a forgotten
 * one is how "2.00" < 0.0 threw in Claim Sale.
 */
export function num(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
}

/** Pandas wrote the string "nan" into text columns on an early import. */
export function text(v: unknown): string {
  const s = (v ?? '').toString().trim();
  return s === '' || s.toLowerCase() === 'nan' || s === 'None' ? '' : s;
}

/**
 * Pulls every listing. The Worker pages at 1000, so this walks until a short
 * page comes back. ~4,500 rows is about five round trips and then the browser
 * owns the data — which is the entire reason filtering is instant here and
 * was not in Streamlit.
 */
export async function fetchListings(onProgress?: (n: number) => void): Promise<Listing[]> {
  const out: Listing[] = [];
  const page = 1000;
  for (let offset = 0; ; offset += page) {
    const d = await call(`/api/db/listings?limit=${page}&offset=${offset}&order=created_at.desc`);
    const rows: Listing[] = d?.data || [];
    out.push(...rows);
    onProgress?.(out.length);
    if (rows.length < page) break;
    if (offset > 100_000) break;                       // never loop forever
  }
  return out;
}
