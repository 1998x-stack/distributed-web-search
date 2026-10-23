#!/usr/bin/env bash
# Run from any of the hosts after configuring worker.env or controller.env.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f runtime/worker.env ]]; then
  # shellcheck disable=SC1091
  source runtime/worker.env
elif [[ -f runtime/controller.env ]]; then
  # shellcheck disable=SC1091
  source runtime/controller.env
else
  echo "No local runtime credentials. Initialize this host first." >&2; exit 1
fi
echo "== LAN API =="
curl --fail-with-body --max-time 10 --show-error --silent "http://$CONTROLLER_IP:8000/api/v1/health"
printf '\n== Cluster stats ==\n'
curl --fail-with-body --max-time 10 --show-error --silent "http://$CONTROLLER_IP:8000/api/v1/stats"
printf '\n'
echo "Check the workers array for ubuntu-a, ubuntu-b and macos-c (must each be live)."
