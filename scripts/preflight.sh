#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v docker >/dev/null || { echo "Docker not found"; exit 1; }
docker info >/dev/null || { echo "Docker daemon not reachable"; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 not installed"; exit 1; }
if [[ "$(uname -s)" == "Linux" ]]; then
  N="$(sysctl -n vm.max_map_count 2>/dev/null || echo 0)"
  if [[ "$N" -lt 262144 ]]; then
    echo "WARN: vm.max_map_count=$N; set to >=262144 on Ubuntu A:"
    echo "  sudo sysctl -w vm.max_map_count=262144"
    echo "  echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-dws-opensearch.conf"
  fi
fi
if [[ -f runtime/controller.env ]]; then
  docker compose --env-file runtime/controller.env -f deploy/controller.yml config --quiet
  echo "Controller Compose validation: PASS"
fi
if [[ -f runtime/worker.env ]]; then
  docker compose -f deploy/worker.yml config --quiet
  echo "Worker Compose validation: PASS"
fi
echo "Preflight complete"
