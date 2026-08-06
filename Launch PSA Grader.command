#!/bin/bash
cd "$(dirname "$0")"

# Kill any existing instances
pkill -f "streamlit run app.py" 2>/dev/null
pkill -f "card-scanner/app.py" 2>/dev/null
sleep 1

# Install dependencies silently
/Library/Frameworks/Python.framework/Versions/3.14/bin/pip3 install streamlit pandas openpyxl -q 2>/dev/null

echo ""
echo "================================================"
echo "  DFS PSA Grader is starting..."
echo "================================================"
echo ""
echo "  Opening in your browser at:"
echo "  http://localhost:8502"
echo ""
echo "  Keep this window open while using the app."
echo "  Close it to shut the app down."
echo "================================================"
echo ""

# Start batch scanner in background
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 card-scanner/app.py > /tmp/dfs-scanner.log 2>&1 &

# Read version from app.py and open with cache-busting param so new versions always load fresh
VERSION=$(grep 'APP_VERSION = ' app.py | head -1 | tr -d '"' | awk -F'= ' '{print $2}' | tr -d '.')
sleep 3 && open "http://localhost:8502/?v=${VERSION}" &

# Start the app
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m streamlit run app.py \
  --server.port 8502 \
  --browser.gatherUsageStats false \
  --server.headless true \
  --browser.serverAddress localhost
