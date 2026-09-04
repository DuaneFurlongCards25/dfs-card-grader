#!/bin/bash
cd "$(dirname "$0")"

# Install dependencies if needed
if ! python3 -c "import flask, watchdog, requests" 2>/dev/null; then
  echo "Installing dependencies..."
  pip3 install -r requirements.txt
fi

echo "Starting DFS Card Scanner..."
echo "Open http://localhost:5100 in your browser"
python3 app.py
