#!/bin/bash
# Double-click to get the newest CardPulse and run it.
#
# Written because the app is used on two Macs — the MacBook and the Mac Studio
# — and each has its own clone. Whichever one you worked on last is ahead, and
# the other opens yesterday's app with no sign anything is missing. This pulls
# first, then launches, so "latest" is not something to remember.
#
# It refuses to pull over uncommitted work rather than clobbering it, and it
# says plainly when it could not reach GitHub instead of starting an old build
# as though nothing happened.

cd "$(dirname "$0")" || exit 1

BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'
echo "${BOLD}CardPulse — update and launch${OFF}"
echo "$(sw_vers -productName) · $(hostname -s)"
echo

PY=$(command -v python3)
if [ -z "$PY" ]; then
  echo "${RED}No python3 on this Mac.${OFF}"
  echo "Install it from python.org, then double-click this again."
  read -r -p "Press return to close."; exit 1
fi

# ── 1. Get the newest code ───────────────────────────────────────────────────
if [ -d .git ]; then
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "${YEL}This Mac has changes that are not committed.${OFF}"
    git status --short --untracked-files=no | sed 's/^/    /'
    echo "Leaving them alone and starting the app as it is — a pull here could"
    echo "throw that work away. Commit or stash it, then run this again."
    echo
  else
    BEFORE=$(git rev-parse --short HEAD 2>/dev/null)
    echo "Checking GitHub for a newer version…"
    if git pull --ff-only --quiet 2>/tmp/cardpulse_pull_err; then
      AFTER=$(git rev-parse --short HEAD 2>/dev/null)
      if [ "$BEFORE" = "$AFTER" ]; then
        echo "${GREEN}Already the latest${OFF} ($AFTER)."
      else
        echo "${GREEN}Updated${OFF} $BEFORE → $AFTER:"
        git log --oneline "$BEFORE..$AFTER" | sed 's/^/    /'
      fi
    else
      echo "${RED}Could not update from GitHub.${OFF}"
      sed 's/^/    /' /tmp/cardpulse_pull_err
      echo "Starting the version already on this Mac — it may be behind the"
      echo "other machine."
    fi
    echo
  fi
fi

# ── 2. Make sure the libraries are there ─────────────────────────────────────
if ! "$PY" -c "import streamlit" >/dev/null 2>&1; then
  echo "Installing the libraries the app needs (first run on this Mac)…"
  "$PY" -m pip install --quiet --user -r requirements.txt || {
    echo "${RED}Install failed.${OFF} Try it by hand:"
    echo "    $PY -m pip install --user -r requirements.txt"
    read -r -p "Press return to close."; exit 1; }
fi

# ── 3. Warn about the file that never travels through git ────────────────────
# .streamlit/secrets.toml is gitignored on purpose — it holds the CardHedger
# and admin keys. A fresh clone therefore has none, and the app comes up
# missing live pricing with nothing on screen explaining why.
if [ ! -f .streamlit/secrets.toml ]; then
  echo "${YEL}No .streamlit/secrets.toml on this Mac.${OFF}"
  echo "The app will start, but live pricing and the admin panel will be off."
  echo "Copy that file across from the other Mac (it is deliberately kept out"
  echo "of GitHub), then run this again."
  echo
fi

echo "Opening CardPulse in your browser. ${BOLD}Leave this window open${OFF} while you use it."
echo "Close this window, or press Control-C, to stop the app."
echo
exec "$PY" -m streamlit run app.py
