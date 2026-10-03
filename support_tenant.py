#!/usr/bin/env python3
"""Supporting a tenant without casually reading their books.

    python3 support_tenant.py --check              # schema drift, all tenants
    python3 support_tenant.py --migrate all        # bring tenants up to date
    python3 support_tenant.py --status betaone     # counts only, no row contents
    python3 support_tenant.py --errors betaone     # what failed for them lately
    python3 support_tenant.py --access betaone "can't save a purchase lot"
    python3 support_tenant.py --log                # who looked at what, when

## The honest caveat

Schema isolation stops the APP from crossing tenants. It does not, and cannot,
stop whoever holds the Neon connection string — that is the owner. Every SaaS
works this way: the operator can read the database. So the goal here is not to
make owner access impossible, it is to make it DELIBERATE and RECORDED, and to
make most support possible without it at all.

## Why drift is the support issue that will actually happen

New features ship DDL. The owner's schema gets it (that is where it is run);
tenant schemas do not. The tester then hits "column does not exist" on a
feature that works perfectly for the owner — a bug that is invisible from the
owner's account and impossible for the tester to describe. `--check` after
every DDL change, `--migrate` to fix. That is the whole maintenance loop.
"""

from __future__ import annotations

import argparse
import getpass
import pathlib
import subprocess
import sys

PSQL = "/opt/homebrew/opt/libpq/bin/psql"
ENV = pathlib.Path.home() / "dfs-backup" / ".env"
SHARED = {"access_codes", "pricing_usage", "tenants", "support_log"}

LOG_DDL = """
create table if not exists support_log (
  id          bigint primary key generated always as identity,
  at          timestamptz default now(),
  who         text,
  tenant_slug text,
  action      text,
  reason      text
);
"""


def db_url() -> str:
    # Line-by-line: NAS_ROOT holds an unquoted path with a space, so sourcing
    # the file aborts and silently leaves everything unset.
    for line in ENV.read_text().splitlines():
        if line.startswith("CARDS_URL="):
            return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("CARDS_URL not found in ~/dfs-backup/.env")


def q(url: str, sql: str, stdin: str | None = None) -> str:
    args = [PSQL, url, "-v", "ON_ERROR_STOP=1", "-At"]
    if stdin is None:
        args += ["-c", sql]
    r = subprocess.run(args, input=stdin, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"psql failed:\n{r.stderr.strip()[:800]}")
    return r.stdout.strip()


def tenants(url: str, only: str | None = None) -> list[tuple[str, str]]:
    where = f"and slug = '{only}'" if only and only != "all" else ""
    rows = q(url, f"select slug, schema_name from tenants "
                  f"where schema_name <> 'public' {where} order by id")
    if not rows:
        return []
    return [tuple(l.split("|")) for l in rows.splitlines()]


def log(url: str, slug: str, action: str, reason: str = "") -> None:
    q(url, LOG_DDL)
    who = getpass.getuser()
    q(url, f"""insert into support_log (who, tenant_slug, action, reason)
               values ($x${who}$x$, $x${slug}$x$, $x${action}$x$, $x${reason}$x$)""")


# ── drift ────────────────────────────────────────────────────────────────────

def columns(url: str, schema: str, table: str) -> dict[str, str]:
    """Column name → definition, straight from the catalog.

    format_type is used rather than information_schema.data_type because the
    latter reports "numeric" without its precision, so a drift check built on
    it reports two different columns as identical.
    """
    rows = q(url, f"""
        select a.attname,
               format_type(a.atttypid, a.atttypmod),
               a.attnotnull,
               coalesce(pg_get_expr(d.adbin, d.adrelid), '')
          from pg_attribute a
          left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
         where a.attrelid = '"{schema}"."{table}"'::regclass
           and a.attnum > 0 and not a.attisdropped
         order by a.attnum""")
    out = {}
    for line in rows.splitlines() if rows else []:
        name, typ, notnull, default = (line.split("|") + [""] * 4)[:4]
        out[name] = f"{typ}{' not null' if notnull == 't' else ''}" + \
                    (f" default {default}" if default else "")
    return out


def public_tables(url: str) -> list[str]:
    rows = q(url, """select table_name from information_schema.tables
                      where table_schema = 'public' and table_type = 'BASE TABLE'
                      order by table_name""")
    return [t for t in rows.splitlines() if t not in SHARED]


def drift(url: str, slug: str, schema: str) -> dict:
    want = public_tables(url)
    have = q(url, f"""select table_name from information_schema.tables
                       where table_schema = '{schema}' and table_type = 'BASE TABLE'""")
    have = set(have.splitlines()) if have else set()

    missing_tables = [t for t in want if t not in have]
    missing_cols: list[tuple[str, str, str]] = []
    for t in want:
        if t in missing_tables:
            continue
        pub, ten = columns(url, "public", t), columns(url, schema, t)
        for name, definition in pub.items():
            if name not in ten:
                missing_cols.append((t, name, definition))
    return {"slug": slug, "schema": schema,
            "missing_tables": missing_tables, "missing_columns": missing_cols}


def report(url: str, only: str | None = None) -> list[dict]:
    rows = tenants(url, only)
    if not rows:
        print("no tenants besides the owner")
        return []
    results = []
    for slug, schema in rows:
        d = drift(url, slug, schema)
        results.append(d)
        if not d["missing_tables"] and not d["missing_columns"]:
            print(f"✅ {slug} ({schema}) — up to date with public")
            continue
        print(f"⚠️  {slug} ({schema}) is behind:")
        for t in d["missing_tables"]:
            print(f"      missing table   {t}")
        for t, c, defn in d["missing_columns"]:
            print(f"      missing column  {t}.{c}  {defn}")
        print(f"      → fix: python3 support_tenant.py --migrate {slug}")
    return results


def migrate(url: str, only: str) -> None:
    for d in report(url, only):
        if not d["missing_tables"] and not d["missing_columns"]:
            continue
        schema, slug = d["schema"], d["slug"]
        stmts = []
        for t in d["missing_tables"]:
            # LIKE copies types, defaults, identity, constraints and indexes
            # from the live table, so a new table cannot drift on arrival.
            stmts.append(f'CREATE TABLE "{schema}"."{t}" '
                         f'(LIKE public."{t}" INCLUDING ALL);')
        for t, c, defn in d["missing_columns"]:
            # NOT NULL is dropped deliberately: an existing tenant row has no
            # value for a new column, so enforcing it here fails the migration.
            safe = defn.replace(" not null", "")
            stmts.append(f'ALTER TABLE "{schema}"."{t}" '
                         f'ADD COLUMN IF NOT EXISTS "{c}" {safe};')
        print(f"\n→ {slug}: applying {len(stmts)} change(s)")
        q(url, "", stdin="begin;\n" + "\n".join(stmts) + "\ncommit;\n")
        log(url, slug, "migrate", f"{len(stmts)} statements")
        print(f"✅ {slug} migrated")
    print("\nre-checking:")
    report(url, only)


# ── status, without reading their rows ───────────────────────────────────────

def status(url: str, slug: str) -> None:
    rows = tenants(url, slug)
    if not rows:
        sys.exit(f"no tenant '{slug}'")
    _, schema = rows[0]
    print(f"Tenant {slug} — schema {schema}\n")
    counts = q(url, f"""
        select relname, n_live_tup
          from pg_stat_user_tables
         where schemaname = '{schema}' and n_live_tup > 0
         order by n_live_tup desc""")
    if counts:
        print("  rows per table (counts only — no contents):")
        for line in counts.splitlines():
            t, n = line.split("|")
            print(f"    {t:<22} {n:>7}")
    else:
        print("  no data yet — they have not imported anything")

    codes = q(url, f"""
        select c.code, c.active, c.daily_limit, coalesce(c.last_used::text, 'never'),
               c.usage_count
          from access_codes c join tenants t on t.id = c.tenant_id
         where t.slug = '{slug}'""")
    print("\n  access codes:")
    for line in codes.splitlines() if codes else ["— none"]:
        parts = line.split("|")
        if len(parts) == 5:
            code, active, limit, last, uses = parts
            print(f"    {code}  active={active}  cap={limit or '∞'}/day  "
                  f"uses={uses}  last={last}")
    log(url, slug, "status")


def errors(url: str, slug: str) -> None:
    """Where to see what actually broke for them.

    Streamlit Cloud holds the Python traceback; the Worker holds the API side.
    Neither is in the database, so this prints the two commands rather than
    pretending to have the logs.
    """
    print(f"Diagnosing {slug} — the logs live in two places:\n")
    print("  1. App errors (Python traceback, the usual cause):")
    print("     Streamlit Cloud → your app → Manage app → logs")
    print("     Filter by the time they reported it.\n")
    print("  2. API errors (database, auth, tenant resolution):")
    print('     cd "/Users/duanefurlong/Desktop/The CardPulse/cloudflare-worker"')
    print("     npx wrangler tail --format pretty")
    print("     Then have them retry while it streams.\n")
    print("  3. Schema behind the owner's? That causes errors no one can")
    print("     describe, and is the first thing to rule out:")
    print(f"     python3 support_tenant.py --check\n")
    status(url, slug)


def access(url: str, slug: str, reason: str) -> None:
    """Sign in as the tenant to reproduce — deliberate, and recorded."""
    if not reason or len(reason) < 8:
        sys.exit('give a reason: --access betaone "cannot save a purchase lot"')
    rows = tenants(url, slug)
    if not rows:
        sys.exit(f"no tenant '{slug}'")
    code = q(url, f"""select c.code from access_codes c join tenants t on t.id = c.tenant_id
                       where t.slug = '{slug}' and c.active limit 1""")
    if not code:
        sys.exit(f"{slug} has no active access code")
    print(f"⚠️  This signs you in AS {slug} and shows their data.")
    print(f"    Reason recorded: {reason}")
    print(f"    Ask them first — it is their business data, not yours.\n")
    if input("Type the slug to confirm: ").strip() != slug:
        sys.exit("cancelled — nothing logged as accessed")
    log(url, slug, "access", reason)
    print(f"\n  Sign in with: {code}")
    print(f"  Recorded in support_log. Sign out when you are done.")


def show_log(url: str) -> None:
    q(url, LOG_DDL)
    rows = q(url, """select at::timestamp(0), who, tenant_slug, action,
                            coalesce(reason, '')
                       from support_log order by at desc limit 40""")
    if not rows:
        print("support_log is empty — no tenant has been accessed")
        return
    print(f"{'when':<20} {'who':<10} {'tenant':<10} {'action':<9} reason")
    for line in rows.splitlines():
        at, who, slug, action, reason = (line.split("|") + [""] * 5)[:5]
        print(f"{at:<20} {who:<10} {slug:<10} {action:<9} {reason}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="schema drift, all tenants")
    ap.add_argument("--migrate", metavar="SLUG|all", help="apply missing tables/columns")
    ap.add_argument("--status", metavar="SLUG", help="row counts and codes, no contents")
    ap.add_argument("--errors", metavar="SLUG", help="where to find their logs")
    ap.add_argument("--access", nargs=2, metavar=("SLUG", "REASON"),
                    help="sign in as them (logged)")
    ap.add_argument("--log", action="store_true", help="show the support audit trail")
    a = ap.parse_args()
    url = db_url()

    if a.check:          report(url)
    elif a.migrate:      migrate(url, a.migrate)
    elif a.status:       status(url, a.status)
    elif a.errors:       errors(url, a.errors)
    elif a.access:       access(url, a.access[0], a.access[1])
    elif a.log:          show_log(url)
    else:                ap.print_help()


if __name__ == "__main__":
    main()
