#!/usr/bin/env bash
# Offline smoke check: no Docker necessary.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for node in ubuntu-a ubuntu-b macos-c; do
  bash "$ROOT/scripts/render-config.sh" "$node" 192.168.1.101 192.168.1.102 192.168.1.103 \
    "$ROOT/tests/fixtures/yacy.init" "$TMP/$node"
done
cmp "$TMP/ubuntu-a/yacy.network.route-A.unit" "$TMP/ubuntu-b/yacy.network.route-A.unit"
cmp "$TMP/ubuntu-a/yacy.network.route-A.unit" "$TMP/macos-c/yacy.network.route-A.unit"
grep -qx 'seedUploadMethod=File' "$TMP/ubuntu-a/yacy.init"
grep -qx 'seedUploadMethod=File' "$TMP/ubuntu-b/yacy.init"
grep -qx 'seedUploadMethod=none' "$TMP/macos-c/yacy.init"
grep -qx 'network.unit.definition=defaults/yacy.network.route-A.unit' "$TMP/ubuntu-a/yacy.init"
! grep -E '^network.unit.bootstrap.seedlist[0-9]+' "$TMP/ubuntu-a/yacy.network.route-A.unit" | grep -q 'yacy.net'
echo "Offline config smoke test: PASS"
