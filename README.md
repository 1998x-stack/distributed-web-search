# Distributed Web Search · Route B V1

**三台同一局域网内的独立网页搜索引擎。** Ubuntu × 2 + macOS × 1，三台协作爬取公共且允许抓取的网页，集中索引，浏览器实时搜索。无需 Google/Baidu 结果接口，不要求 GPU。

- Crawling: **Scrapy 2.13** (one long-running worker per machine).
- Scheduling and recovery: **Redis 7 Streams**, consumer groups, Lua dedup and host-wide rate limiter, `XAUTOCLAIM`.
- Search: **OpenSearch 3 + analysis-icu**, Chinese/multilingual BM25 index.
- API: **FastAPI**, token-protected seed creation and index ingestion.
- UI: **Next.js 15 / React 19**, local search homepage.
- Runtime: **Docker Compose**, central Ubuntu A controller, Ubuntu A/B/Mac workers.

[Architecture](docs/ARCHITECTURE.md) · [Deployment manual](docs/DEPLOYMENT.md)

## LAN deployment in three commands (after Docker is installed)

Use **your real IP**, not the following illustrative one. All hosts must reach Ubuntu A TCP 6379 and 8000, and browser TCP 3000. Clone the same branch separately on each:

```bash
git clone -b route-B-v1 https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
```

**Ubuntu A** (controller + its local worker):

```bash
sudo sysctl -w vm.max_map_count=262144
bash scripts/init-controller.sh 192.168.1.101
bash scripts/up-controller.sh
bash scripts/up-worker.sh
```

**Ubuntu B** (copy worker credentials from A over SSH first):

```bash
mkdir -p runtime
scp YOUR_USER@192.168.1.101:~/distributed-web-search/runtime/worker-base.env runtime/worker-base.env
bash scripts/init-worker.sh ubuntu-b 192.168.1.101 runtime/worker-base.env
bash scripts/up-worker.sh
```

**macOS** (Docker Desktop started; copy worker credentials from A):

```bash
mkdir -p runtime
scp YOUR_USER@192.168.1.101:~/distributed-web-search/runtime/worker-base.env runtime/worker-base.env
bash scripts/init-worker.sh macos-c 192.168.1.101 runtime/worker-base.env
bash scripts/up-worker.sh
open http://192.168.1.101:3000
```

A more detailed runbook with system prerequisites, security and network checking is in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

On **Ubuntu A** after checking crawl permissions:

```bash
bash scripts/add-seed.sh https://YOUR_AUTHORIZED_PUBLIC_DOMAIN/ 1 100
bash scripts/check-cluster.sh
```

Visit `http://192.168.1.101:3000` to search. API status lives at `http://192.168.1.101:8000/api/v1/stats`.

## Design choices

- All hosts can fetch from the same Redis Stream. No task allocation by machine IP, no multi-host Docker overlay network, no Kubernetes.
- All machines are workers; only Ubuntu A owns the Redis queue, OpenSearch index, FastAPI and web app.
- Index uses one primary shard / zero replicas: this is **distributed crawling, not distributed search storage**, as requested for V1.
- First crawl is intentionally limited to the **exact seed hostname**, `max_depth` and `max_pages`. Redirects, cookies, non-HTTP protocols and private IPs are blocked; robots.txt is respected.
- No continuous recrawl, semantic search, distributed OpenSearch, or login UI in V1.

## Important security and implementation limits

This is a **trusted LAN research environment**, not a hardened public search SaaS. Redis and API work over LAN plaintext, OpenSearch is isolated behind the Docker network, and remote worker API writes are token-authenticated. Never forward ports 6379/8000 to public networks. Common HTML robots meta and X-Robots-Tag noindex/nofollow are implemented; before crawling third-party websites at scale, complete per-agent robots semantics, removal requests and stronger DNS rebinding protection. Respect website policies and crawl only authorized sources.

**Validation status:** GitHub CI runs unit tests, Python syntax, Next build and Docker Compose config. These tests cannot prove successful 3-host operation on your hardware; after deployment, verify workers, indexing, failover and query results using the runbook.
