#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo "Missing .env; deploy a node first" >&2; exit 1; }
docker compose -f infra/compose.yml --env-file .env ps
echo
echo "Logs: docker compose -f infra/compose.yml --env-file .env logs -f --tail=100"
