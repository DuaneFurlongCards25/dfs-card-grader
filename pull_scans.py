#!/usr/bin/env python3
"""
Pull the phone's card photos onto this Mac.

The phone writes every shot into the Worker's R2 bucket under
`scan/<stack>/<name>.jpg`. This brings them down into

    ~/Desktop/Card Scans/<stack>/

ready to drag into Card Luma. It reads the Worker URL and key straight out of
CardPulse's own .streamlit/secrets.toml, so there is no second place to keep a
secret in step.

    python3 pull_scans.py                 # pull everything new, once
    python3 pull_scans.py --watch         # keep pulling every 20s
    python3 pull_scans.py --stack KKWHAT  # just that one
    python3 pull_scans.py --clear         # remove the phone's copy once it is
                                          # safely on disk (verified by size)

A photo already on disk at the same size is skipped, so running it twice costs
nothing and an interrupted run just picks up where it stopped.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEST = Path.home() / "Desktop" / "Card Scans"
DEFAULT_URL = "https://dfs-cards-api.duane-588.workers.dev"


def secrets() -> tuple[str, str, str]:
    """(worker url, api key, scan key) from secrets.toml, env wins."""
    url = os.environ.get("DFS_WORKER_URL", "")
    key = os.environ.get("DFS_WORKER_KEY", "")
    scan = os.environ.get("DFS_SCAN_KEY", "")
    path = HERE / ".streamlit" / "secrets.toml"
    if path.exists() and not (url and (key or scan)):
        try:
            try:
                import tomllib
            except ModuleNotFoundError:  # py<3.11
                import tomli as tomllib  # type: ignore
            data = tomllib.loads(path.read_text())
            w = data.get("worker", {})
            url = url or w.get("url", "")
            key = key or w.get("key", "")
            scan = scan or w.get("scan_key", "")
        except Exception as e:
            print(f"  could not read secrets.toml: {e}", file=sys.stderr)
    return (url or DEFAULT_URL).rstrip("/"), key, scan


def ssl_ctx() -> ssl.SSLContext:
    """
    This Mac's python.org build ships without the system CA bundle wired in,
    so plain urllib fails every HTTPS call with CERTIFICATE_VERIFY_FAILED.
    certifi is already installed (Streamlit pulls it in) and carries the roots.
    Verification stays ON — this points it at a bundle that exists.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


CTX = ssl_ctx()


def call(url: str, key: str, scan: str, path: str, method: str = "GET") -> bytes:
    req = urllib.request.Request(url + path, method=method)
    # Cloudflare's bot check answers urllib's default agent string with a 1010
    # before the request ever reaches the Worker. Naming the tool gets through.
    req.add_header("User-Agent", "DFS-CardPulse-ScanPuller/1.0")
    # Either key opens /api/scan; the API key is the one already on this Mac.
    if key:
        req.add_header("X-DFS-Key", key)
    if scan:
        req.add_header("X-DFS-Scan", scan)
    with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
        return r.read()


def pull_once(url: str, key: str, scan: str, only: str | None, clear: bool) -> int:
    q = f"?stack={urllib.parse.quote(only)}" if only else ""
    try:
        listing = json.loads(call(url, key, scan, "/api/scan/list" + q))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        if e.code in (401, 503):
            print(f"  the Worker would not accept the key ({e.code}): {body}")
            print("   set it with:  cd cloudflare-worker && npx wrangler secret put SCAN_KEY")
        else:
            print(f"  HTTP {e.code}: {body}")
        return 0
    except Exception as e:
        print(f"  cannot reach the Worker: {e}")
        return 0

    photos = listing.get("photos", [])
    got = 0
    for p in photos:
        out = DEST / p["stack"] / p["name"]
        if out.exists() and out.stat().st_size == p["bytes"]:
            if clear:
                try:
                    call(url, key, scan, "/api/scan/img/" + urllib.parse.quote(p["key"], safe=""),
                         method="DELETE")
                except Exception:
                    pass
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            blob = call(url, key, scan, "/api/scan/img/" + urllib.parse.quote(p["key"], safe=""))
        except Exception as e:
            print(f"  ! {p['name']}: {e}")
            continue
        # Write beside the target first — a dropped connection must not leave a
        # half file that the size check then accepts on the next run.
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(blob)
        tmp.replace(out)
        got += 1
        print(f"  ↓ {p['stack']}/{p['name']}  ({p['bytes'] / 1024:.0f} KB)")
        if clear and out.stat().st_size == p["bytes"]:
            try:
                call(url, key, scan, "/api/scan/img/" + urllib.parse.quote(p["key"], safe=""),
                     method="DELETE")
            except Exception as e:
                print(f"    (left on the phone's side: {e})")

    if got:
        stacks = sorted({p["stack"] for p in photos})
        print(f"{got} new photo(s) → {DEST}")
        for s in stacks:
            n = len(list((DEST / s).glob("*.jpg"))) if (DEST / s).exists() else 0
            print(f"   {s}: {n} on disk")
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description="Pull phone card scans to this Mac")
    ap.add_argument("--watch", action="store_true", help="keep pulling every 20 seconds")
    ap.add_argument("--stack", help="only this stack")
    ap.add_argument("--clear", action="store_true",
                    help="delete the remote copy once it is verified on disk")
    ap.add_argument("--every", type=int, default=20, help="seconds between checks when watching")
    a = ap.parse_args()

    url, key, scan = secrets()
    if not (key or scan):
        print("No worker key found. Add it under [worker] in .streamlit/secrets.toml,")
        print("or export DFS_SCAN_KEY=…")
        return 1

    DEST.mkdir(parents=True, exist_ok=True)
    print(f"Worker: {url}")
    print(f"Folder: {DEST}")
    if not a.watch:
        n = pull_once(url, key, scan, a.stack, a.clear)
        if not n:
            print("Nothing new.")
        return 0

    print(f"Watching every {a.every}s — Control-C to stop.\n")
    try:
        while True:
            pull_once(url, key, scan, a.stack, a.clear)
            time.sleep(a.every)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
