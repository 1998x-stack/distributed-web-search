# Distributed Web Search — Route A: YaCy

A deployable **three-host private YaCy P2P search experiment** using Ubuntu A + Ubuntu B + macOS C. This branch keeps the original YaCy search/crawl UI rather than rebuilding a separate front end.

**What it delivers:** isolated network definition (not `freeworld`), three independent YaCy instances, two potential Principal seed publishers, persistent named volumes, a reproducible deployment command per machine, health checks, backup and offline CI validation.

**Important limitation:** joining three peers does not guarantee YaCy will immediately transfer index blocks through its DHT, and remote crawling does **not** automatically load balance all crawl URLs. Peer discovery, remote search, remote crawl and DHT counters require separate runtime verification. See [verification](docs/VERIFY.md).

## Prerequisites

- Two Ubuntu/Linux machines plus a Mac, each running **Docker Engine + Docker Compose v2** (Docker Desktop on Mac).
- A stable reachable IPv4 address for each host (LAN or a properly routed private overlay). Mac must remain awake during crawls.
- Each host must be able to reach the others on TCP **8090**. If a host's firewall blocks 8090, allow **only trusted peer/client IPs**.
- Minimum practical starting point: 4 GB free RAM per YaCy host, more for large indexes. Tune JVM heap in local `.env`.
- Fresh named volumes: script refuses incompatible existing YaCy config rather than silently joining public `freeworld`.

## Commands (run locally on each host)

Replace these **example** addresses with your actual addresses, using the **same three addresses in every command**.

**Ubuntu A — first (bootstrap / Principal):**

```bash
git clone -b route-A https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
bash scripts/deploy.sh ubuntu-a 192.168.1.101 192.168.1.102 192.168.1.103
```

Open `http://192.168.1.101:8090/Settings_p.html?page=seed`; confirm `File` seed upload and `http://192.168.1.101:8090/seed.txt`. **Do not start B until `curl -fsS http://192.168.1.101:8090/seed.txt` returns a valid, non-empty YaCy seed list and A reaches Principal**. The initial seed publish may require the administrator to save the Seed Upload settings through the UI.

**Ubuntu B — second (also Principal):**

```bash
git clone -b route-A https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
bash scripts/deploy.sh ubuntu-b 192.168.1.101 192.168.1.102 192.168.1.103
```

Confirm B joined the `homeweb` network, then configure/verify B's File seed upload `http://192.168.1.102:8090/seed.txt`. This gives new nodes a backup Bootstrap source.

**macOS — third:**

```bash
git clone -b route-A https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
bash scripts/deploy.sh macos-c 192.168.1.101 192.168.1.102 192.168.1.103
open http://localhost:8090
```

Verify from any machine:

```bash
bash scripts/cluster-check.sh 192.168.1.101 192.168.1.102 192.168.1.103
```

### URLs
- Search: `http://HOST:8090/`
- Network peers: `http://HOST:8090/Network.html`
- Crawl start: `http://HOST:8090/CrawlStart_p.html`
- Administrator password: `http://HOST:8090/ConfigAccounts_p.html`
- Seed publish: `http://HOST:8090/seed.txt`

**Immediately change the default admin password** (`admin` / `yacy`) on **each host**. Do not expose 8090 to the open Internet; no TLS reverse proxy is configured in this lab. Restrict host firewall / VPN access.

## How it works

```text
Ubuntu A (Principal) --- private seeds --- Ubuntu B (Principal)
          |                   |                     |
          +---- YaCy peers -- Mac C (crawler/search) +
               same local homeweb network definition
```

Every node runs its own YaCy crawler, Solr-backed local index and web interface. Private network parameters are rendered from the same three IPs and mounted **before initial startup**. Peer addresses are published as static reachable host IPv4s. Ubuntu A/B can publish seed lists under `DATA/HTDOCS/seed.txt`.

For safe operations and real search tests see [deployment details](docs/DEPLOYMENT.md), [verification](docs/VERIFY.md) and [architecture/limitations](docs/ARCHITECTURE.md).

## Maintenance

```bash
bash scripts/status.sh
bash scripts/backup.sh
docker compose -f infra/compose.yml --env-file .env logs -f --tail=100
docker compose -f infra/compose.yml --env-file .env stop
docker compose -f infra/compose.yml --env-file .env start
```

Backups are saved under ignored `backups/`. Upgrading an image or changing the network definition needs careful review and backups.

## Upstream references

- [YaCy server source](https://github.com/yacy/yacy_search_server)
- [YaCy custom network and bootstrap](https://www.yacy.de/operation/network-definition/)
- [YaCy Docker installation](https://yacy.net/download_installation/)
- [YaCy settings](https://yacy.net/operation/yacy_conf/)
- [YaCy LAN cluster historical notes](https://wiki.yacy.net/index.php/De:FirmenLAN)

**Verification status:** local config generation and CI are included; a live three-host test cannot be performed without access to the actual three machines. Do not label the P2P network operational solely because three containers are running.
