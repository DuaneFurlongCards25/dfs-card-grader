/**
 * DFS Cards API — CardPulse's own Worker.
 *
 * Split out of the studio's `dfs-api` on purpose. That Worker carries client
 * bookings, the portal, invoices, Square checkout and staff sign-in for DFS
 * Studios. This one serves the card business, which is a different company.
 * Two consequences, both deliberate:
 *
 *   1. A bad deploy here cannot stop a client paying for a session.
 *   2. The cards app cannot reach leads, payroll or portal data — the table
 *      allow-list below is the whole surface.
 *
 * Same Neon database, its own DATABASE_URL secret, its own R2 bucket.
 *
 * ## Type parsing matters more than it looks
 *
 * postgres.js returns bigint and date as strings by default. The studio Worker
 * learned this the hard way: `leads.find(l => l.id === id)` fails when one is
 * a string, and an <input type="date"> rejects a Date object. The same parsers
 * are set here. `numeric` is left as a string to match the studio Worker's
 * behaviour exactly — CardPulse already coerces those (see coerce_listings in
 * app.py), and quietly changing the shape under it would be a worse surprise
 * than the inconsistency.
 */

import postgres from 'postgres';

export interface Env {
  DATABASE_URL: string;
  API_KEY?: string;
  CARD_IMAGES?: R2Bucket;
  HYPERDRIVE?: { connectionString: string };
}

/**
 * Nothing reaches the database without the key.
 *
 * This Worker serves purchase costs, sale proceeds, margins and break P&L —
 * the whole card business — so an unauthenticated `/api/db/*` is the business
 * readable by anyone who learns the URL. The studio Worker shipped with its
 * gate defaulting OPEN when the secret was unset, and it has stayed open for
 * months because a public lead form depends on it. That mistake is not
 * repeated here: a missing key fails CLOSED, so the failure mode is "my app
 * stopped working" rather than silent exposure.
 *
 * Exceptions are deliberate and narrow: `/api/health` reveals nothing but
 * connectivity, and image GETs are fetched by the browser from an <img> tag
 * that cannot carry a header. Those R2 keys are long and unguessable, which
 * is obscurity, not access control — the fix is signed URLs, and it is only
 * card photographs, not costs.
 */
function authed(request: Request, env: Env): boolean {
  if (!env.API_KEY) return false;
  const sent = request.headers.get('X-DFS-Key') || '';
  // Constant-ish time: compare full length rather than bailing on first byte.
  if (sent.length !== env.API_KEY.length) return false;
  let diff = 0;
  for (let i = 0; i < sent.length; i++) diff |= sent.charCodeAt(i) ^ env.API_KEY.charCodeAt(i);
  return diff === 0;
}

// Only the card business. Anything not listed is a 403 — new tables are
// locked by default rather than exposed by forgetting.
const ALLOWED_TABLES = new Set([
  // inventory + intake
  'inventory_cards', 'inventory_boxes', 'card_listings', 'intake_batches',
  'card_events',
  // buying, selling, grading
  'purchase_lots', 'lot_cards', 'card_purchases', 'sales_records', 'listings',
  'grading_tracker', 'shipment_intake', 'scan_cards', 'scan_stacks',
  'break_spots',
  // consignment
  'consignment_items', 'consignment_lots', 'consignment_shipments',
  // app plumbing
  'access_codes', 'pricing_usage', 'support_tickets',
  // Owner-only; see the guard in handleDb.
  'tenants',
]);

/**
 * Tables that are the same for everyone and live only in `public`.
 *
 * Login has to work before a tenant is known — resolving the tenant means
 * reading `access_codes`, so it cannot itself be per-tenant. Metering is
 * deliberately shared too: a daily look-up budget that each tenant could
 * reset by writing to their own copy is not a budget.
 */
const SHARED_TABLES = new Set(['access_codes', 'pricing_usage', 'tenants',
                               'support_tickets']);
// Same list for SQL: a shared table lives only in public and must never be
// copied into a tenant schema by the drift repair.
const SHARED_LIST = [...SHARED_TABLES, 'support_log'];

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-API-Key, Authorization',
};

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status, headers: { 'Content-Type': 'application/json', ...CORS },
  });

const err = (message: string, status = 400) => json({ error: message }, status);

function getSql(env: Env) {
  // A fresh client per request: Cloudflare I/O objects cannot outlive the
  // request that created them.
  return postgres(env.HYPERDRIVE?.connectionString || env.DATABASE_URL, {
    ssl: 'require',
    max: 1,
    idle_timeout: 5,
    connect_timeout: 10,
    fetch_types: true,
    types: {
      bigint: {
        to: 20, from: [20],
        serialize: (x: any) => x.toString(),
        parse: (x: string) => Number(x),
      },
      date: {
        to: 1082, from: [1082, 1114, 1184],
        serialize: (x: any) => x,
        // Dates as yyyy-MM-dd strings; a Date object breaks date inputs.
        parse: (x: string) => x,
      },
    },
  });
}

const IDENT = /^[a-z_][a-z0-9_]*$/i;

/** Supabase-style query params, matching what CardPulse already sends. */
function parseFilters(url: URL) {
  const params: any[] = [];
  const where: string[] = [];
  let orderSql = '';
  let limit: number | null = null;

  for (const [key, value] of url.searchParams) {
    if (key === 'order') {
      const [col, dir] = value.split('.');
      if (col && IDENT.test(col)) {
        orderSql = `ORDER BY "${col}" ${dir === 'desc' ? 'DESC' : 'ASC'}`;
      }
      continue;
    }
    if (key === 'limit') {
      const n = parseInt(value, 10);
      if (n > 0 && n <= 10000) limit = n;
      continue;
    }
    if (key === 'select' || key === 'single') continue;
    if (!IDENT.test(key)) continue;

    const dot = value.indexOf('.');
    const op = dot > 0 ? value.slice(0, dot) : 'eq';
    const arg = dot > 0 ? value.slice(dot + 1) : value;
    const p = () => `$${params.length + 1}`;

    if (op === 'eq') { where.push(`"${key}" = ${p()}`); params.push(arg); }
    else if (op === 'neq') { where.push(`"${key}" <> ${p()}`); params.push(arg); }
    else if (op === 'gt') { where.push(`"${key}" > ${p()}`); params.push(arg); }
    else if (op === 'gte') { where.push(`"${key}" >= ${p()}`); params.push(arg); }
    else if (op === 'lt') { where.push(`"${key}" < ${p()}`); params.push(arg); }
    else if (op === 'lte') { where.push(`"${key}" <= ${p()}`); params.push(arg); }
    else if (op === 'like' || op === 'ilike') {
      where.push(`"${key}" ${op === 'ilike' ? 'ILIKE' : 'LIKE'} ${p()}`);
      params.push(arg.replace(/\*/g, '%'));
    }
    else if (op === 'in') {
      const items = arg.replace(/^\(|\)$/g, '').split(',').filter(Boolean);
      if (!items.length) continue;
      // push() returns the new length, which is exactly this value's 1-based
      // placeholder number — so numbering stays correct however many filters
      // came before this one.
      const holders = items.map(v => `$${params.push(v)}`);
      where.push(`"${key}" IN (${holders.join(',')})`);
    }
    else if (op === 'is') {
      if (arg === 'null') where.push(`"${key}" IS NULL`);
      else if (arg === 'notnull' || arg === 'not.null') where.push(`"${key}" IS NOT NULL`);
    }
    else if (op === 'not') {
      if (arg === 'is.null') where.push(`"${key}" IS NOT NULL`);
      else if (arg === 'is.notnull') where.push(`"${key}" IS NULL`);
    }
  }
  return {
    whereSql: where.length ? 'WHERE ' + where.join(' AND ') : '',
    params, orderSql, limit,
  };
}

/**
 * Which tenant's data is this request for?
 *
 * One Postgres schema per tenant. Not one row-filter per tenant: `app.py` is
 * 14,000 lines and every query would have to carry the filter forever, where
 * one omission silently serves another dealer their competitor's costs. A
 * schema cannot be forgotten — the table does not exist outside it.
 *
 * The caller proves two separate things. `X-DFS-Key` proves the request came
 * from our deployment (see `authed`). `X-DFS-Tenant` says which tenant the
 * signed-in user belongs to, and is their access code — the thing the app
 * already has at login.
 *
 * The header is REQUIRED, with no default. A default of "public" would mean
 * any bug that drops the header hands a beta user the owner's books, which is
 * the exact failure this design exists to make impossible. The owner is not
 * special-cased: DFS-MASTER is a row in `tenants` like everyone else.
 */
const SCHEMA_OK = /^[a-z_][a-z0-9_]*$/;

async function resolveTenant(request: Request, sql: any): Promise<{ slug: string; schema: string }> {
  const code = (request.headers.get('X-DFS-Tenant') || '').trim();
  if (!code) throw new TenantError('X-DFS-Tenant header required', 400);

  const rows = await sql`
    select t.slug, t.schema_name, t.active as t_active,
           c.active as c_active, c.expires_at
      from access_codes c
      join tenants t on t.id = c.tenant_id
     where c.code = ${code}
     limit 1`;
  if (!rows.length) throw new TenantError('unknown tenant', 403);

  const r = rows[0];
  if (!r.c_active) throw new TenantError('access suspended', 403);
  if (!r.t_active) throw new TenantError('tenant suspended', 403);
  if (r.expires_at && new Date(r.expires_at) < new Date())
    throw new TenantError('access expired', 403);

  // Interpolated into SQL below, so it is validated rather than trusted —
  // even though it comes from our own table and not the request.
  if (!SCHEMA_OK.test(r.schema_name)) throw new TenantError('bad schema name', 500);
  return { slug: r.slug, schema: r.schema_name };
}

async function tenantSchema(request: Request, sql: any): Promise<string> {
  return (await resolveTenant(request, sql)).schema;
}

class TenantError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

async function handleDb(request: Request, env: Env, table: string, id: string | null) {
  if (!ALLOWED_TABLES.has(table)) return err(`table not allowed: ${table}`, 403);
  const sql = getSql(env);
  try {
    const url = new URL(request.url);
    // Tables shared across tenants (login, metering) always live in public.
    // `tenants` is the exception among them: it is the list of everyone using
    // CardPulse, so only the owner's account may read it — otherwise any
    // tester could enumerate the others.
    if (table === 'tenants' && (await tenantSchema(request, sql)) !== 'public')
      return err('owner only', 403);

    /**
     * Support tickets are shared on purpose: Duane has to see a tester's
     * problem, and a ticket filed into the tester's own schema would be
     * invisible to him — which is the one thing a support channel must not be.
     *
     * So the row is scoped here instead. A tester reads only their own
     * tickets, and the tenant on a new ticket is stamped from their access
     * code rather than taken from the request, so it cannot be forged or
     * mistyped into someone else's queue.
     */
    if (table === 'support_tickets') {
      const t = await resolveTenant(request, sql);
      if (t.schema !== 'public') {
        if (request.method === 'DELETE') return err('owner only', 403);
        if (request.method === 'GET') url.searchParams.set('tenant_slug', `eq.${t.slug}`);
        if (request.method === 'POST') {
          const body = await request.json().catch(() => null);
          const rows = (Array.isArray(body) ? body : [body]).filter(Boolean)
            .map((r: any) => ({ ...r, tenant_slug: t.slug, status: 'open' }));
          request = new Request(request.url, {
            method: 'POST', headers: request.headers, body: JSON.stringify(rows),
          });
        }
        if (request.method === 'PATCH') return err('owner only', 403);
      }
    }

    const schema = SHARED_TABLES.has(table) ? 'public' : await tenantSchema(request, sql);

    if (request.method === 'GET') {
      if (id) {
        const rows = await sql.unsafe(`SELECT * FROM "${schema}"."${table}" WHERE id = $1`, [id]);
        return rows.length ? json(rows[0]) : err('not found', 404);
      }
      const { whereSql, params, orderSql, limit } = parseFilters(url);
      const rows = await sql.unsafe(
        `SELECT * FROM "${schema}"."${table}" ${whereSql} ${orderSql} LIMIT ${limit || 500}`.trim(),
        params);
      return json({ data: rows, count: rows.length });
    }

    if (request.method === 'POST') {
      const body = await request.json() as any;
      const rows = Array.isArray(body) ? body : [body];
      if (!rows.length) return err('empty body');
      const cols = Object.keys(rows[0]).filter(c => IDENT.test(c));
      if (!cols.length) return err('no columns in body');

      const params: any[] = [];
      const tuples = rows.map(r =>
        `(${cols.map(c => `$${params.push((r as any)[c])}`).join(',')})`);
      const colSql = cols.map(c => `"${c}"`).join(',');
      const onConflict = url.searchParams.get('on_conflict');
      let sqlText =
        `INSERT INTO "${schema}"."${table}" (${colSql}) OVERRIDING SYSTEM VALUE ` +
        `VALUES ${tuples.join(',')}`;
      if (onConflict) {
        const keys = onConflict.split(',').map(c => c.trim()).filter(c => IDENT.test(c));
        if (!keys.length) return err('bad on_conflict');
        // Only the columns actually sent are updated, so a sync that omits
        // location/cost/notes cannot wipe what a person typed.
        sqlText += ` ON CONFLICT (${keys.map(c => `"${c}"`).join(',')}) DO UPDATE SET ` +
          cols.map(c => `"${c}" = EXCLUDED."${c}"`).join(', ');
      }
      sqlText += ' RETURNING *';
      const out = await sql.unsafe(sqlText, params);
      return json({ data: out, count: out.length });
    }

    if (request.method === 'PATCH') {
      if (!id) return err('id required');
      const body = await request.json() as Record<string, any>;
      const cols = Object.keys(body).filter(c => IDENT.test(c));
      if (!cols.length) return err('no columns');
      const params: any[] = [];
      const sets = cols.map(c => `"${c}" = $${params.push(body[c])}`).join(', ');
      const out = await sql.unsafe(
        `UPDATE "${schema}"."${table}" SET ${sets} WHERE id = $${params.push(id)} RETURNING *`, params);
      return out.length ? json({ data: out }) : err('not found', 404);
    }

    if (request.method === 'DELETE') {
      if (!id) return err('id required');
      const out = await sql.unsafe(
        `DELETE FROM "${schema}"."${table}" WHERE id = $1 RETURNING *`, [id]);
      return out.length ? json({ data: out }) : err('not found', 404);
    }

    return err('method not allowed', 405);
  } catch (e: any) {
    // A tenant that cannot be resolved is a 403, not a 500 — and must never
    // fall through to a query, which is why it throws rather than returning.
    if (e instanceof TenantError) return err(e.message, e.status);
    return err(`db error: ${String(e?.message || e).slice(0, 300)}`, 500);
  } finally {
    await sql.end({ timeout: 5 }).catch(() => {});
  }
}

// ── Tenant schema drift ─────────────────────────────────────────────────────
/**
 * Keep every tenant's tables identical to the owner's.
 *
 * A new feature ships DDL. It is applied to `public`, where the owner works,
 * and the tenant schemas are left behind — so a tester hits "column does not
 * exist" on a feature that is perfect from the owner's account, invisible to
 * him and impossible for them to describe.
 *
 * A command-line script existed for this and relied on someone remembering to
 * run it, which is not a plan. The app checks on its own and offers the fix.
 *
 * This is the only route that runs DDL, so it is narrow on purpose:
 *   - owner only (schema `public`);
 *   - it compares against `public`'s own catalog and generates the statements
 *     itself — nothing in the request body becomes SQL;
 *   - identifiers are validated even though they come from our own catalog;
 *   - it only ever ADDs. Nothing is dropped or altered, so the worst outcome
 *     of a bug here is a column nobody uses.
 */
const IDENT_OK = /^[a-z_][a-z0-9_]*$/;
const TYPE_OK = /^[a-z0-9_ ()\[\],."']+$/i;

/**
 * Delete a tenant: their codes, their registry row, and their data.
 *
 * This is the only route that drops anything, and it cannot be undone, so it
 * asks the caller to prove intent rather than trusting a single click:
 * `confirm` must equal the slug being deleted. A mis-aimed request fails
 * instead of taking the wrong dealer's inventory with it.
 *
 * `public` can never be the target — that is the owner's own data and there
 * is no reason this route should ever be the thing that removes it.
 */
async function tenantDelete(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    if ((await tenantSchema(request, sql)) !== 'public') return err('owner only', 403);
    const body = await request.json().catch(() => null) as
      { slug?: string; confirm?: string } | null;
    const slug = (body?.slug || '').trim();
    if (!slug) return err('slug required');
    if (body?.confirm !== slug)
      return err('confirm must match the slug exactly', 400);

    const [t] = await sql`select id, schema_name from tenants where slug = ${slug}`;
    if (!t) return err(`no tenant '${slug}'`, 404);
    if (t.schema_name === 'public') return err('refusing to delete the owner', 403);
    if (!IDENT_OK.test(t.schema_name)) return err('bad schema name', 500);

    const [{ rows }] = await sql`
      select coalesce(sum(n_live_tup), 0)::bigint as rows
        from pg_stat_user_tables where schemaname = ${t.schema_name}`;

    await sql.unsafe(`DROP SCHEMA IF EXISTS "${t.schema_name}" CASCADE`);
    await sql`delete from access_codes where tenant_id = ${t.id}`;
    await sql`delete from support_tickets where tenant_slug = ${slug}`;
    await sql`delete from tenants where id = ${t.id}`;

    return json({ deleted: slug, schema: t.schema_name, rows_removed: Number(rows) });
  } catch (e: any) {
    if (e instanceof TenantError) return err(e.message, e.status);
    return err(`delete: ${String(e?.message || e).slice(0, 300)}`, 500);
  } finally {
    await sql.end({ timeout: 5 }).catch(() => {});
  }
}

async function tenantDrift(request: Request, env: Env, apply: boolean) {
  const sql = getSql(env);
  try {
    if ((await tenantSchema(request, sql)) !== 'public') return err('owner only', 403);

    const tenants = await sql`
      select slug, schema_name from tenants
       where schema_name <> 'public' and active order by id`;

    const wanted = await sql`
      select table_name from information_schema.tables
       where table_schema = 'public' and table_type = 'BASE TABLE'
         and table_name <> all(${SHARED_LIST})
       order by table_name`;

    const report: any[] = [];
    for (const t of tenants) {
      if (!IDENT_OK.test(t.schema_name)) continue;
      const have = new Set((await sql`
        select table_name from information_schema.tables
         where table_schema = ${t.schema_name} and table_type = 'BASE TABLE'`)
        .map((r: any) => r.table_name));

      const missingTables: string[] = [];
      const missingCols: any[] = [];
      for (const w of wanted) {
        const name = w.table_name;
        if (!IDENT_OK.test(name)) continue;
        if (!have.has(name)) { missingTables.push(name); continue; }
        // format_type, not information_schema.data_type: the latter reports
        // numeric without its precision, calling two different columns equal.
        const cols = await sql`
          select a.attname as name,
                 format_type(a.atttypid, a.atttypmod) as type,
                 coalesce(pg_get_expr(d.adbin, d.adrelid), '') as dflt,
                 a.attrelid::regclass::text as src
            from pg_attribute a
            left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
           where a.attrelid = ${'public."' + name + '"'}::regclass
             and a.attnum > 0 and not a.attisdropped`;
        const theirs = new Set((await sql`
          select attname from pg_attribute
           where attrelid = ${t.schema_name + '."' + name + '"'}::regclass
             and attnum > 0 and not attisdropped`).map((r: any) => r.attname));
        for (const c of cols) {
          if (!theirs.has(c.name) && IDENT_OK.test(c.name) && TYPE_OK.test(c.type))
            missingCols.push({ table: name, column: c.name, type: c.type });
        }
      }

      let applied = 0;
      if (apply && (missingTables.length || missingCols.length)) {
        for (const name of missingTables) {
          // LIKE copies types, defaults, identity, constraints and indexes
          // from the live table, so a new table cannot arrive already stale.
          await sql.unsafe(`CREATE TABLE "${t.schema_name}"."${name}" ` +
                           `(LIKE public."${name}" INCLUDING ALL)`);
          applied++;
        }
        for (const c of missingCols) {
          // No NOT NULL: an existing tenant row has no value for a new
          // column, and the migration would fail on it.
          await sql.unsafe(`ALTER TABLE "${t.schema_name}"."${c.table}" ` +
                           `ADD COLUMN IF NOT EXISTS "${c.column}" ${c.type}`);
          applied++;
        }
      }

      report.push({
        slug: t.slug, schema: t.schema_name,
        missing_tables: missingTables,
        missing_columns: missingCols,
        behind: missingTables.length + missingCols.length,
        applied,
      });
    }
    return json({
      tenants: report,
      behind: report.filter((r) => r.behind > (apply ? r.applied : 0)).length,
      total_changes: report.reduce((n, r) => n + r.behind, 0),
      applied: report.reduce((n, r) => n + r.applied, 0),
    });
  } catch (e: any) {
    if (e instanceof TenantError) return err(e.message, e.status);
    return err(`drift: ${String(e?.message || e).slice(0, 300)}`, 500);
  } finally {
    await sql.end({ timeout: 5 }).catch(() => {});
  }
}

// ── Card images ────────────────────────────────────────────────────────────
// Heystack and Card Dealer Pro host card photos on their own S3, and those are
// the URLs their exports carry. Point a Shopify product or an Instagram post
// at them and the catalogue dies the day that account lapses — by which time
// the cards are filed away in boxes. These two routes keep our own copy.

const IMG_MAX = 12 * 1024 * 1024;

async function mirror(request: Request, env: Env) {
  if (!env.CARD_IMAGES) return err('image bucket not bound', 500);
  const body = await request.json().catch(() => null) as
    { sku?: string; urls?: string[] } | null;
  const sku = (body?.sku || '').trim();
  const urls = (body?.urls || []).filter(u => /^https?:\/\//i.test(u));
  if (!sku) return err('sku required');
  if (!urls.length) return err('no urls');

  const base = new URL(request.url).origin;
  const safe = sku.replace(/[^A-Za-z0-9._-]/g, '_');
  const out: string[] = [];
  const failed: { url: string; why: string }[] = [];

  for (let i = 0; i < urls.length && i < 20; i++) {
    const key = `inventory/${safe}/${i + 1}`;
    try {
      // Re-running after a partial failure should be cheap, not a re-download.
      if (await env.CARD_IMAGES.head(key)) {
        out.push(`${base}/api/inventory/img/${encodeURIComponent(key)}`);
        continue;
      }
      const r = await fetch(urls[i]);
      if (!r.ok) { failed.push({ url: urls[i], why: `HTTP ${r.status}` }); continue; }
      const type = r.headers.get('content-type') || 'image/jpeg';
      if (!type.startsWith('image/')) { failed.push({ url: urls[i], why: `not an image (${type})` }); continue; }
      const buf = await r.arrayBuffer();
      if (buf.byteLength > IMG_MAX) { failed.push({ url: urls[i], why: 'too large' }); continue; }
      if (buf.byteLength < 1024) { failed.push({ url: urls[i], why: 'too small to be a card photo' }); continue; }
      await env.CARD_IMAGES.put(key, buf, {
        httpMetadata: { contentType: type, cacheControl: 'public, max-age=31536000, immutable' },
        customMetadata: { sku, source: urls[i].slice(0, 500), mirrored_at: new Date().toISOString() },
      });
      out.push(`${base}/api/inventory/img/${encodeURIComponent(key)}`);
    } catch (e: any) {
      failed.push({ url: urls[i], why: String(e?.message || e).slice(0, 120) });
    }
  }
  return json({ sku, mirrored: out.length, urls: out, failed });
}

async function serveImage(env: Env, key: string) {
  if (!env.CARD_IMAGES) return err('image bucket not bound', 500);
  if (!key.startsWith('inventory/')) return err('not found', 404);
  const obj = await env.CARD_IMAGES.get(key);
  if (!obj) return err('image not found', 404);
  return new Response(obj.body, {
    headers: {
      'Content-Type': obj.httpMetadata?.contentType || 'image/jpeg',
      // The key never points at different bytes, so cache it hard — that is
      // what keeps a storefront fast without paying R2 for every view.
      'Cache-Control': 'public, max-age=31536000, immutable',
      ...CORS,
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';

    if (request.method === 'OPTIONS') return new Response(null, { headers: CORS });

    if (path === '/api/health') {
      const sql = getSql(env);
      try {
        const [row] = await sql`select current_database() as db, now() as at`;
        return json({ ok: true, service: 'dfs-cards-api', db: row.db, at: row.at,
                      tables: ALLOWED_TABLES.size, images: !!env.CARD_IMAGES });
      } catch (e: any) {
        return json({ ok: false, error: String(e?.message || e).slice(0, 200) }, 500);
      } finally {
        await sql.end({ timeout: 5 }).catch(() => {});
      }
    }

    // Browser-fetched, cannot carry a header — see `authed` above.
    const img = path.match(/^\/api\/inventory\/img\/(.+)$/);
    if (img && request.method === 'GET') return serveImage(env, decodeURIComponent(img[1]));

    if (!authed(request, env)) {
      return err(env.API_KEY
        ? 'unauthorized'
        : 'API_KEY not configured on this Worker — run: npx wrangler secret put API_KEY',
        env.API_KEY ? 401 : 503);
    }

    if (path === '/api/inventory/mirror' && request.method === 'POST') return mirror(request, env);

    if (path === '/api/tenants/delete' && request.method === 'POST')
      return tenantDelete(request, env);

    if (path === '/api/tenants/drift') return tenantDrift(request, env, false);
    if (path === '/api/tenants/migrate' && request.method === 'POST')
      return tenantDrift(request, env, true);

    const db = path.match(/^\/api\/db\/([a-z_]+)(?:\/(.+))?$/);
    if (db) return handleDb(request, env, db[1], db[2] || null);

    return err(`no route: ${request.method} ${path}`, 404);
  },
};
