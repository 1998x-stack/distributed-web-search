#!/usr/bin/env bash
# Usage: bash scripts/init-controller.sh 192.168.1.101
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ $# -ne 1 ]]; then
  echo "Usage: bash scripts/init-controller.sh CONTROLLER_LAN_IP" >&2; exit 2
fi
HOST="$1"
python3 - "$HOST" <<'PY'
import ipaddress, sys
try:
    addr = ipaddress.IPv4Address(sys.argv[1])
    assert addr.is_private and not addr.is_loopback and not addr.is_link_local
except (ValueError, AssertionError):
    raise SystemExit("Please enter a reachable private LAN IPv4 (not loopback)")
PY

mkdir -p runtime
umask 077
if [[ -f runtime/controller.env ]]; then
  echo "runtime/controller.env already exists, refusing to overwrite secrets." >&2
  echo "Reuse the existing configuration or back it up explicitly." >&2
  exit 1
fi
if [[ -f runtime/worker-base.env ]]; then
  echo "Existing worker-base.env detected; refusing secret rotation." >&2
  exit 1
fi
TOKENS="$(python3 - <<'PY'
import secrets
for _ in range(3):
    print(secrets.token_urlsafe(36))
PY
)"
REDIS_PASSWORD="$(printf '%s\n' "$TOKENS" | sed -n '1p')"
INGEST_TOKEN="$(printf '%s\n' "$TOKENS" | sed -n '2p')"
ADMIN_TOKEN="$(printf '%s\n' "$TOKENS" | sed -n '3p')"
cat > runtime/controller.env <<EOF
CONTROLLER_IP=$HOST
REDIS_PASSWORD=$REDIS_PASSWORD
INGEST_TOKEN=$INGEST_TOKEN
ADMIN_TOKEN=$ADMIN_TOKEN
OPENSEARCH_HEAP=1g
EOF
cat > runtime/worker-base.env <<EOF
CONTROLLER_IP=$HOST
REDIS_HOST=$HOST
REDIS_PASSWORD=$REDIS_PASSWORD
API_URL=http://$HOST:8000
INGEST_TOKEN=$INGEST_TOKEN
DOMAIN_DELAY_MS=3000
WORKER_CONCURRENCY=4
SCRAPY_LOG_LEVEL=INFO
EOF
bash scripts/init-worker.sh ubuntu-a "$HOST" runtime/worker-base.env
echo
echo "Controller config generated (permissions restricted to current user)."
echo "Copy runtime/worker-base.env to Ubuntu B and Mac over SCP/SSH."
echo "Start: bash scripts/up-controller.sh"
echo "Then:  bash scripts/up-worker.sh"
echo "Do not commit, paste publicly, or expose runtime/*.env."
