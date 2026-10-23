#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f runtime/worker.env ]] || { echo "Run scripts/init-worker.sh first" >&2; exit 1; }
bash scripts/preflight.sh
docker compose --project-name dws-worker -f deploy/worker.yml up -d --build
echo "Worker started. Inspect logs:"
echo " docker compose --project-name dws-worker -f deploy/worker.yml logs -f --tail=100"
