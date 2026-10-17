#!/bin/zsh
# Double-click to keep pulling the phone's card photos onto this Mac.
# Close the window to stop. Photos land in ~/Desktop/Card Scans/<stack>/
cd "$(dirname "$0")"
clear
echo "Pulling card scans — leave this window open while you scan."
echo
exec python3 pull_scans.py --watch --clear
