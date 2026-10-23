#!/usr/bin/env bash
# Consistent cold backup: stop YaCy, archive named volume, restart.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo "Missing .env" >&2; exit 1; }
# shellcheck disable=SC1091
source .env
[[ "$YACY_VOLUME_NAME" =~ ^route_a_[a-z0-9_]+_data$ ]] || { echo "Unexpected volume" >&2; exit 1; }
mkdir -p backups
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${NODE_ID}_${STAMP}.tar.gz"
dc() { docker compose -f infra/compose.yml --env-file .env "$@"; }
dc stop
trap 'dc start >/dev/null || true' EXIT
docker run --rm -v "$YACY_VOLUME_NAME:/data:ro" -v "$ROOT/backups:/backups" busybox:1.36 \
  sh -c 'cd /data && tar -czf "/backups/$1" .' sh "$ARCHIVE"
echo "Saved $ROOT/backups/$ARCHIVE"
echo "Keep archives outside Git and verify backup integrity before restore."
