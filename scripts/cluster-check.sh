#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo "Usage: bash scripts/cluster-check.sh IP_A IP_B IP_C" >&2; exit 2
fi
failures=0
for entry in "ubuntu-a:$1" "ubuntu-b:$2" "macos-c:$3"; do
  name="${entry%%:*}"; ip="${entry#*:}"
  echo "== $name ($ip) =="
  if code="$(curl -L --max-time 12 --connect-timeout 4 -sS -o /dev/null -w '%{http_code}' "http://$ip:8090/")"; then
    echo "  HTTP search home: $code"
    [[ "$code" =~ ^2|3 ]] || failures=$((failures+1))
  else echo "  ERROR: unreachable"; failures=$((failures+1)); fi
  if code="$(curl -L --max-time 12 --connect-timeout 4 -sS -o /dev/null -w '%{http_code}' "http://$ip:8090/Network.html")"; then
    echo "  Network page: $code"
  else
    echo "  WARN: Network page unavailable or requires authentication"
  fi
done

echo "== Bootstrap (principal seed list) =="
if seed="$(curl -fsSL --max-time 15 "http://$1:8090/seed.txt")" && [[ -n "$seed" ]]; then
  echo "  A seed list: reachable, non-empty (${#seed} bytes)"
  if [[ "$seed" == *"<html"* || "$seed" == *"<!DOCTYPE"* ]]; then
    echo "  ERROR: seed URL returned HTML, not a seed list"
    failures=$((failures+1))
  fi
else
  echo "  ERROR: A seed list missing; configure File seed upload / Principal"
  failures=$((failures+1))
fi
if seed="$(curl -fsSL --max-time 15 "http://$2:8090/seed.txt")" && [[ -n "$seed" ]]; then
  echo "  B seed list: reachable, non-empty"
else
  echo "  WARN: B seed list not ready (recommended backup Principal)"
fi
echo "== Reminder =="
echo "HTTP success and seed download do NOT prove peer convergence or DHT transfer."
echo "Open each Network.html and confirm only expected homeweb peers are listed."
echo "Verify remote crawler jobs, index receive/send counters and cross-peer search."
if (( failures > 0 )); then exit 1; fi
