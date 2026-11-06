#!/usr/bin/env bash
# Persist the SQLite history (what was made/published, so nothing repeats) on an orphan branch `ivs-state`.
# usage: scripts/state.sh restore | save     (needs `permissions: contents: write`; uses the built-in GITHUB_TOKEN, free)
set -euo pipefail
DB="${IVS_DB:-data/ivs.sqlite3}"; BR=ivs-state; TMP="$(mktemp -d)"
case "${1:-}" in
  restore)
    mkdir -p "$(dirname "$DB")"
    if git ls-remote --exit-code --heads origin "$BR" >/dev/null 2>&1; then
      git fetch --depth=1 origin "$BR"; git --work-tree="$TMP" checkout FETCH_HEAD -- . 2>/dev/null || true
      [ -f "$TMP/ivs.sqlite3" ] && cp "$TMP/ivs.sqlite3" "$DB" && echo "state restored"
    else echo "no state branch yet (first run)"; fi ;;
  save)
    [ -f "$DB" ] || { echo "no db to save"; exit 0; }
    python3 - "$DB" "$TMP/ivs.sqlite3" <<'PY'
import sqlite3, sys
s = sqlite3.connect(sys.argv[1]); d = sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()   # consistent snapshot
PY
    cd "$TMP"; git init -q -b "$BR"; git config user.name "ivs-bot"; git config user.email "ivs-bot@users.noreply.github.com"
    git add ivs.sqlite3; git commit -qm "state $(date -u +%FT%TZ)"
    git push -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" "$BR" && echo "state saved" ;;
  *) echo "usage: $0 restore|save"; exit 2 ;;
esac
