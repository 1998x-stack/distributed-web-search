# Distributed Web Search — Route B V2

**两台 Ubuntu + 一台 macOS 同一局域网内的独立搜索引擎。** V2 is an implementation branch based on `route-B-v1`, with Redis delayed retries and recrawls, two OpenSearch **data** nodes (with one replica per shard), and a Mac **cluster-manager-only** voting node. All three hosts also run crawler Workers.

[Hardening audit](docs/HARDENING_AUDIT.md) · [Deployment](docs/DEPLOYMENT_V2.md) · [Architecture](docs/ARCHITECTURE_V2.md) · [Acceptance tests](docs/VERIFY_V2.md) · [V1→V2 migration](docs/MIGRATION_V2.md)

## Key differences from V1

| Area | V1 | V2 |
|---|---|---|
| Scrapy crawling | 3 workers | 3 workers + scheduled recrawls |
| Queue | Redis Streams + PEL | atomic delayed retry ZSET + Streams + recovery |
| Index | 1 shard, no replicas, Ubuntu A | 2 shards + 1 replica, Ubuntu A and B |
| Voting | single-node | manager candidates A, B, Mac C (quorum) |
| Fetch fail | PEL timeout + claim | exponential delayed retry and deadletter |
| 404/410 | ignored | remove old search document |
| noindex on recrawl | skip indexing | remove old indexed document |
| Index namespace | dws-pages-v1 | dws-pages-v2 (no implicit migration) |
| URL namespace | dws:v1:* | dws:v2:* |

## Deployment preview (replace sample LAN IPs)

Prerequisites: Docker Engine/Compose on both Ubuntu PCs, Docker Desktop on Mac; Python 3 + PyYAML on all three hosts; 8090 is **not** used in Route B; TCP 9300 reachable between all three machines; Ubuntu A API TCP 8000, Redis TCP 6379, Web TCP 3000 reachable over trusted LAN.

Clone on **each** machine:

```bash
git clone --branch route-B-v2 --single-branch https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
python3 -m pip install --user pyyaml
```

**Ubuntu A** (scheduler + redis + API + Web + OS data A + Scrapy):

```bash
sudo sysctl -w vm.max_map_count=262144
bash scripts/init-controller.sh 192.168.1.101
python3 scripts/render-os-config.py os-a 192.168.1.101 192.168.1.102 192.168.1.103
bash scripts/up-controller.sh
bash scripts/up-worker.sh
```

**Ubuntu B** (OS data B + Scrapy): copy `worker-base.env` securely from Ubuntu A over SCP after controller init.

```bash
mkdir -p runtime
scp YOUR_USER@192.168.1.101:~/distributed-web-search/runtime/worker-base.env runtime/worker-base.env
bash scripts/init-worker.sh ubuntu-b 192.168.1.101 runtime/worker-base.env
python3 scripts/render-os-config.py os-b 192.168.1.101 192.168.1.102 192.168.1.103
bash scripts/up-search-node.sh
bash scripts/up-worker.sh
```

**Mac C** (OS voting manager + Scrapy):

```bash
mkdir -p runtime
scp YOUR_USER@192.168.1.101:~/distributed-web-search/runtime/worker-base.env runtime/worker-base.env
bash scripts/init-worker.sh macos-c 192.168.1.101 runtime/worker-base.env
python3 scripts/render-os-config.py os-c 192.168.1.101 192.168.1.102 192.168.1.103
bash scripts/up-search-node.sh
bash scripts/up-worker.sh
open http://192.168.1.101:3000
```

On Ubuntu A, verify `/api/v1/cluster` returns **3 nodes / 2 data nodes** while Mac is awake. Once the cluster is fully formed, remove `cluster.initial_cluster_manager_nodes` from each node's config with the `--post-bootstrap` rendering option (see full runbook for safe restart order).

Then add a permitted seed from Ubuntu A:

```bash
bash scripts/add-seed.sh https://YOUR_AUTHORIZED_PUBLIC_DOMAIN/ 1 100
bash scripts/cluster-inspect.sh
```

The browser search service remains `http://192.168.1.101:3000`.

## Major limitations / security boundary

**V2 has replicated search shards, not full high availability.** Redis, web and API still depend on Ubuntu A; B and C do not replace the controller. The Mac witness may sleep as long as both Ubuntu manager voters stay up, but losing one Ubuntu during that sleep loses majority. Never interpret a green index as guaranteed backup: take off-site snapshots and test restore.

OpenSearch Security plugin is deliberately disabled; **only TCP 9300** is exposed to trusted hosts for OpenSearch cluster transport. **Never publicly port-forward 9300, 6379 or 8000.** This is a lab reference, not a hardened untrusted multi-tenant crawler. Crawling arbitrary websites is allowed only to the extent their rules and applicable permissions allow it. SSRF has DNS-rebinding caveats that require outbound network isolation to harden further.

**Do not mount/reuse V1 Redis or OpenSearch named volumes.** All V2 data has separate names and new index/stream namespaces. Running a fresh V2 stack does not import old indexes.

Live cluster formation, failover and crawling have not yet been tested on your own LAN; CI exercises code, Redis Lua semantics, Compose rendering and front-end compilation.
