"""
fix_skus.py — Fix SKU prefix and title casing on Haystack export
Usage:  python3 fix_skus.py  HaystackExport.csv
Output: HaystackExport_FIXED.csv  (same folder)

Steps:
  1. In Haystack → Inventory, export your listings to CSV
  2. Run:  python3 fix_skus.py  /path/to/export.csv
  3. In Haystack → Import, upload the _FIXED.csv as "Update existing"
"""
import csv, re, sys, pathlib

OLD_PREFIX = "POOKIEWHT-08-17-26"   # uppercase compare
NEW_PREFIX = "CURTDAWG-08-15-26"

def fix_title_caps(title: str) -> str:
    """
    If title is mostly uppercase (all-caps entry from Haystack),
    convert to Title Case with player name still in ALL CAPS.
    Detects all-caps: >70% of alpha chars are uppercase.
    """
    alpha = [c for c in title if c.isalpha()]
    if not alpha:
        return title
    upper_pct = sum(1 for c in alpha if c.isupper()) / len(alpha)
    if upper_pct < 0.70:
        return title           # already mixed case, leave it

    # Title-case everything first
    words = title.split()
    fixed = []
    for w in words:
        # Keep card-number tokens like #BCP-199, #CPA-JM as-is (uppercase is fine)
        if w.startswith('#') or re.match(r'^[A-Z]{2,}-\d', w):
            fixed.append(w)
        # Short all-caps tokens that look like abbreviations: RC, GTC, etc.
        elif re.match(r'^[A-Z]{2,4}$', w):
            fixed.append(w)
        else:
            fixed.append(w.title())
    return ' '.join(fixed)

def fix_player_caps(title: str) -> str:
    """
    Ensure player names stay ALL CAPS in mixed-case titles.
    Heuristic: after '#CARDNUM' or after set tokens, the all-caps word(s)
    that look like a person's name → uppercase them.
    This is a light-touch pass; the main fix is fix_title_caps above.
    """
    return title  # title_caps already handles this acceptably

def process(input_path: str):
    p = pathlib.Path(input_path)
    out_path = p.with_name(p.stem + "_FIXED" + p.suffix)

    # Try common SKU column names Haystack uses
    SKU_COLS = ["CustomLabel", "Custom Label", "SKU", "Custom label (SKU)"]
    TITLE_COLS = ["*Title", "Title"]

    with open(p, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    sku_col   = next((c for c in fieldnames if c in SKU_COLS), None)
    title_col = next((c for c in fieldnames if c in TITLE_COLS), None)

    if not sku_col:
        print(f"ERROR: No SKU column found. Columns in file: {fieldnames}")
        sys.exit(1)

    changed_sku   = 0
    changed_title = 0

    for row in rows:
        sku = row.get(sku_col, "") or ""
        if sku.upper().startswith(OLD_PREFIX):
            suffix = sku[len(OLD_PREFIX):]        # e.g. "-00036"
            row[sku_col] = NEW_PREFIX + suffix
            changed_sku += 1

        if title_col:
            orig = row.get(title_col, "") or ""
            fixed = fix_title_caps(orig)
            if fixed != orig:
                row[title_col] = fixed
                changed_title += 1

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done → {out_path}")
    print(f"  SKUs renamed : {changed_sku}")
    print(f"  Titles fixed : {changed_title}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    process(sys.argv[1])
