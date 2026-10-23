#!/usr/bin/env bash
# Display index health AND expected three-node participation from Ubuntu A.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f runtime/controller.env ]] || { echo "Run on Ubuntu A" >&2; exit 1; }
# shellcheck disable=SC1091
source runtime/controller.env
echo "== Search index cluster =="
curl --fail-with-body --show-error -fsS "http://$CONTROLLER_IP:8000/api/v1/cluster"
printf '\n== Crawler cluster ==\n'
curl --fail-with-body --show-error -fsS "http://$CONTROLLER_IP:8000/api/v1/stats"
printf '\n'
echo "Expect os-a, os-b, os-c when all nodes are awake; expect 2 data nodes."
echo "Expect ubuntu-a, ubuntu-b, macos-c Worker heartbeats while running."
