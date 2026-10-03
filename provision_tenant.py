#!/usr/bin/env python3
"""Give a beta tester their own data, in their own Postgres schema.

    python3 provision_tenant.py "Robert Bass" robert
    python3 provision_tenant.py --list
    python3 provision_tenant.py --drop robert      # deletes their data

## Why a schema and not a filter column

The alternative was `account_id` on all 20 tables and a `where` clause on
every query in a 14,000-line app. One forgotten clause there shows a dealer
his competitor's purchase costs, and it would stay forgotten until someone
noticed. A schema cannot be forgotten: outside it, the table does not exist.

## Why the structure is copied, not written out by hand

The schema is built with `pg_dump --schema-only` of `public`, rewritten to the
new schema name. A hand-maintained CREATE TABLE list drifts the first time a
column is added in the Neon console and nobody updates the script — and the
drift shows up as a tester hitting an error on a column the owner has.
Copying means a tenant is always structurally identical to production.

Data is never copied. A new tenant starts empty, which is the whole point.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import secrets as pysecrets
import subprocess
import sys

PSQL = "/opt/homebrew/opt/libpq/bin/psql"
PG_DUMP = "/opt/homebrew/opt/libpq/bin/pg_dump"
ENV = pathlib.Path.home() / "dfs-backup" / ".env"

# Shared across tenants, so they stay in public and must not be duplicated
# into a tenant schema: logins (needed before a tenant is known) and the
# pricing meter (a budget each tenant could reset is not a budget).
SHARED = {"access_codes", "pricing_usage", "tenants"}

SLUG_OK = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def db_url() -> str:
    """CARDS_URL from the backup env.

    Read line-by-line rather than sourced: NAS_ROOT in that file contains an
    unquoted path with a space, so `. .env` aborts and leaves everything unset.
    """
    if not ENV.exists():
        sys.exit(f"missing {ENV}")
    for line in ENV.read_text().splitlines():
        if line.startswith("CARDS_URL="):
            return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("CARDS_URL not found in ~/dfs-backup/.env")


def psql(url: str, sql: str, quiet: bool = False) -> str:
    r = subprocess.run([PSQL, url, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
                       capture_output=True, text=True)
    if r.returncode:
        if quiet:
            return ""
        sys.exit(f"psql failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def list_tenants(url: str) -> None:
    rows = psql(url, """
        select t.id, t.slug, t.schema_name, t.active, t.name,
               coalesce(string_agg(c.code, ' ' order by c.code), '—')
          from tenants t
          left join access_codes c on c.tenant_id = t.id and c.active
         group by t.id, t.slug, t.schema_name, t.active, t.name
         order by t.id""")
    print(f"{'id':>3}  {'slug':<12} {'schema':<14} {'on':<3} {'name':<22} active codes")
    for line in rows.splitlines():
        i, slug, schema, active, name, codes = (line.split("|") + [""] * 6)[:6]
        print(f"{i:>3}  {slug:<12} {schema:<14} {active:<3} {name[:22]:<22} {codes}")
    # Row counts per schema make an empty tenant obviously empty.
    print()
    for line in rows.splitlines():
        schema = line.split("|")[2]
        n = psql(url, f"""
            select coalesce(sum(n_live_tup), 0) from pg_stat_user_tables
             where schemaname = '{schema}'""")
        print(f"  {schema:<14} ~{n or 0} rows")


def provision(url: str, name: str, slug: str) -> None:
    if not SLUG_OK.match(slug):
        sys.exit("slug must be lowercase letters/digits/underscore, 2-31 chars, "
                 "starting with a letter")
    schema = f"t_{slug}"

    if psql(url, f"select 1 from tenants where slug = '{slug}'"):
        sys.exit(f"tenant '{slug}' already exists — use --list")
    if psql(url, f"select 1 from information_schema.schemata "
                 f"where schema_name = '{schema}'"):
        sys.exit(f"schema {schema} already exists; refusing to touch it")

    print(f"→ copying the public structure into {schema} (no data)")
    dump = subprocess.run(
        [PG_DUMP, url, "--schema-only", "--schema=public", "--no-owner",
         "--no-privileges", "--no-comments"],
        capture_output=True, text=True)
    if dump.returncode:
        sys.exit(f"pg_dump failed:\n{dump.stderr.strip()[:500]}")

    ddl = rewrite_schema(dump.stdout, schema)
    out = subprocess.run([PSQL, url, "-v", "ON_ERROR_STOP=1", "-q"],
                         input=f"CREATE SCHEMA {schema};\n{ddl}",
                         capture_output=True, text=True)
    if out.returncode:
        # Leave nothing half-built: a partial schema is worse than none.
        psql(url, f"drop schema if exists {schema} cascade", quiet=True)
        sys.exit(f"schema build failed (rolled back):\n{out.stderr.strip()[:900]}")

    code = f"DFS-{pysecrets.token_hex(2).upper()}-{pysecrets.token_hex(2).upper()}"
    psql(url, f"""
        insert into tenants (slug, name, schema_name, notes)
        values ('{slug}', $n${name}$n$, '{schema}', 'provisioned by provision_tenant.py')""")
    psql(url, f"""
        insert into access_codes (code, name, active, daily_limit, tenant_id)
        values ('{code}', $n${name}$n$, true, 25,
                (select id from tenants where slug = '{slug}'))""")

    tables = psql(url, f"select count(*) from information_schema.tables "
                       f"where table_schema = '{schema}'")
    rows = psql(url, f"select coalesce(sum(n_live_tup),0) from pg_stat_user_tables "
                     f"where schemaname = '{schema}'")
    print(f"✅ {name}: schema {schema}, {tables} tables, {rows} rows (empty as intended)")
    print(f"   access code: {code}   (25 look-ups/day)")
    print(f"   They sign in with that code and see only their own data.")


def rewrite_schema(ddl: str, schema: str) -> str:
    """Point a public-schema dump at `schema` instead.

    Only the three forms pg_dump actually emits are rewritten — qualified
    `public.x` references, the `SET search_path`, and schema creation. A blunt
    replace of the word "public" would also rename it inside a column default
    or a tenant's own data, which is how this kind of script quietly corrupts
    the thing it builds.
    """
    out = []
    for line in ddl.splitlines():
        s = line.strip()
        if s.startswith("CREATE SCHEMA") or s.startswith("COMMENT ON SCHEMA"):
            continue
        line = re.sub(r"\bSET search_path = public\b", f"SET search_path = {schema}", line)
        line = re.sub(r"(?<![\w.])public\.", f"{schema}.", line)
        line = re.sub(r"\bSCHEMA public\b", f"SCHEMA {schema}", line)
        out.append(line)
    return "\n".join(out)


def drop(url: str, slug: str) -> None:
    schema = psql(url, f"select schema_name from tenants where slug = '{slug}'")
    if not schema:
        sys.exit(f"no tenant '{slug}'")
    if schema == "public":
        sys.exit("refusing to drop the owner's schema")
    n = psql(url, f"select coalesce(sum(n_live_tup),0) from pg_stat_user_tables "
                  f"where schemaname = '{schema}'")
    print(f"About to permanently delete schema {schema} (~{n} rows) and its codes.")
    if input("Type the slug to confirm: ").strip() != slug:
        sys.exit("cancelled")
    psql(url, f"drop schema {schema} cascade")
    psql(url, f"delete from access_codes where tenant_id = "
              f"(select id from tenants where slug = '{slug}')")
    psql(url, f"delete from tenants where slug = '{slug}'")
    print(f"✅ dropped {schema}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", help='display name, e.g. "Robert Bass"')
    ap.add_argument("slug", nargs="?", help="short id, e.g. robert")
    ap.add_argument("--list", action="store_true", help="show tenants and row counts")
    ap.add_argument("--drop", metavar="SLUG", help="delete a tenant and ALL their data")
    a = ap.parse_args()

    url = db_url()
    if a.list:
        list_tenants(url)
    elif a.drop:
        drop(url, a.drop)
    elif a.name and a.slug:
        provision(url, a.name, a.slug)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
