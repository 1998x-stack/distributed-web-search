# Route B V2 — three-host LAN deployment

**These commands are meant to run on three different computers, using their ACTUAL LAN IPv4 addresses.** Replace all sample addresses and SSH usernames.

## Resource requirements and IP planning

| Host | Software | Approx. recommended free RAM |
|---|---|---|
| Ubuntu A 192.168.1.101 | Redis, FastAPI, Next.js, scheduler, crawler, os-a | 16 GB+ |
| Ubuntu B 192.168.1.102 | crawler, os-b | 8 GB+ |
| Mac C 192.168.1.103 | crawler, manager-only os-c | 4 GB+ available to Docker Desktop |

The two Ubuntu machines should be continuously online. The Mac may sleep during routine crawling; for tests requiring all three voters, keep it awake.

- Ubuntu A should allow trusted clients to TCP **3000**, **8000**, **6379** and peers to TCP **9300**.
- Ubuntu B & Mac C allow **9300** from the other two nodes (only OpenSearch transport, no 9200).
- Redis credentials are transferred over SSH; never expose `runtime/*.env` via Git.
- Set `vm.max_map_count>=262144` on both Ubuntu machines, including across reboot using `/etc/sysctl.d/`.
- Mac Docker Desktop needs adequate VM memory and port-forwarding of 9300; validate actual LAN inbound connectivity, not merely localhost reachability.

## 1. Clone on each computer

```bash
git clone -b route-B-v2 https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
python3 -m pip install --user pyyaml
```

For Ubuntu where system Python is externally managed, create and activate an isolated Python venv instead of forcing a system install:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install pyyaml
```

## 2. Ubuntu A

```bash
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-dws-opensearch.conf
bash scripts/init-controller.sh 192.168.1.101
python3 scripts/render-os-config.py os-a 192.168.1.101 192.168.1.102 192.168.1.103
bash scripts/up-controller.sh
bash scripts/up-worker.sh
```

Controller startup may temporarily show API restart logs if the initial OpenSearch manager election has not completed; launch Ubuntu B promptly. Initial cluster manager election needs 2 of 3 listed voters. The Mac may join before or after initial A+B election.

## 3. Ubuntu B

```bash
sudo sysctl -w vm.max_map_count=262144
mkdir -p runtime && chmod 700 runtime
scp YOUR_USER@192.168.1.101:~/distributed-web-search/runtime/worker-base.env runtime/worker-base.env
chmod 600 runtime/worker-base.env
bash scripts/init-worker.sh ubuntu-b 192.168.1.101 runtime/worker-base.env
python3 scripts/render-os-config.py os-b 192.168.1.101 192.168.1.102 192.168.1.103
bash scripts/up-search-node.sh
bash scripts/up-worker.sh
```

If Python is in a virtual environment, use `python` rather than `python3`. The renderer only writes YAML configuration and a local env file, no private secrets.

## 4. Mac C

```bash
mkdir -p runtime && chmod 700 runtime
scp YOUR_USER@192.168.1.101:~/distributed-web-search/runtime/worker-base.env runtime/worker-base.env
chmod 600 runtime/worker-base.env
bash scripts/init-worker.sh macos-c 192.168.1.101 runtime/worker-base.env
python3 scripts/render-os-config.py os-c 192.168.1.101 192.168.1.102 192.168.1.103
bash scripts/up-search-node.sh
bash scripts/up-worker.sh
open http://192.168.1.101:3000
```

## 5. Verify and end bootstrap phase

On Ubuntu A, the API must report a formed cluster:

```bash
bash scripts/cluster-inspect.sh
curl -fsS http://192.168.1.101:8000/api/v1/cluster
```

Expected while all awake: `number_of_nodes=3`, `number_of_data_nodes=2`, nodes `os-a, os-b, os-c`, eventually `status=green`. When os-c is sleeping A+B can maintain a manager majority, but this is not a guarantee against two simultaneous losses.

**Important OpenSearch procedure:** after the cluster has formed and survived one health check, remove the initial bootstrap list from **each** node's `opensearch.yml`:

```bash
# Run on Ubuntu A, in repo directory
python3 scripts/render-os-config.py os-a 192.168.1.101 192.168.1.102 192.168.1.103 --post-bootstrap

# Run on Ubuntu B
python3 scripts/render-os-config.py os-b 192.168.1.101 192.168.1.102 192.168.1.103 --post-bootstrap

# Run on Mac
python3 scripts/render-os-config.py os-c 192.168.1.101 192.168.1.102 192.168.1.103 --post-bootstrap
```

After confirming the stored cluster state exists, restart **one OpenSearch node at a time** (B, then Mac, then A), and wait for manager quorum/cluster health after each restart. On A:

```bash
docker compose --env-file runtime/controller.env -f deploy/controller.yml restart opensearch
```

On B/C (with `runtime/search.env` exported per up-search-node script):

```bash
bash scripts/up-search-node.sh
```

**Never clear the data volumes as part of this procedure.** If the cluster is not yet formed, do not remove initial bootstrapping settings. Avoid reusing the bootstrap config to start brand new clusters on old data.

## 6. Crawl and search

```bash
# Ubuntu A: authorized test website
bash scripts/add-seed.sh https://YOUR_AUTHORIZED_PUBLIC_DOMAIN/ 1 100
bash scripts/check-cluster.sh
bash scripts/cluster-inspect.sh
```

Search at `http://192.168.1.101:3000`. To observe distributed index actual allocation, inspect the `/api/v1/cluster` response; for exact per-shard allocation use an authenticated exec inside OS container with `/_cat/shards/dws-pages-v2?v`. Do NOT expose raw OpenSearch HTTP 9200 to public LAN.

## 7. Fault testing

1. With 3 nodes awake and green status, shut down Mac `os-c`. Observe A+B retain majority.
2. Restart Mac; observe 3 node convergence.
3. Stop Ubuntu B data node briefly, with Mac awake; verify index can still serve queries from A with reduced redundancy.
4. Never simultaneously interrupt A and B during these tests, because Redis/API/web lives on A.
5. Stop one Scrapy Worker and observe queued tasks claimed by another after 120 seconds; verify unique URL results remain stable.

## 8. V1 to V2 considerations

Read [MIGRATION_V2.md](MIGRATION_V2.md). The V2 index is a separate index; no automatic V1 OpenSearch index or queue migration. Do not use `down -v` or delete old volumes until restored and verified.

## 9. Operational safety

Restrict TCP 9300 to only cluster hosts. Because Docker bypasses some firewall frontends, verify at the host DOCKER-USER/nftables chains and upstream switch/firewall. Redis TCP 6379 should accept only crawler hosts. Expose API TCP 8000 only to trusted LAN clients; prefer authenticating stats endpoints before external exposure.

Increase `RECRAWL_SECONDS` in `runtime/worker.env` only after careful throughput measurement. Periodic recrawling with no content hash optimization will rewrite the same OpenSearch document even when text is unchanged. Keep initial site scope 100 documents and concurrency 4/worker.
