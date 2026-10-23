#!/usr/bin/env bash
# Run on Ubuntu A. URL must be a public HTTP(S) page which permits crawling.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Usage: bash scripts/add-seed.sh https://example.org/ [max_depth=1] [max_pages=100]" >&2; exit 2
fi
[[ -f runtime/controller.env ]] || { echo "Controller credentials missing" >&2; exit 1; }
# shellcheck disable=SC1091
source runtime/controller.env
URL="$1"; DEPTH="${2:-1}"; PAGES="${3:-100}"
[[ "$DEPTH" =~ ^[0-5]$ ]] || { echo "max_depth must be 0..5" >&2; exit 2; }
[[ "$PAGES" =~ ^[0-9]+$ ]] && (( PAGES >= 1 && PAGES <= 10000 )) || { echo "max_pages must be 1..10000" >&2; exit 2; }
BODY="$(python3 - "$URL" "$DEPTH" "$PAGES" <<'PY'
import json, sys
print(json.dumps({"url": sys.argv[1], "max_depth": int(sys.argv[2]), "max_pages": int(sys.argv[3])}))
PY
)"
curl --fail-with-body --show-error --silent \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  --data "$BODY" \
  "http://$CONTROLLER_IP:8000/api/v1/seeds"
printf '\n'
