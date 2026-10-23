# LAN deployment — exact operator runbook

Prerequisites: Ubuntu A recommended 16–32 GB RAM, >50 GB SSD, Ubuntu B >=8 GB, macOS Docker Desktop (Intel or Apple Silicon) >=4 GB spare. Require Docker Engine + Compose v2 on Ubuntu and Docker Desktop on Mac. All three hosts must be able to reach Ubuntu A IP on TCP 6379 and 8000. Browser reaches Ubuntu A on TCP 3000. No ports are needed inbound on B or Mac.

### Step 0: assign stable LAN addresses

Example only: `IP_A=192.168.1.101`, `IP_B=192.168.1.102`, `IP_C=192.168.1.103`. Reserve A's IP in router DHCP or use static IP. `hostname -I` on Ubuntu; `ipconfig getifaddr en0` on a Wi-Fi Mac.

### Step 1: Ubuntu A controller

```bash
git clone -b route-B-v1 https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-dws-opensearch.conf
bash scripts/init-controller.sh 192.168.1.101
bash scripts/up-controller.sh
bash scripts/up-worker.sh
```

Initial image pulls/builds can take several minutes, especially OpenSearch + ICU plugin. The controller uses Redis AOF, persistent OpenSearch, separate HTTP API and Node Web. Wait for `curl -f http://192.168.1.101:8000/api/v1/health` to respond with `{"status":"ok"}`.

Controller initializes `runtime/controller.env` (admin, ingest and Redis secrets), `runtime/worker-base.env` (only worker-required credentials) and `runtime/worker.env` (worker A). All are ignored by git and chmod 600.

### Step 2: copy worker credentials over SSH, Ubuntu B

On Ubuntu B:

```bash
git clone -b route-B-v1 https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
mkdir -p runtime && chmod 700 runtime
scp YOUR_USER@192.168.1.101:~/distributed-web-search/runtime/worker-base.env runtime/worker-base.env
chmod 600 runtime/worker-base.env
bash scripts/init-worker.sh ubuntu-b 192.168.1.101 runtime/worker-base.env
bash scripts/up-worker.sh
```

Replace YOUR_USER with the SSH user on Ubuntu A. The `scp` path assumes the repository was cloned under that user's home directory. If SSH isn't available, use another encrypted transfer mechanism; **never send credentials via plain text chat or commit them to GitHub**.

### Step 3: copy worker credentials over SSH, macOS

On Mac:

```bash
git clone -b route-B-v1 https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
mkdir -p runtime && chmod 700 runtime
scp YOUR_USER@192.168.1.101:~/distributed-web-search/runtime/worker-base.env runtime/worker-base.env
chmod 600 runtime/worker-base.env
bash scripts/init-worker.sh macos-c 192.168.1.101 runtime/worker-base.env
bash scripts/up-worker.sh
open http://192.168.1.101:3000
```

Docker Desktop must be running. The Mac worker initiates outbound connections to A; no custom docker overlay network or cross-host bridge is necessary. Mac sleeps cause this worker to go offline, which is acceptable.

### Step 4: start crawl on Ubuntu A

First verify `robots.txt` and your right to crawl the target. Suggested start: a small, permitted HTML documentation site under your control.

```bash
bash scripts/add-seed.sh https://YOUR_AUTHORIZED_PUBLIC_DOMAIN/ 1 100
bash scripts/check-cluster.sh
```

The operator API enqueues once per canonical URL. Workers all draw jobs from the same Redis Stream. Wait for index refresh, then search at `http://IP_A:3000`.

### Step 5: evaluate

- All 3 worker IDs appear in `/api/v1/stats` after they start.
- `known_urls` should increase when page links are discovered.
- `indexed_pages` should increase after successful fetch + parse + ingest.
- Query a distinct word found in one indexed webpage; search results link to the original URL.
- Stop one worker: the other two continue to consume newly queued tasks. Unacknowledged messages may be reassigned after ~120 seconds.
- Web and API remain available when Mac sleeps.

**Do not interpret `queued_events_total` as the number of currently waiting jobs:** Redis Streams retain acknowledged entries until trimmed. `pending_acks` reflects unacknowledged delivered tasks.

### Node diagnostics

```bash
docker compose --env-file runtime/controller.env -f deploy/controller.yml ps
docker compose --env-file runtime/controller.env -f deploy/controller.yml logs -f --tail=100
docker compose -p dws-worker -f deploy/worker.yml logs -f --tail=100
curl -fsS http://192.168.1.101:8000/api/v1/stats
```

### Networking and security

Restrict Ubuntu A TCP 3000, 6379, 8000 to your actual trusted LAN client/worker addresses using router and host firewall rules (Docker published port rules can bypass ordinary UFW INPUT restrictions; validate DOCKER-USER/nftables policy as applicable). Never forward Redis/API ports to the Internet. OpenSearch has no host-published port.

For backups, stop writes before snapshotting OpenSearch volume and Redis AOF volume. Do not use `docker compose down -v` unless you explicitly intend irreversible data deletion. Future production deployments should configure TLS and API limits/ACLs.

### Next work

Add noindex and HTTP X-Robots handling before using arbitrary external domains; use permissioned documentation sites for the first smoke test.
