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
import { SCANNER_HTML } from './scanner.gen';
import { buildTitle, NICKNAMES, readTitle, teamIn } from './titles';
import { identifyCard, titleFrom, VISION_MODEL } from './hopper';
import {
  ebayAccessToken, ebayCall, ebayConsentUrl, ebayEndOffer, ebayExchangeCode,
  ebayOrders, ebayRevisePrice, ebayWhy, type EbayEnv,
} from './ebay';

export interface Env {
  DATABASE_URL: string;
  API_KEY?: string;
  SCAN_KEY?: string;
  CARDHEDGER_KEY?: string;
  ANTHROPIC_API_KEY?: string;
  AI?: { run: (model: string, input: any) => Promise<any> };
  EBAY_APP_ID?: string;
  EBAY_CERT_ID?: string;
  EBAY_RU_NAME?: string;
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
  'access_codes', 'pricing_usage', 'support_tickets', 'price_approvals',
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
                               'support_tickets', 'price_approvals']);
// Same list for SQL: a shared table lives only in public and must never be
// copied into a tenant schema by the drift repair.
const SHARED_LIST = [...SHARED_TABLES, 'support_log'];

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
  'Access-Control-Allow-Headers':
    'Content-Type, X-API-Key, Authorization, X-DFS-Key, X-DFS-Tenant, X-DFS-Scan',
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
  let offset = 0;

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
    // Paging. Without this, `offset` falls through to the filter branch
    // below and becomes WHERE "offset" = 0 — a column that does not exist.
    if (key === 'offset') {
      const n = parseInt(value, 10);
      if (n > 0) offset = n;
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
    params, orderSql, limit, offset,
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
    if (table === 'support_tickets' || table === 'price_approvals') {
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
      const { whereSql, params, orderSql, limit, offset } = parseFilters(url);
      const rows = await sql.unsafe(
        `SELECT * FROM "${schema}"."${table}" ${whereSql} ${orderSql} LIMIT ${limit || 500}${offset ? " OFFSET " + offset : ""}`.trim(),
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

/**
 * Everything the app needs to draw its first screen, in one trip.
 *
 * Sign-in was making six separate calls — who am I, am I in the owner's
 * workspace, do my prices need approval, how many tickets, how many price
 * approvals, and a schema drift check — each a round trip to Neon at roughly
 * a second. Nearly twelve seconds of staring at nothing before the first
 * paint. They are all small questions against the same connection, so they
 * are answered together.
 *
 * Drift is deliberately NOT here. It is the slowest of them and it only
 * changes when someone ships DDL, so it belongs behind the Admin panel
 * rather than in front of every sign-in.
 */
async function whoAmI(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const code = (request.headers.get('X-DFS-Tenant') || '').trim();
    if (!code) return err('X-DFS-Tenant header required', 400);

    const [who] = await sql`
      select t.slug, t.schema_name, t.active as t_active,
             c.active as c_active, c.expires_at, c.name,
             coalesce(c.needs_approval, false) as needs_approval,
             c.daily_limit
        from access_codes c
        join tenants t on t.id = c.tenant_id
       where c.code = ${code} limit 1`;
    if (!who) return err('unknown tenant', 403);
    if (!who.c_active) return err('access suspended', 403);
    if (!who.t_active) return err('tenant suspended', 403);
    if (who.expires_at && new Date(who.expires_at) < new Date())
      return err('access expired', 403);

    const owner = who.schema_name === 'public';
    const [tickets] = await sql`
      select count(*)::int as n from support_tickets
       where status = 'open' ${owner ? sql`` : sql`and tenant_slug = ${who.slug}`}`;
    const [approvals] = await sql`
      select count(*)::int as n from price_approvals
       where status = 'pending' ${owner ? sql`` : sql`and tenant_slug = ${who.slug}`}`;

    return json({
      slug: who.slug, schema: who.schema_name, name: who.name,
      is_owner_workspace: owner,
      needs_approval: who.needs_approval,
      daily_limit: who.daily_limit,
      open_tickets: tickets.n, pending_approvals: approvals.n,
    });
  } catch (e: any) {
    return err(`me: ${String(e?.message || e).slice(0, 200)}`, 500);
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
    const schemas = ['public', ...tenants.map((t: any) => t.schema_name)
      .filter((s: string) => IDENT_OK.test(s))];

    /**
     * One query for every column in every schema, diffed here.
     *
     * This used to ask the catalog per tenant per table — around 90 round
     * trips on a small account — and took 6.9 seconds, every one of them in
     * front of the owner at login. The catalog is small; fetching all of it
     * once and comparing in memory is the same answer in a single trip.
     */
    const cols = await sql`
      select n.nspname as schema, c.relname as tbl, a.attname as col,
             format_type(a.atttypid, a.atttypmod) as typ
        from pg_attribute a
        join pg_class c on c.oid = a.attrelid
        join pg_namespace n on n.oid = c.relnamespace
       where n.nspname = any(${schemas})
         and c.relkind = 'r' and a.attnum > 0 and not a.attisdropped
         and c.relname <> all(${SHARED_LIST})`;

    const bySchema: Record<string, Map<string, Map<string, string>>> = {};
    for (const r of cols as any[]) {
      const s = (bySchema[r.schema] ||= new Map());
      (s.get(r.tbl) || s.set(r.tbl, new Map()).get(r.tbl))!.set(r.col, r.typ);
    }
    const want = bySchema['public'] || new Map();

    const report: any[] = [];
    for (const t of tenants) {
      if (!IDENT_OK.test(t.schema_name)) continue;
      const have = bySchema[t.schema_name] || new Map();
      const missingTables: string[] = [];
      const missingCols: any[] = [];
      for (const [name, wcols] of want) {
        if (!IDENT_OK.test(name)) continue;
        const hcols = have.get(name);
        if (!hcols) { missingTables.push(name); continue; }
        for (const [col, typ] of wcols) {
          if (!hcols.has(col) && IDENT_OK.test(col) && TYPE_OK.test(typ))
            missingCols.push({ table: name, column: col, type: typ });
        }
      }

      let applied = 0;
      if (apply && (missingTables.length || missingCols.length)) {
        for (const name of missingTables) {
          await sql.unsafe(`CREATE TABLE "${t.schema_name}"."${name}" ` +
                           `(LIKE public."${name}" INCLUDING ALL)`);
          applied++;
        }
        for (const c of missingCols) {
          // No NOT NULL: an existing row has no value for a new column.
          await sql.unsafe(`ALTER TABLE "${t.schema_name}"."${c.table}" ` +
                           `ADD COLUMN IF NOT EXISTS "${c.column}" ${c.type}`);
          applied++;
        }
      }

      report.push({
        slug: t.slug, schema: t.schema_name,
        missing_tables: missingTables, missing_columns: missingCols,
        behind: missingTables.length + missingCols.length, applied,
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









/**
 * Accepts Meta's community licence for the vision model.
 *
 * Deliberately its own endpoint behind its own button: agreeing to a
 * licence is the account owner's act. Cloudflare records the acceptance
 * when the literal prompt "agree" is sent once.
 */
async function aiAccept(request: Request, env: Env) {
  if (!env.AI) return err('no AI binding on this Worker', 503);
  try {
    const r = await env.AI.run(VISION_MODEL, { prompt: 'agree' });
    const said = String((r as any)?.response ?? '');
    return json({ ok: true, model: VISION_MODEL, said: said.slice(0, 200) });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  }
}

/* ------------------------------------------------------------------ *
 * The Hopper.
 *
 * Photos in, listable cards out. Identify reads one pair at a time so
 * progress is visible and a failure costs one card, not a batch.
 * ------------------------------------------------------------------ */

/** Everything the Hopper holds for a stack, identified or not. */
async function hopperCards(request: Request, env: Env, url: URL) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const stack = (url.searchParams.get('stack') || '').trim();
    const rows = stack
      ? await sql.unsafe(
          `SELECT * FROM "${schema}"."scan_cards" WHERE stack_name = $1 ORDER BY idx`, [stack])
      : await sql.unsafe(
          `SELECT * FROM "${schema}"."scan_cards" ORDER BY updated_at DESC NULLS LAST LIMIT 500`);
    return json({ cards: rows });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

async function hopperIdentify(request: Request, env: Env) {
  if (!env.CARD_IMAGES) return err('image bucket not bound', 500);
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const b = (await request.json()) as any;
    const frontKey = String(b?.front ?? '').trim();
    const backKey = String(b?.back ?? '').trim();
    const stack = String(b?.stack ?? '').trim();
    const idx = Number(b?.idx) || 0;
    if (!frontKey.startsWith('scan/')) return err('a front photo is required', 400);

    const fo = await env.CARD_IMAGES.get(frontKey);
    if (!fo) return err('that photo is no longer in the bucket', 404);
    const front = await fo.arrayBuffer();
    let back: ArrayBuffer | null = null;
    if (backKey.startsWith('scan/')) {
      const bo = await env.CARD_IMAGES.get(backKey);
      if (bo) back = await bo.arrayBuffer();
    }

    const card = await identifyCard(env, front, back,
      fo.httpMetadata?.contentType || 'image/jpeg');
    const title = titleFrom(card);

    // Price it while we are here: a card with no price is not listable,
    // and the comp lookup is one more call on a card already in hand.
    let fmv: number | null = null;
    if (env.CARDHEDGER_KEY && card.confidence >= 0.5 && title) {
      const res = await chPost(env, '/v1/cards/card-match',
        { query: title, page: 1, page_size: 3 });
      const m = res?.match;
      if (m && Number(m.confidence ?? 0) >= 0.7) {
        const want = card.grader && card.grade
          ? `${card.grader.toUpperCase()} ${card.grade}` : 'Raw';
        fmv = chPickPrice(m, want);
      }
    }

    // One stack row per name, so a re-scan does not pile up duplicates.
    const [st] = await sql.unsafe(
      `INSERT INTO "${schema}"."scan_stacks" (name) VALUES ($1)
       ON CONFLICT DO NOTHING RETURNING id`, [stack || 'loose']);
    const stackId = st?.id ?? (await sql.unsafe(
      `SELECT id FROM "${schema}"."scan_stacks" WHERE name = $1 LIMIT 1`,
      [stack || 'loose']))[0]?.id;

    const [saved] = await sql.unsafe(
      `INSERT INTO "${schema}"."scan_cards"
         (stack_id, idx, stack_name, r2_front, r2_back, player, title, year,
          set_name, card_number, parallel, serial, grader, grade, team, sport,
          is_rookie, is_auto, confidence, unsure, fmv, price, status, updated_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$21,
               $22, now())
       ON CONFLICT (r2_front) DO UPDATE SET
         player=excluded.player, title=excluded.title, year=excluded.year,
         set_name=excluded.set_name, card_number=excluded.card_number,
         parallel=excluded.parallel, serial=excluded.serial, grader=excluded.grader,
         grade=excluded.grade, team=excluded.team, sport=excluded.sport,
         is_rookie=excluded.is_rookie, is_auto=excluded.is_auto,
         confidence=excluded.confidence, unsure=excluded.unsure,
         fmv=excluded.fmv, status=excluded.status, updated_at=now()
       RETURNING *`,
      [stackId, idx, stack, frontKey, backKey || null, card.player, title, card.year,
       card.set_name, card.card_number, card.parallel, card.serial, card.grader,
       card.grade, card.team, card.sport, card.is_rookie, card.is_auto,
       card.confidence, card.unsure.join(', '), fmv,
       card.confidence >= 0.8 && card.unsure.length === 0 ? 'identified' : 'needs_review']);

    return json({ ok: true, card: saved });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/** Review edits — whatever a person corrects wins over what was read. */
async function hopperSave(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const b = (await request.json()) as any;
    const id = Number(b?.id);
    if (!Number.isFinite(id)) return err('which card?', 400);

    const ok = ['player','title','year','set_name','card_number','parallel','serial',
                'grader','grade','team','sport','price','sku','status','notes'];
    const sets: string[] = [];
    const vals: any[] = [];
    for (const k of ok) {
      if (k in b) { vals.push(b[k] === '' ? null : b[k]); sets.push(`"${k}" = $${vals.length}`); }
    }
    if (!sets.length) return err('nothing to change', 400);
    vals.push(id);
    const [row] = await sql.unsafe(
      `UPDATE "${schema}"."scan_cards" SET ${sets.join(', ')}, updated_at = now()
        WHERE id = $${vals.length} RETURNING *`, vals);
    return json({ ok: true, card: row });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/* ------------------------------------------------------------------ *
 * Title suggestions.
 *
 * The player comes from the catalogue, never from reading the title —
 * that is guesswork, and the catalogue knows. A card the matcher is not
 * confident about is reformatted from what the title already says and
 * marked low confidence, rather than rebuilt around a name that might
 * belong to someone else.
 *
 * Nothing is written. This proposes; the screen decides.
 * ------------------------------------------------------------------ */
async function titlesSuggest(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const b = (await request.json()) as any;
    const ids: string[] = (Array.isArray(b?.item_numbers) ? b.item_numbers : [])
      .filter((x: any) => typeof x === 'string' && x).slice(0, 25);
    if (!ids.length) return err('no item numbers', 400);

    const rows = await sql.unsafe(
      `SELECT item_number, sku, title, grader, grade, sport
         FROM "${schema}"."listings"
        WHERE item_number = ANY($1::text[]) AND ended_at IS NULL`, [ids]);

    const out: any[] = [];
    for (let i = 0; i < rows.length; i++) {
      const row: any = rows[i];
      const before = String(row.title ?? '');
      let player = '', confidence = 0;

      if (env.CARDHEDGER_KEY) {
        if (i > 0) await sleep(850);                 // the same 1.2/sec limit
        const res = await chPost(env, '/v1/cards/card-match',
          { query: before, page: 1, page_size: 3 });
        const m = res?.match;
        confidence = Number(m?.confidence ?? 0);
        if (m && confidence >= 0.7) player = String(m.player ?? '').trim();
      }

      const parts = readTitle(before, player);
      // A grade on the card beats one read out of the title.
      const g = [String(row.grader ?? ''), String(row.grade ?? '')]
        .map((x) => x.trim()).filter((x) => x && x.toLowerCase() !== 'nan');
      if (g.length === 2) parts.grade = `${g[0].toUpperCase()} ${g[1]}`;

      const team = parts.team || teamIn(before, NICKNAMES);
      const built = buildTitle(parts, team);

      out.push({
        item_number: row.item_number, sku: row.sku, before,
        after: built.title,
        changed: built.title !== before,
        length: built.title.length,
        trimmed: built.trimmed,
        confidence,
        player: parts.name || null,
        needs_team: !team,
        // Said plainly so the screen can show it beside the row.
        note: !player && confidence < 0.7
          ? 'catalogue was not confident — reformatted from what the title already said'
          : !team ? 'no team in the title; a team cannot be guessed safely' : '',
      });
    }
    return json({ ok: true, suggestions: out });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/* ------------------------------------------------------------------ *
 * Lots — what a box of cards cost, and what it has made back.
 *
 * This is the piece that turns revenue into profit. Everything else can
 * say what came in; only a lot cost can say whether it was worth buying.
 *
 * Cards join a lot by SKU prefix, which is how he already names them,
 * so no card has to be assigned by hand. Sales join through the item
 * number — old rows carry a trailing '.0' from a pandas import, hence
 * the strip.
 * ------------------------------------------------------------------ */
async function lots(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const L = `"${schema}"."listings"`;
    const S = `"${schema}"."sales_records"`;
    const P = `"${schema}"."purchase_lots"`;

    const rows = await sql.unsafe(`
      WITH lot AS (
        SELECT id, lot_prefix, source, purchase_date, is_break, breaker, product,
               coalesce(total_cost,0) + coalesce(ship_cost,0) AS cost,
               card_count
          FROM ${P}
      ),
      held AS (
        SELECT l.lot_prefix,
               count(*) FILTER (WHERE c.ended_at IS NULL)::int AS still_listed,
               coalesce(sum(c.current_price) FILTER (WHERE c.ended_at IS NULL),0) AS listed_value,
               count(*) FILTER (WHERE c.ended_at IS NOT NULL)::int AS gone
          FROM lot l JOIN ${L} c ON c.sku ILIKE l.lot_prefix || '%'
         GROUP BY 1
      ),
      sold AS (
        SELECT l.lot_prefix,
               count(*)::int AS sales,
               coalesce(sum(s.gross_revenue),0) AS revenue,
               coalesce(sum(s.platform_fee),0)  AS fees
          FROM lot l JOIN ${S} s ON s.sku ILIKE l.lot_prefix || '%'
         GROUP BY 1
      )
      SELECT lot.*,
             coalesce(held.still_listed,0)  AS still_listed,
             coalesce(held.listed_value,0)  AS listed_value,
             coalesce(held.gone,0)          AS gone,
             coalesce(sold.sales,0)         AS sales,
             coalesce(sold.revenue,0)       AS revenue,
             coalesce(sold.fees,0)          AS fees
        FROM lot
        LEFT JOIN held ON held.lot_prefix = lot.lot_prefix
        LEFT JOIN sold ON sold.lot_prefix = lot.lot_prefix
       ORDER BY lot.purchase_date DESC NULLS LAST, lot.id DESC`);

    return json({ lots: rows });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}


/**
 * Spread each lot's cost over the cards that carry its prefix.
 *
 * Deliberately divided by the cards actually found, not the card_count
 * typed into the lot — that field is 0 on most rows, and dividing by it
 * would either fail or invent a cost. Recomputed on demand rather than
 * stored once, so correcting a lot's price corrects every card under it.
 *
 * This is an even split. A $1,200 box does not really hold twelve $100
 * cards, but for "did this lot pay for itself" and "never list under
 * cost" an even split is the honest approximation, and it is the one a
 * spreadsheet would make too.
 */
async function costSpread(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const done = await sql.unsafe(`
      WITH spread AS (
        SELECT p.lot_prefix,
               (coalesce(p.total_cost,0) + coalesce(p.ship_cost,0))
                 / nullif(count(l.item_number),0) AS per_card
          FROM "${schema}"."purchase_lots" p
          JOIN "${schema}"."listings" l ON l.sku ILIKE p.lot_prefix || '%'
         WHERE coalesce(p.total_cost,0) + coalesce(p.ship_cost,0) > 0
         GROUP BY 1, p.total_cost, p.ship_cost
      )
      UPDATE "${schema}"."listings" c
         SET cost_basis = round(s.per_card, 2)
        FROM spread s
       WHERE c.sku ILIKE s.lot_prefix || '%'
         AND s.per_card IS NOT NULL
      RETURNING c.item_number`);
    const [tot] = await sql.unsafe(
      `SELECT count(*) FILTER (WHERE cost_basis IS NOT NULL)::int AS with_cost,
              count(*)::int AS all_cards
         FROM "${schema}"."listings" WHERE ended_at IS NULL`);
    return json({ ok: true, priced: done.length,
                  live_with_cost: tot.with_cost, live_total: tot.all_cards });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/** Create or update a lot — what it cost is the only number that matters. */
async function lotSave(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const b = (await request.json()) as any;
    const prefix = String(b?.lot_prefix ?? '').trim().slice(0, 80);
    if (!prefix) return err('a lot needs a SKU prefix', 400);
    const cost = Number(b?.total_cost);
    if (!Number.isFinite(cost) || cost < 0) return err('cost must be a number', 400);

    await sql.unsafe(
      `INSERT INTO "${schema}"."purchase_lots"
         (lot_prefix, source, purchase_date, total_cost, ship_cost, notes, card_count)
       VALUES ($1,$2,nullif($3,'')::date,$4,$5,$6,$7)
       ON CONFLICT (lot_prefix) DO UPDATE SET
         source = excluded.source,
         purchase_date = coalesce(excluded.purchase_date, "purchase_lots".purchase_date),
         total_cost = excluded.total_cost,
         ship_cost = excluded.ship_cost,
         notes = excluded.notes`,
      [prefix, String(b?.source ?? '').slice(0, 80), String(b?.purchase_date ?? ''),
       cost, Number(b?.ship_cost) || 0, String(b?.notes ?? '').slice(0, 500),
       Number(b?.card_count) || 0]);
    return json({ ok: true, lot_prefix: prefix });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/* ------------------------------------------------------------------ *
 * Pages eBay's app registration insists on.
 *
 * The redirect form will not save without a privacy policy URL and a
 * declined URL, so both are served here rather than leaving him to find
 * somewhere to host them.
 * ------------------------------------------------------------------ */
const PAGE = (title: string, inner: string) => new Response(
  `<!doctype html><html lang=en><meta charset=utf-8>
   <meta name=viewport content="width=device-width,initial-scale=1">
   <title>${title} — DFS Cards</title>
   <style>
     body{background:#0f1117;color:#fafafa;margin:0;padding:40px 22px;
          font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
     main{max-width:680px;margin:0 auto}
     h1{font-weight:600;letter-spacing:-.3px;margin:0 0 6px}
     h2{font-size:17px;font-weight:650;margin:28px 0 6px}
     p,li{color:#c8cfdd} li{margin-bottom:6px}
     .m{color:#9aa3bd;font-size:14px}
     a{color:#5a8cff}
   </style><main>${inner}</main>`,
  { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'public, max-age=3600' } });

function privacyPage() {
  return PAGE('Privacy', `
    <h1>Privacy Policy</h1>
    <p class=m>CardPulse — DFS Cards LLC, Scottsdale, Arizona. Updated 17 October 2026.</p>
    <p>CardPulse is private inventory software used by DFS Cards LLC to run its own
       trading-card business. It is not offered to the public and has no other users.</p>
    <h2>What it stores</h2>
    <ul>
      <li>Our own card listings, prices, storage locations and photographs.</li>
      <li>Our own sales records: order number, date, item, quantity and amount.</li>
      <li>An access token for our own eBay seller account, used only to manage our own listings and read our own orders.</li>
    </ul>
    <h2>What it does not store</h2>
    <ul>
      <li><b>No buyer personal data.</b> Buyer names, email addresses, postal addresses and
          phone numbers appear in eBay's reports and are deliberately discarded on import.</li>
      <li>No payment details. We never see or hold card numbers.</li>
      <li>No data about any other eBay user.</li>
    </ul>
    <h2>eBay account deletion notifications</h2>
    <p>Because CardPulse holds no eBay user data, there is nothing for us to delete on
       request, and we are opted out of marketplace account-deletion notifications.</p>
    <h2>Sharing and keeping</h2>
    <p>Nothing is sold, shared or sent to advertisers or analytics services. Data sits in a
       private database and a private file store, reachable only with our own credentials, and
       is kept while we are trading so the books and the inventory history stay intact.</p>
    <h2>Contact</h2>
    <p>dfscards25@gmail.com</p>`);
}

function declinedPage() {
  return PAGE('Not connected', `
    <h1>eBay was not connected</h1>
    <p>You chose not to give CardPulse access, or eBay stopped partway. Nothing changed, and
       no permission was granted.</p>
    <p class=m>To try again, open CardPulse → Settings → Connect eBay. You can close this tab.</p>`);
}

/* ------------------------------------------------------------------ *
 * Dashboard — the one screen that answers "how is it going".
 *
 * Computed in the database because it is five aggregates over 7,000
 * listings and 2,500 sales; shipping that to the browser to add up would
 * be slower and no more honest.
 *
 * Every figure here comes back with what it is made of, so the screen
 * can print the sentence underneath instead of asking him to trust it.
 * ------------------------------------------------------------------ */
async function dashboard(request: Request, env: Env, url: URL) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const year = parseInt(url.searchParams.get('year') || String(new Date().getFullYear()), 10);
    const L = `"${schema}"."listings"`;
    const S = `"${schema}"."sales_records"`;

    const [inv] = await sql.unsafe(`
      SELECT count(*) FILTER (WHERE ended_at IS NULL)::int              AS live,
             count(*) FILTER (WHERE ended_at IS NOT NULL)::int          AS ended,
             coalesce(sum(current_price) FILTER (WHERE ended_at IS NULL),0) AS listed_value,
             count(*) FILTER (WHERE ended_at IS NULL AND comp_avg IS NOT NULL)::int AS with_comp,
             count(*) FILTER (WHERE ended_at IS NULL AND cost_basis IS NOT NULL)::int AS with_cost,
             count(*) FILTER (WHERE ended_at IS NULL AND sport = 'Unknown')::int AS no_sport,
             coalesce(sum(current_price) FILTER (
               WHERE ended_at IS NULL AND start_date < now() - interval '90 days'),0) AS stale_value,
             count(*) FILTER (
               WHERE ended_at IS NULL AND start_date < now() - interval '90 days')::int AS stale_n,
             coalesce(sum(watchers) FILTER (WHERE ended_at IS NULL),0)::int AS watchers
        FROM ${L}`);

    const [sale] = await sql.unsafe(`
      SELECT count(*)::int AS lines,
             count(DISTINCT order_id)::int AS orders,
             coalesce(sum(gross_revenue),0) AS gross,
             coalesce(sum(platform_fee),0)  AS fees,
             count(*) FILTER (WHERE platform_fee > 0)::int AS with_fee
        FROM ${S} WHERE extract(year from sale_date) = $1`, [year]);

    const byMonth = await sql.unsafe(`
      SELECT to_char(sale_date,'MM') AS m,
             coalesce(sum(gross_revenue),0) AS gross,
             coalesce(sum(platform_fee),0)  AS fees,
             count(*)::int AS n
        FROM ${S} WHERE extract(year from sale_date) = $1
       GROUP BY 1 ORDER BY 1`, [year]);

    const byChannel = await sql.unsafe(`
      SELECT source, count(*)::int AS n, coalesce(sum(gross_revenue),0) AS gross
        FROM ${S} WHERE extract(year from sale_date) = $1
       GROUP BY 1 ORDER BY 3 DESC`, [year]);

    // How long a card actually sits before it sells. Joined on the item
    // number (old rows carry a trailing '.0' from a pandas import), and
    // only where the sale came after the listing started — anything else
    // is a relist and would read as a negative.
    const [speed] = await sql.unsafe(`
      SELECT count(*)::int AS n,
             percentile_disc(0.5) WITHIN GROUP (ORDER BY (s.sale_date - l.start_date::date)) AS median_days
        FROM ${S} s JOIN ${L} l
          ON regexp_replace(s.item_number,'\\.0$','') = l.item_number
       WHERE l.start_date IS NOT NULL AND s.sale_date >= l.start_date::date`);

    const topBoxes = await sql.unsafe(`
      SELECT split_part(split_part(sku,'_',1),'-',1) AS box,
             count(*)::int AS n, coalesce(sum(current_price),0) AS value
        FROM ${L} WHERE ended_at IS NULL AND sku <> '' AND sku IS NOT NULL
       GROUP BY 1 ORDER BY 3 DESC LIMIT 6`);

    return json({ year, inventory: inv, sales: sale, by_month: byMonth,
                  by_channel: byChannel, speed, top_boxes: topBoxes });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/* ------------------------------------------------------------------ *
 * eBay routes.
 *
 * Connecting is a browser redirect, so the consent link is minted here
 * and eBay sends the person back to /api/ebay/callback with a one-time
 * code. Everything after that is server to server.
 * ------------------------------------------------------------------ */
async function ebayStatus(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const configured = !!(env.EBAY_APP_ID && env.EBAY_CERT_ID && env.EBAY_RU_NAME);
    const [row] = await sql.unsafe(
      `SELECT connected_at, access_expires FROM "${schema}"."marketplace_tokens"
        WHERE marketplace = 'ebay'`);
    const [log] = await sql.unsafe(
      `SELECT count(*)::int AS n, count(*) FILTER (WHERE NOT ok)::int AS failed
         FROM "${schema}"."marketplace_log"
        WHERE marketplace='ebay' AND at > now() - interval '7 days'`);
    return json({
      configured,
      connected: !!row,
      connected_at: row?.connected_at ?? null,
      recent_calls: log?.n ?? 0,
      recent_failures: log?.failed ?? 0,
      // Said plainly so the screen can tell him what to do next.
      next_step: !configured
        ? 'Register the app at developer.ebay.com, then set EBAY_APP_ID, EBAY_CERT_ID and EBAY_RU_NAME on the Worker'
        : !row ? 'Press Connect eBay' : null,
    });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

function ebayConnect(request: Request, env: Env, url: URL) {
  if (!(env.EBAY_APP_ID && env.EBAY_CERT_ID && env.EBAY_RU_NAME))
    return err('eBay app keys are not set on the Worker yet', 503);
  const code = (request.headers.get('X-DFS-Tenant') || '').trim();
  // The tenant code rides in `state` so the callback — which eBay calls
  // with no headers of ours — knows whose account came back.
  return json({ url: ebayConsentUrl(env as EbayEnv, code) });
}

async function ebayCallback(request: Request, env: Env, url: URL) {
  const code = url.searchParams.get('code');
  const state = (url.searchParams.get('state') || '').trim();
  const page = (msg: string, ok: boolean) => new Response(
    `<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
     <body style="background:#0f1117;color:#fafafa;font:16px -apple-system,sans-serif;
                  display:grid;place-items:center;height:100vh;margin:0;text-align:center;padding:24px">
     <div><h1 style="color:${ok ? '#2e9e63' : '#e0505f'};font-weight:600">${msg}</h1>
     <p style="color:#9aa3bd">You can close this tab and go back to CardPulse.</p></div>`,
    { status: ok ? 200 : 400, headers: { 'Content-Type': 'text/html; charset=utf-8' } });

  if (!code) return page('eBay did not send a code back', false);
  if (!state) return page('That link is missing its account', false);

  const sql = getSql(env);
  try {
    const fake = new Request(request.url, { headers: { 'X-DFS-Tenant': state } });
    const schema = await tenantSchema(fake, sql);
    const tok = await ebayExchangeCode(env as EbayEnv, code);
    await sql.unsafe(
      `INSERT INTO "${schema}"."marketplace_tokens"
         (marketplace, refresh_token, access_token, access_expires, scopes)
       VALUES ('ebay', $1, $2, $3, $4)
       ON CONFLICT (marketplace) DO UPDATE SET
         refresh_token = excluded.refresh_token,
         access_token = excluded.access_token,
         access_expires = excluded.access_expires,
         updated_at = now()`,
      [tok.refresh_token, tok.access_token,
       new Date(Date.now() + (tok.expires_in ?? 7200) * 1000).toISOString(), 'sell']);
    return page('eBay connected', true);
  } catch (e: any) {
    return page(`eBay refused: ${String(e?.message || e).slice(0, 160)}`, false);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/** Price changes straight onto live listings — no CSV, no upload. */
async function ebayPush(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const body = (await request.json()) as any;
    const changes: { item_number: string; price: number }[] =
      (Array.isArray(body?.changes) ? body.changes : [])
        .filter((c: any) => c?.item_number && Number.isFinite(+c.price) && +c.price > 0)
        .slice(0, 100);
    if (!changes.length) return err('no changes', 400);

    const token = await ebayAccessToken(env as EbayEnv, sql, schema);
    const done: any[] = [];
    for (const c of changes) {
      // The offer id is what the Inventory API edits; the item number is
      // what a seller knows. Look one up from the other.
      const look = await ebayCall(token,
        `/sell/inventory/v1/offer?sku=${encodeURIComponent(c.item_number)}`);
      const offerId = look.body?.offers?.[0]?.offerId;
      let ok = false, detail = '';
      if (!offerId) {
        detail = 'no offer on eBay for that SKU — it may have been listed outside CardPulse';
      } else {
        const r = await ebayRevisePrice(token, offerId, c.price);
        ok = r.ok; detail = ok ? `now $${c.price.toFixed(2)}` : ebayWhy(r.body);
      }
      done.push({ item_number: c.item_number, ok, detail });
      await sql.unsafe(
        `INSERT INTO "${schema}"."marketplace_log"
           (marketplace, action, item_number, ok, detail)
         VALUES ('ebay','revise_price',$1,$2,$3)`, [c.item_number, ok, detail]);
    }
    return json({ ok: true, changed: done.filter((d) => d.ok).length,
                  failed: done.filter((d) => !d.ok).length, results: done });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/** Orders, pulled instead of downloaded. */
async function ebayPullOrders(request: Request, env: Env, url: URL) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const days = Math.min(90, Math.max(1, parseInt(url.searchParams.get('days') || '30', 10)));
    const since = new Date(Date.now() - days * 86400_000).toISOString();
    const token = await ebayAccessToken(env as EbayEnv, sql, schema);
    const r = await ebayOrders(token, since);
    if (!r.ok) return err(ebayWhy(r.body), r.status);

    const rows: any[] = [];
    for (const o of (r.body?.orders ?? [])) {
      for (const li of (o.lineItems ?? [])) {
        rows.push({
          source: 'ebay', order_id: o.orderId,
          sale_date: (o.creationDate || '').slice(0, 10),
          title: String(li.title ?? '').slice(0, 400),
          item_number: String(li.legacyItemId ?? ''),
          sku: String(li.sku ?? '').slice(0, 120),
          quantity: Number(li.quantity ?? 1),
          sale_price: Number(li.lineItemCost?.value ?? 0),
          shipping_collected: Number(li.deliveryCost?.shippingCost?.value ?? 0),
          // Fees are NOT on an order — they live in the Finances API
          // (getTransactions). Left at zero rather than guessed; Money
          // already says on screen where fees are missing.
          platform_fee: 0,
          dedup_key: `ebay|${o.orderId}|${li.lineItemId}`,
        });
      }
    }
    if (rows.length) {
      await sql.unsafe(
        `INSERT INTO "${schema}"."sales_records"
           (source, order_id, sale_date, title, item_number, sku, quantity,
            sale_price, shipping_collected, gross_revenue, platform_fee,
            net_proceeds, status, dedup_key)
         SELECT source, order_id, sale_date::date, title, item_number, sku, quantity,
                sale_price, shipping_collected, sale_price + shipping_collected,
                platform_fee, 0, 'sold', dedup_key
           FROM jsonb_to_recordset($1::text::jsonb) AS x(
                source text, order_id text, sale_date text, title text,
                item_number text, sku text, quantity int, sale_price numeric,
                shipping_collected numeric, platform_fee numeric, dedup_key text)
         ON CONFLICT (dedup_key) DO NOTHING`, [JSON.stringify(rows)]);
    }
    return json({ ok: true, days, order_lines: rows.length });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally { await sql.end({ timeout: 5 }).catch(() => {}); }
}

/* ------------------------------------------------------------------ *
 * Comps from CardHedger.
 *
 * The whole pricing engine reads comp_avg, and until this runs that
 * column is empty — which is why Reprice priced nothing on day one.
 *
 * CardHedger is rate limited and metered, so this takes a batch of cards
 * the person actually picked rather than walking the whole table, runs
 * them a few at a time, and writes what it finds. A card it cannot match
 * is left with no comp rather than a guessed one: an empty cell is
 * honest, a wrong comp quietly reprices a card to the wrong number.
 * ------------------------------------------------------------------ */
const CH_BASE = 'https://api.cardhedger.com';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * CardHedger allows about 1.2 requests a second. Going faster does not
 * fail loudly — it returns refusals that look exactly like "no such
 * card", which is how a throttled run reads as a catalogue full of
 * unmatched cards. One retry, then give up honestly.
 */
async function chPost(env: Env, path: string, body: unknown, tries = 2): Promise<any> {
  if (!env.CARDHEDGER_KEY) return null;
  for (let attempt = 0; attempt < tries; attempt++) {
    try {
      const r = await fetch(CH_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': env.CARDHEDGER_KEY },
        body: JSON.stringify(body),
      });
      if (r.ok) return await r.json();
      if (r.status === 429 || r.status >= 500) { await sleep(1200); continue; }
      return null;                       // a real refusal, not a wobble
    } catch { await sleep(600); }
  }
  return null;
}

/**
 * Which of CardHedger's prices applies to this card.
 *
 * card-match already returns a price per grade, so one call answers the
 * whole question — the separate FMV call this used to make was a second
 * round trip that mostly came back empty.
 */
function chWantedGrade(row: any): string {
  const g = String(row.grade ?? '').trim();
  const grader = String(row.grader ?? '').trim();
  const bad = (x: string) => !x || x.toLowerCase() === 'nan' || x.toLowerCase() === 'none';
  if (bad(g) || bad(grader)) return 'Raw';
  return `${grader.toUpperCase()} ${g}`;
}

function chPickPrice(match: any, want: string): number | null {
  const list: any[] = Array.isArray(match?.prices) ? match.prices : [];
  if (!list.length) return null;
  const num = (p: any) => { const n = Number(p?.price); return Number.isFinite(n) && n > 0 ? n : null; };
  const exact = list.find((p) => String(p?.grade ?? '').toUpperCase() === want.toUpperCase());
  if (exact && num(exact) !== null) return num(exact);
  // A graded card with no price at its own grade is NOT worth the raw
  // price — leave it empty rather than pricing a PSA 10 off a raw comp.
  if (want !== 'Raw') return null;
  const raw = list.find((p) => String(p?.grade ?? '').toLowerCase() === 'raw');
  return raw ? num(raw) : null;
}

async function compsFetch(request: Request, env: Env) {
  if (!env.CARDHEDGER_KEY)
    return err('CARDHEDGER_KEY not set — run: npx wrangler secret put CARDHEDGER_KEY', 503);
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const body = (await request.json()) as any;
    const ids: string[] = (Array.isArray(body?.item_numbers) ? body.item_numbers : [])
      .filter((x: any) => typeof x === 'string' && x).slice(0, 25);
    if (!ids.length) return err('no item numbers', 400);

    const rows = await sql.unsafe(
      `SELECT item_number, title, grader, grade FROM "${schema}"."listings"
        WHERE item_number = ANY($1::text[]) AND ended_at IS NULL`, [ids]);

    const found: { item_number: string; comp: number }[] = [];
    // CardHedger names the sport on every match. Cheaper and more
    // reliable than another regex over the title, and it rides along on
    // a call already being made.
    const sports: { item_number: string; sport: string }[] = [];
    const missed: string[] = [];

    // One at a time with a gap, because the limit is per second and the
    // browser loops over batches — progress stays visible either way.
    for (let i = 0; i < rows.length; i++) {
      if (i > 0) await sleep(850);
      await (async (row: any) => {
        const title = String(row.title ?? '').trim();
        if (!title) { missed.push(row.item_number); return; }
        const res = await chPost(env, '/v1/cards/card-match',
          { query: title, page: 1, page_size: 5 });
        const match = res?.match ?? res?.cards?.[0] ?? null;
        // A weak match is worse than none: it reprices the wrong card.
        if (!match || Number(match.confidence ?? 0) < 0.7) { missed.push(row.item_number); return; }
        const cat = String(match.category ?? '').trim();
        if (cat && (!row.sport || row.sport === 'Unknown' || row.sport === ''))
          sports.push({ item_number: row.item_number, sport: cat.slice(0, 40) });
        const price = chPickPrice(match, chWantedGrade(row));
        if (price !== null) found.push({ item_number: row.item_number, comp: price });
        else missed.push(row.item_number);
      })(rows[i]);
    }

    if (found.length) {
      await sql.unsafe(
        `UPDATE "${schema}"."listings" AS l
            SET comp_avg = x.comp, last_priced_at = now()
           FROM jsonb_to_recordset($1::text::jsonb)
                AS x(item_number text, comp numeric)
          WHERE l.item_number = x.item_number`,
        [JSON.stringify(found)]);
    }
    if (sports.length) {
      await sql.unsafe(
        `UPDATE "${schema}"."listings" AS l SET sport = x.sport
           FROM jsonb_to_recordset($1::text::jsonb) AS x(item_number text, sport text)
          WHERE l.item_number = x.item_number`,
        [JSON.stringify(sports)]);
    }
    return json({ ok: true, asked: rows.length, found: found.length,
                  missed: missed.length, sports_named: sports.length });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally {
    await sql.end({ timeout: 5 }).catch(() => {});
  }
}

/* ------------------------------------------------------------------ *
 * Refresh listings from the eBay active-listings report.
 *
 * There is no eBay API here and there never will be — the report he
 * downloads by hand IS the sync. So this takes the parsed rows and makes
 * the table match them, in two statements rather than 4,500 round trips.
 *
 * What is NOT here, deliberately: deleting rows that are missing from the
 * report. A card absent from the report has sold or been ended, and that
 * is the single most valuable signal in the whole business — it is what
 * stops a sold card being relisted. The browser works out that difference
 * and shows it; nothing is removed without him looking at it first.
 * ------------------------------------------------------------------ */
async function listingsRefresh(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const body = (await request.json()) as any;
    const rows: any[] = Array.isArray(body?.rows) ? body.rows : [];
    if (!rows.length) return err('no rows', 400);
    if (rows.length > 20000) return err('too many rows in one go', 413);

    // Only the columns the report actually carries. Everything else on the
    // row — cost basis, comps, suggested price — is ours and is left alone.
    const clean = rows
      .filter((r) => r && typeof r.item_number === 'string' && r.item_number)
      .map((r) => ({
        item_number: String(r.item_number).slice(0, 40),
        title: String(r.title ?? '').slice(0, 500),
        sku: String(r.sku ?? '').slice(0, 120),
        current_price: Number.isFinite(+r.current_price) ? +r.current_price : null,
        start_date: r.start_date || null,
        end_date: r.end_date || null,
        watchers: Number.isFinite(+r.watchers) ? Math.trunc(+r.watchers) : 0,
        sold_qty: Number.isFinite(+r.sold_qty) ? Math.trunc(+r.sold_qty) : 0,
        condition: String(r.condition ?? '').slice(0, 60),
        grader: String(r.grader ?? '').slice(0, 60),
        grade: String(r.grade ?? '').slice(0, 30),
        cert_number: String(r.cert_number ?? '').slice(0, 60),
      }));
    if (!clean.length) return err('nothing usable in those rows', 400);

    const before = await sql.unsafe(
      `SELECT count(*)::int AS n FROM "${schema}"."listings"`);

    // One statement. ON CONFLICT so a re-run of the same file is a no-op
    // rather than a duplicate, and so his own columns survive the update.
    await sql.unsafe(
      `INSERT INTO "${schema}"."listings"
         (item_number, title, sku, current_price, start_date, end_date,
          watchers, sold_qty, condition, grader, grade, cert_number,
          updated_at, last_seen_at, ended_at)
       SELECT x.item_number, x.title, x.sku, x.current_price,
              nullif(x.start_date,'')::timestamptz,
              nullif(x.end_date,'')::timestamptz,
              x.watchers, x.sold_qty, x.condition, x.grader, x.grade,
              x.cert_number, now(), now(), NULL
         FROM jsonb_to_recordset($1::text::jsonb) AS x(
              item_number text, title text, sku text, current_price numeric,
              start_date text, end_date text, watchers int, sold_qty int,
              condition text, grader text, grade text, cert_number text)
       ON CONFLICT (item_number) DO UPDATE SET
              title = excluded.title,
              sku = excluded.sku,
              current_price = excluded.current_price,
              start_date = excluded.start_date,
              end_date = excluded.end_date,
              watchers = excluded.watchers,
              sold_qty = excluded.sold_qty,
              condition = excluded.condition,
              grader = excluded.grader,
              grade = excluded.grade,
              cert_number = excluded.cert_number,
              updated_at = now(),
              last_seen_at = now(),
              -- back in the report means it is live again
              ended_at = NULL`,
      [JSON.stringify(clean)]);

    const after = await sql.unsafe(
      `SELECT count(*)::int AS n FROM "${schema}"."listings"`);

    return json({
      ok: true,
      sent: clean.length,
      added: after[0].n - before[0].n,
      updated: clean.length - (after[0].n - before[0].n),
      total: after[0].n,
    });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally {
    await sql.end({ timeout: 5 }).catch(() => {});
  }
}

/**
 * Marks listings gone from eBay as ended. Deliberately NOT a delete: the
 * row is the only record of what a card was listed at when it sold, and
 * that history is what the analysis runs on. Marked rows drop out of the
 * live inventory everywhere, which is what stops a sold card being
 * relisted — the useful half of deleting, without losing anything.
 */
async function listingsRetire(request: Request, env: Env) {
  const sql = getSql(env);
  try {
    const schema = await tenantSchema(request, sql);
    const body = (await request.json()) as any;
    const ids: string[] = (Array.isArray(body?.item_numbers) ? body.item_numbers : [])
      .filter((x: any) => typeof x === 'string' && x).slice(0, 20000);
    if (!ids.length) return err('no item numbers', 400);
    const done = await sql.unsafe(
      `UPDATE "${schema}"."listings" SET ended_at = now()
        WHERE item_number = ANY($1::text[]) AND ended_at IS NULL
        RETURNING item_number`, [ids]);
    return json({ ok: true, removed: done.length, ended: done.length });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 300), 500);
  } finally {
    await sql.end({ timeout: 5 }).catch(() => {});
  }
}

/* ------------------------------------------------------------------ *
 * Sign-in for the web app.
 *
 * Streamlit could hold API_KEY because it runs on a server. The web app at
 * app.dfscards.com is static files in a browser, so it cannot hold anything
 * secret — a key shipped to the browser is a published key. Instead the
 * Worker trades an access code for a short-lived signed token.
 *
 * The token carries the ACCESS CODE, not the resolved tenant, so every
 * request still goes through resolveTenant. That costs one join and buys
 * something worth more: suspending a code takes effect on the next request
 * rather than whenever the token happens to expire. "Suspend all logins"
 * has to mean now.
 *
 * The signing key is derived from API_KEY rather than being a secret of its
 * own — one less thing to rotate, and rotating API_KEY correctly invalidates
 * every session with it.
 * ------------------------------------------------------------------ */
const SESSION_HOURS = 12;

const b64url = (b: ArrayBuffer | Uint8Array) =>
  btoa(String.fromCharCode(...new Uint8Array(b as any)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

async function signingKey(env: Env): Promise<CryptoKey> {
  const seed = new TextEncoder().encode((env.API_KEY || '') + '|dfs-session|v1');
  const raw = await crypto.subtle.digest('SHA-256', seed);
  return crypto.subtle.importKey('raw', raw, { name: 'HMAC', hash: 'SHA-256' },
                                 false, ['sign', 'verify']);
}

async function mintSession(env: Env, code: string): Promise<string> {
  const body = b64url(new TextEncoder().encode(JSON.stringify({
    c: code, exp: Date.now() + SESSION_HOURS * 3600_000,
  })));
  const sig = await crypto.subtle.sign('HMAC', await signingKey(env),
                                       new TextEncoder().encode(body));
  return `dfsw_${body}.${b64url(sig)}`;
}

/** Returns the access code a valid token stands for, or null. */
async function readSession(env: Env, token: string): Promise<string | null> {
  if (!env.API_KEY || !token.startsWith('dfsw_')) return null;
  const [body, sig] = token.slice(5).split('.');
  if (!body || !sig) return null;
  try {
    const expect = await crypto.subtle.sign('HMAC', await signingKey(env),
                                            new TextEncoder().encode(body));
    if (b64url(expect) !== sig) return null;          // forged or tampered
    const json = JSON.parse(atob(body.replace(/-/g, '+').replace(/_/g, '/')));
    if (!json.c || typeof json.exp !== 'number' || json.exp < Date.now()) return null;
    return String(json.c);
  } catch { return null; }
}

async function authLogin(request: Request, env: Env) {
  if (!env.API_KEY) return err('Worker not configured', 503);
  let code = '';
  try { code = String(((await request.json()) as any)?.code || '').trim(); } catch {}
  if (!code) return err('access code required', 400);

  const sql = getSql(env);
  try {
    // Deliberately the same checks resolveTenant makes, so a code that cannot
    // be used cannot be signed in with either.
    const [who] = await sql`
      select t.slug, t.schema_name, t.active as t_active,
             c.active as c_active, c.expires_at, c.name
        from access_codes c
        join tenants t on t.id = c.tenant_id
       where c.code = ${code} limit 1`;
    // One message for every failure: a sign-in screen that distinguishes
    // "no such code" from "suspended" tells a stranger which codes exist.
    const bad = !who || !who.c_active || !who.t_active ||
                (who.expires_at && new Date(who.expires_at) < new Date());
    if (bad) return err('that code will not sign in', 403);

    return json({
      token: await mintSession(env, code),
      name: who.name || null,
      slug: who.slug,
      is_owner: who.schema_name === 'public',
      expires_in: SESSION_HOURS * 3600,
    });
  } catch (e: any) {
    return err(String(e?.message || e).slice(0, 200), 500);
  } finally {
    await sql.end({ timeout: 5 }).catch(() => {});
  }
}

/* ------------------------------------------------------------------ *
 * The phone scanner.
 *
 * One phone, one Mac, one person — so this is a single shared key rather
 * than sign-ins and tenants. What it protects is narrow by design: a
 * SCAN_KEY holder can add and read photographs under `scan/`, and can do
 * nothing else. It never touches the database, so the worst case is a
 * stranger filling an R2 bucket with pictures, not reading what a card
 * cost. Like everything else here it fails CLOSED when unset.
 * ------------------------------------------------------------------ */
function scanAuthed(request: Request, env: Env): boolean {
  if (!env.SCAN_KEY) return false;
  const sent = request.headers.get('X-DFS-Scan') || '';
  if (sent.length !== env.SCAN_KEY.length) return false;
  let diff = 0;
  for (let i = 0; i < sent.length; i++) diff |= sent.charCodeAt(i) ^ env.SCAN_KEY.charCodeAt(i);
  // The Mac-side puller already holds the full API key; let it use that too
  // rather than making him keep a second secret in a second place.
  return diff === 0;
}

/** A stack or file name becomes part of an R2 key, so nothing else is allowed. */
function safeName(s: string, max = 120): string {
  return (s || '').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[.-]+/, '').slice(0, max);
}

const SCAN_MAX = 12 * 1024 * 1024;

async function scanUpload(request: Request, env: Env, url: URL) {
  if (!env.CARD_IMAGES) return err('image bucket not bound', 500);
  const stack = safeName(url.searchParams.get('stack') || '', 60);
  const name = safeName(url.searchParams.get('name') || '', 120);
  if (!stack || !name) return err('stack and name are required', 400);
  if (!/\.(jpe?g|png|heic)$/i.test(name)) return err('only jpg, png or heic', 400);

  const buf = await request.arrayBuffer();
  if (buf.byteLength < 1024) return err('too small to be a card photo', 400);
  if (buf.byteLength > SCAN_MAX) return err('photo over 12MB', 413);

  const key = `scan/${stack}/${name}`;
  await env.CARD_IMAGES.put(key, buf, {
    httpMetadata: {
      contentType: request.headers.get('content-type') || 'image/jpeg',
      cacheControl: 'public, max-age=31536000, immutable',
    },
    customMetadata: { stack, uploaded_at: new Date().toISOString() },
  });
  return json({ ok: true, key, bytes: buf.byteLength });
}

/** Lists what the phone has sent, so the Mac can pull only what is new. */
async function scanList(env: Env, url: URL) {
  if (!env.CARD_IMAGES) return err('image bucket not bound', 500);
  const stack = safeName(url.searchParams.get('stack') || '', 60);
  const prefix = stack ? `scan/${stack}/` : 'scan/';
  const out: any[] = [];
  const stacks = new Map<string, { photos: number; bytes: number; newest: string }>();
  let cursor: string | undefined;
  do {
    const r: R2Objects = await env.CARD_IMAGES.list({ prefix, cursor, limit: 1000 });
    for (const o of r.objects) {
      const rel = o.key.slice('scan/'.length);
      const slash = rel.indexOf('/');
      const st = slash < 0 ? '(loose)' : rel.slice(0, slash);
      const at = o.uploaded.toISOString();
      const agg = stacks.get(st) || { photos: 0, bytes: 0, newest: at };
      agg.photos++; agg.bytes += o.size;
      if (at > agg.newest) agg.newest = at;
      stacks.set(st, agg);
      out.push({ key: o.key, stack: st, name: rel.slice(slash + 1), bytes: o.size, uploaded: at });
    }
    cursor = r.truncated ? r.cursor : undefined;
  } while (cursor);
  out.sort((a, b) => (a.key < b.key ? -1 : 1));
  return json({
    stacks: [...stacks.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => (a.newest < b.newest ? 1 : -1)),
    photos: out,
  });
}

async function scanGet(env: Env, key: string) {
  if (!env.CARD_IMAGES) return err('image bucket not bound', 500);
  if (!key.startsWith('scan/')) return err('not found', 404);
  const obj = await env.CARD_IMAGES.get(key);
  if (!obj) return err('photo not found', 404);
  return new Response(obj.body, {
    headers: {
      'Content-Type': obj.httpMetadata?.contentType || 'image/jpeg',
      'Cache-Control': 'public, max-age=31536000, immutable',
      ...CORS,
    },
  });
}

async function scanDelete(env: Env, key: string) {
  if (!env.CARD_IMAGES) return err('image bucket not bound', 500);
  if (!key.startsWith('scan/')) return err('not found', 404);
  await env.CARD_IMAGES.delete(key);
  return json({ ok: true, deleted: key });
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

    // ---- phone scanner ----
    // The page itself carries no secret; the key is typed in on the phone
    // once and kept there, so serving the HTML openly costs nothing.
    // Public, and must be: eBay's own forms fetch these.
    if (path === '/privacy') return privacyPage();
    if (path === '/api/ebay/declined') return declinedPage();

    if (path === '/scan' || path === '/scan/index.html') {
      return new Response(SCANNER_HTML, {
        headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' },
      });
    }
    // A valid session token stands in for the key AND for X-DFS-Tenant. The
    // request is rebuilt with that header so every route below — including
    // the existing /api/db and /api/me — carries on unchanged, and Streamlit,
    // which sends the key directly, is untouched by any of this.
    const bearer = (request.headers.get('Authorization') || '').replace(/^Bearer /i, '');
    let signedIn = false;
    if (bearer) {
      const code = await readSession(env, bearer);
      if (code) {
        const h = new Headers(request.headers);
        h.set('X-DFS-Tenant', code);
        request = new Request(request, { headers: h });
        signedIn = true;
      } else {
        // Say so plainly: the app shows "signed out" rather than a dead screen.
        return err('session expired', 401);
      }
    }

    if (path.startsWith('/api/scan')) {
      // The phone has the scan key; the app has a session. Both are
      // him, and the Hopper reads the same bucket the phone writes.
      if (!signedIn && !scanAuthed(request, env) && !authed(request, env)) {
        return err(env.SCAN_KEY
          ? 'unauthorized'
          : 'SCAN_KEY not configured — run: npx wrangler secret put SCAN_KEY',
          env.SCAN_KEY ? 401 : 503);
      }
      if (path === '/api/scan/upload' && request.method === 'POST') return scanUpload(request, env, url);
      if (path === '/api/scan/list' && request.method === 'GET') return scanList(env, url);
      const sg = path.match(/^\/api\/scan\/img\/(.+)$/);
      if (sg && request.method === 'GET') return scanGet(env, decodeURIComponent(sg[1]));
      if (sg && request.method === 'DELETE') return scanDelete(env, decodeURIComponent(sg[1]));
      return err(`no route: ${request.method} ${path}`, 404);
    }

    if (path === '/api/auth/login' && request.method === 'POST')
      return authLogin(request, env);

    // eBay redirects the browser here after consent, carrying no header
    // of ours — the tenant travels in `state` instead.
    if (path === '/api/ebay/callback') return ebayCallback(request, env, url);

    if (!signedIn && !authed(request, env)) {
      return err(env.API_KEY
        ? 'unauthorized'
        : 'API_KEY not configured on this Worker — run: npx wrangler secret put API_KEY',
        env.API_KEY ? 401 : 503);
    }

    if (path === '/api/inventory/mirror' && request.method === 'POST') return mirror(request, env);

    if (path === '/api/listings/refresh' && request.method === 'POST')
      return listingsRefresh(request, env);
    if (path === '/api/listings/retire' && request.method === 'POST')
      return listingsRetire(request, env);
    if (path === '/api/comps/fetch' && request.method === 'POST')
      return compsFetch(request, env);
    if (path === '/api/dashboard') return dashboard(request, env, url);
    if (path === '/api/ai/accept-licence' && request.method === 'POST')
      return aiAccept(request, env);
    if (path === '/api/hopper/cards') return hopperCards(request, env, url);
    if (path === '/api/hopper/identify' && request.method === 'POST')
      return hopperIdentify(request, env);
    if (path === '/api/hopper/save' && request.method === 'POST')
      return hopperSave(request, env);
    if (path === '/api/titles/suggest' && request.method === 'POST')
      return titlesSuggest(request, env);
    if (path === '/api/lots' && request.method === 'GET') return lots(request, env);
    if (path === '/api/lots' && request.method === 'POST') return lotSave(request, env);
    if (path === '/api/lots/spread-cost' && request.method === 'POST') return costSpread(request, env);
    if (path === '/api/ebay/status') return ebayStatus(request, env);
    if (path === '/api/ebay/connect') return ebayConnect(request, env, url);
    if (path === '/api/ebay/push' && request.method === 'POST') return ebayPush(request, env);
    if (path === '/api/ebay/orders' && request.method === 'POST')
      return ebayPullOrders(request, env, url);

    if (path === '/api/tenants/delete' && request.method === 'POST')
      return tenantDelete(request, env);

    if (path === '/api/me') return whoAmI(request, env);

    if (path === '/api/tenants/drift') return tenantDrift(request, env, false);
    if (path === '/api/tenants/migrate' && request.method === 'POST')
      return tenantDrift(request, env, true);

    const db = path.match(/^\/api\/db\/([a-z_]+)(?:\/(.+))?$/);
    if (db) return handleDb(request, env, db[1], db[2] || null);

    return err(`no route: ${request.method} ${path}`, 404);
  },
};
