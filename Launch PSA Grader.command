#!/bin/bash
cd "$(dirname "$0")"

# Kill any existing instance
pkill -f "streamlit run app.py" 2>/dev/null
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

# Open browser after 3 second delay
sleep 3 && open "http://localhost:8502" &

# Start the app
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m streamlit run app.py \
  --server.port 8502 \
  --browser.gatherUsageStats false \
  --server.headless true \
  --browser.serverAddress localhost
