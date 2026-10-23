#!/usr/bin/env bash
# Ubuntu B or macOS C: run cluster manager/data-node outside of controller.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f runtime/search.env && -f runtime/opensearch.yml ]] || {
  echo "Run scripts/render-os-config.py on this host first." >&2; exit 1;
}
# shellcheck disable=SC1091
source runtime/search.env
export OS_PUBLISH_IP OS_HEAP
case "$OS_NODE" in
  os-b) [[ "$(uname -s)" == Linux ]] || { echo "os-b requires Ubuntu/Linux"; exit 2; }
        FILE=deploy/search-node.yml ;;
  os-c) [[ "$(uname -s)" == Darwin ]] || { echo "os-c requires macOS"; exit 2; }
        FILE=deploy/witness.yml ;;
  *) echo "This is only for os-b (Ubuntu B) or os-c (macOS)"; exit 2 ;;
esac
docker info >/dev/null
docker compose -f "$FILE" config --quiet
docker compose -f "$FILE" up -d --build
echo "Started $OS_NODE at $OS_PUBLISH_IP:9300 (TCP transport only)."
