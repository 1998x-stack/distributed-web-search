#!/usr/bin/env bash
# Usage: bash scripts/deploy.sh ubuntu-a IP_A IP_B IP_C
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ $# -ne 4 ]]; then
  echo "Usage: bash scripts/deploy.sh <ubuntu-a|ubuntu-b|macos-c> <IP_A> <IP_B> <IP_C>" >&2
  exit 2
fi
NODE_ID="$1"; IP_A="$2"; IP_B="$3"; IP_C="$4"
command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
docker info >/dev/null || { echo "Docker daemon/Desktop is not running." >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 is required." >&2; exit 1; }

case "$NODE_ID" in
  ubuntu-a) NODE_IP="$IP_A"; VOLUME=route_a_ubuntu_a_data ;;
  ubuntu-b) NODE_IP="$IP_B"; VOLUME=route_a_ubuntu_b_data ;;
  macos-c)  NODE_IP="$IP_C"; VOLUME=route_a_macos_c_data ;;
  *) echo "Unknown node ID" >&2; exit 2 ;;
esac
case "$(uname -s)" in
  Darwin) [[ "$NODE_ID" == "macos-c" ]] || { echo "Use macos-c on macOS" >&2; exit 2; } ;;
  Linux) [[ "$NODE_ID" != "macos-c" ]] || { echo "Use ubuntu-a/b on Linux" >&2; exit 2; } ;;
  *) echo "Only Ubuntu/Linux and macOS are supported" >&2; exit 2 ;;
esac

# The current latest image is multi-platform (linux/amd64 and linux/arm64).
# Override YACY_IMAGE to pin an immutable platform-specific digest if desired.
IMAGE="${YACY_IMAGE:-yacy/yacy_search_server:latest}"
echo "Pulling official YaCy image: $IMAGE"
docker pull "$IMAGE"

mkdir -p runtime
UPSTREAM="$(mktemp)"
trap 'rm -f "$UPSTREAM"' EXIT
docker run --rm --entrypoint cat "$IMAGE" \
  /opt/yacy_search_server/defaults/yacy.init > "$UPSTREAM"
bash scripts/render-config.sh "$NODE_ID" "$IP_A" "$IP_B" "$IP_C" "$UPSTREAM" runtime

# Never silently reuse an unrelated YaCy index/data volume (freeworld, etc.).
if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  STORED="$(docker run --rm --entrypoint sh \
    -v "$VOLUME:/opt/yacy_search_server/DATA:ro" "$IMAGE" -c \
    'if [ -f /opt/yacy_search_server/DATA/SETTINGS/yacy.conf ]; then grep -E "^network.unit.definition[[:space:]]*=" /opt/yacy_search_server/DATA/SETTINGS/yacy.conf || true; fi')"
  if [[ -n "$STORED" && "$STORED" != "network.unit.definition=defaults/yacy.network.route-A.unit" && "$STORED" != "network.unit.definition = defaults/yacy.network.route-A.unit" ]]; then
    echo "Existing volume has incompatible network setting: $STORED" >&2
    echo "Use a clean volume or migrate manually. Existing index was NOT modified." >&2
    exit 1
  fi
fi

# Refuse to replace another node's local configuration.
if [[ -f .env ]] && ! grep -Fxq "NODE_ID=$NODE_ID" .env; then
  echo ".env belongs to another node; refusing overwrite." >&2
  exit 1
fi
cat > .env <<EOF
NODE_ID=$NODE_ID
YACY_IMAGE=$IMAGE
YACY_VOLUME_NAME=$VOLUME
YACY_HTTP_PORT=8090
BIND_ADDRESS=0.0.0.0
YACY_JAVASTART_XMX=Xmx1500m
EOF

docker volume create "$VOLUME" >/dev/null
# Prepare writable host-customized HTTP document directory on the volume.
docker run --rm --user root --entrypoint sh \
  -v "$VOLUME:/opt/yacy_search_server/DATA" "$IMAGE" -c \
  'mkdir -p /opt/yacy_search_server/DATA/HTDOCS && chown yacy:yacy /opt/yacy_search_server/DATA /opt/yacy_search_server/DATA/HTDOCS'
docker compose -f infra/compose.yml --env-file .env config --quiet
docker compose -f infra/compose.yml --env-file .env up -d

echo
echo "Node: $NODE_ID | IP: $NODE_IP | Network: homeweb"
echo "Search: http://$NODE_IP:8090/"
echo "Network: http://$NODE_IP:8090/Network.html"
echo "Seed: http://$NODE_IP:8090/seed.txt"
echo "IMPORTANT: Change YaCy default admin password immediately at /ConfigAccounts_p.html"
if [[ "$NODE_ID" == "ubuntu-a" ]]; then
  echo "WAIT for A to generate a non-empty seed list before deploying Ubuntu B."
fi
