#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f runtime/controller.env ]] || { echo "Run scripts/init-controller.sh first" >&2; exit 1; }
[[ -f runtime/search.env && -f runtime/opensearch.yml ]] || {
  echo "Run python3 scripts/render-os-config.py os-a IP_A IP_B IP_C first" >&2; exit 1;
}
# shellcheck disable=SC1091
source runtime/search.env
export OS_PUBLISH_IP OS_HEAP
bash scripts/preflight.sh
docker compose --env-file runtime/controller.env -f deploy/controller.yml up -d --build
# shellcheck disable=SC1091
source runtime/controller.env
echo "Web:     http://$CONTROLLER_IP:3000"
echo "API:     http://$CONTROLLER_IP:8000/api/v1/health"
echo "Cluster: http://$CONTROLLER_IP:8000/api/v1/cluster"
echo "Search node A will wait for cluster manager quorum."
