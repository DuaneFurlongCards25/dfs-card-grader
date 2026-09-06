#!/bin/bash
# Double-click to run CardPulse.
#
# This used to call /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
# by its full path. That is this Mac's Python, at this Mac's version number —
# on any machine with 3.13, or with Python from Homebrew, the launcher died
# before printing anything. It now finds whatever Python is actually here.

cd "$(dirname "$0")" || exit 1

PY=$(command -v python3)
if [ -z "$PY" ]; then
  clear
  echo "✗ Python 3 is not installed on this Mac."
  echo
  echo "  Install it from https://www.python.org/downloads/ then try again."
  echo
  read -r -p "Press return to close."
  exit 1
fi

# Stop anything already running, so a second double-click doesn't fight
# the first over port 8502.
pkill -f "streamlit run app.py" 2>/dev/null
pkill -f "card-scanner/app.py" 2>/dev/null
sleep 1

clear
echo "================================================"
echo "  CardPulse is starting..."
echo "================================================"
echo
echo "  Python: $($PY -V)"

# Dependencies, checked every launch rather than only on the first: the
# requirements grow, and a Mac that worked last month can be missing
# something added since.
NEED=$("$PY" - <<'EOF'
mods = {"streamlit": "streamlit", "pandas": "pandas",
        "openpyxl": "openpyxl", "reportlab": "reportlab"}
print(" ".join(v for k, v in mods.items()
               if not __import__("importlib.util", fromlist=["util"])
                        .util.find_spec(k)))
EOF
)
if [ -n "$NEED" ]; then
  echo "  installing: $NEED"
  "$PY" -m pip install --user --quiet $NEED || {
    echo
    echo "✗ Install failed. Run this in Terminal to see why:"
    echo "    cd \"$(pwd)\" && python3 -m pip install -r requirements.txt"
    echo
    read -r -p "Press return to close."
    exit 1
  }
fi
echo "  dependencies ok"

if [ -f .streamlit/secrets.toml ]; then
  echo "  API keys found"
else
  echo
  echo "✗ .streamlit/secrets.toml is missing — no CardHedger, so no pricing."
  echo
  read -r -p "Press return to close."
  exit 1
fi

echo
echo "  Opening at http://localhost:8502"
echo "  Keep this window open while you work; closing it stops the app."
echo "================================================"
echo

# The phone-scanning helper, in the background.
"$PY" card-scanner/app.py > /tmp/dfs-scanner.log 2>&1 &

# Cache-bust on the version so a new build never loads from cache.
VERSION=$(grep 'APP_VERSION = ' app.py | head -1 | tr -d '"' | awk -F'= ' '{print $2}' | tr -d '.')
( sleep 3; open "http://localhost:8502/?v=${VERSION}" ) &

exec "$PY" -m streamlit run app.py \
  --server.port 8502 \
  --browser.gatherUsageStats false \
  --server.headless true \
  --browser.serverAddress localhost
