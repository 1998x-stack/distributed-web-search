#!/usr/bin/env bash
# Usage: bash scripts/init-worker.sh <ubuntu-a|ubuntu-b|macos-c> CONTROLLER_IP PATH_TO_WORKER_BASE_ENV
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ $# -ne 3 ]]; then
  echo "Usage: bash scripts/init-worker.sh ubuntu-b CONTROLLER_LAN_IP runtime/worker-base.env" >&2; exit 2
fi
NODE="$1"; HOST="$2"; BASE="$3"
case "$NODE" in ubuntu-a|ubuntu-b|macos-c) ;; *) echo "Unknown worker ID" >&2; exit 2 ;; esac
[[ -f "$BASE" ]] || { echo "Worker base credentials file not found: $BASE" >&2; exit 1; }
grep -Fxq "REDIS_HOST=$HOST" "$BASE" || { echo "Controller IP mismatch" >&2; exit 1; }
grep -Fxq "API_URL=http://$HOST:8000" "$BASE" || { echo "API URL mismatch" >&2; exit 1; }
grep -Eq '^REDIS_PASSWORD=[A-Za-z0-9_-]{32,}$' "$BASE" || { echo "Missing/invalid Redis credential" >&2; exit 1; }
grep -Eq '^INGEST_TOKEN=[A-Za-z0-9_-]{32,}$' "$BASE" || { echo "Missing/invalid ingest credential" >&2; exit 1; }
mkdir -p runtime
umask 077
if [[ -f runtime/worker.env ]] && ! grep -Fxq "WORKER_ID=$NODE" runtime/worker.env; then
  echo "Worker already configured for a different node; refusing overwrite" >&2; exit 1
fi
cp "$BASE" runtime/worker.env
printf 'WORKER_ID=%s\n' "$NODE" >> runtime/worker.env
chmod 600 runtime/worker.env
echo "Configured $NODE => controller $HOST"
