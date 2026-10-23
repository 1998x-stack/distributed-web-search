#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v docker >/dev/null || { echo "Docker not found"; exit 1; }
docker info >/dev/null || { echo "Docker daemon not reachable"; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 not installed"; exit 1; }
if [[ "$(uname -s)" == Linux ]]; then
  N="$(sysctl -n vm.max_map_count 2>/dev/null || echo 0)"
  if [[ "$N" -lt 262144 ]]; then
    echo "WARN: vm.max_map_count=$N (OpenSearch needs >=262144 on data nodes)"
    echo "  sudo sysctl -w vm.max_map_count=262144"
  fi
fi
if [[ -f runtime/controller.env ]]; then
  [[ -f runtime/opensearch.yml && -f runtime/search.env ]] || {
    echo "Missing runtime search config for Ubuntu A"; exit 1;
  }
  # shellcheck disable=SC1091
  source runtime/search.env
  export OS_PUBLISH_IP OS_HEAP
  docker compose --env-file runtime/controller.env -f deploy/controller.yml config --quiet
  echo "Controller Compose: valid"
fi
if [[ -f runtime/worker.env ]]; then
  docker compose -f deploy/worker.yml config --quiet
  echo "Worker Compose: valid"
fi
echo "Preflight: PASS"
