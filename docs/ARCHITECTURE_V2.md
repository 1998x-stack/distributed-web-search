# Route B V2 — architecture and invariants

## LAN architecture

```text
                 BROWSER -> Ubuntu A :3000
                              |
Ubuntu A (192.168.1.101)     |   Ubuntu B (192.168.1.102)
 ┌────────────────────────────┐   ┌─────────────────────────────┐
 │ Next.js -> FastAPI :8000   │   │ Scrapy Worker B             │
 │ Redis :6379                │   │ OpenSearch os-b             │
 │ Scheduler V2               │   │ data,ingest,cluster_manager │
 │ Scrapy Worker A            │   │ transport :9300             │
 │ OpenSearch os-a            │   └─────────────────────────────┘
 │ data,ingest,cluster_manager│                  ^
 │ transport :9300            │                  |
 └────────────────────────────┘                  |
                ^                                |
                +------- LAN TCP 9300 -----------+
                |
 macOS C (192.168.1.103): Scrapy Worker C + OpenSearch os-c (cluster_manager only)
```

Two **data nodes** store two primary shards and one replica each; replicas should be placed on a different host from their primaries. Three **voting candidates** participate in manager election, of which two are Ubuntu always-on. Mac sleeps are expected; Mac is not a data-hosting node. Bootstrap configuration must be identical on first formation and removed once elected. OpenSearch documentation: https://docs.opensearch.org/latest/tuning-your-cluster/discovery-cluster-formation/bootstrapping/

Transport peer discovery uses each host's **LAN routable IPv4 address on TCP 9300**, not Docker container IP. OpenSearch HTTP port 9200 remains accessible only inside Ubuntu A's local Docker network, and is NOT exposed to LAN.

## Redis V2 state machine

```text
DISCOVERED -> ACTIVE (XADD) -> FETCHED -> INDEXED -> FINISH -> DUE(zset)
                 |                            ^               |
                 +--> RETRY(delay ZSET) ------+               |
                 |                                            |
                 +--> DEADLETTER (max attempts)               |
                                                              |
                 <-------------- SCHEDULER -------------------+
```

- `dws:v2:seen`: exact canonical URL keys (no Bloom false positives).
- `dws:v2:site:<sha>`: per-host discovery count cap, distinct from revisit counts.
- `dws:v2:active`: inflight stream jobs; protects scheduled duplicates.
- `dws:v2:frontier` + `dws-v2-workers`: Redis Streams consumer group and PEL.
- `dws:v2:payloads`: per-URL serializable next attempt/recrawl metadata.
- `dws:v2:due`: ZSET of URL next eligible dispatch times.
- `dws:v2:deadletters`: tasks exceeding retry limit.
- `dws:v2:worker:<id>`: TTL-backed heartbeat.
- `dws:v2:rate:<host>`: Lua global next-slot for each hostname, no per-process-only limiter.

Each new URL uses ONE Lua transaction to atomically reserve site capacity, mark active and append a stream entry. A successful index write uses a stable SHA256 URL document id, queues discovered URLs using idempotent dedup, and **atomically** acknowledges+deletes the parent stream entry, releases active, and adds a future recrawl. A failed fetch similarly atomically ACKs and schedules an exponential retry. A killed worker leaves the message pending for `XAUTOCLAIM` after 120 seconds. This gives *at least once* processing, not exactly once. For large crawls, Redis Sets/ZSET/HASH memory is the bottleneck.

## Search, updates, deletion

Index `dws-pages-v2`: 2 primaries, 1 replica, `analysis-icu` analyzer, BM25 title boost 4×, description 2×. The API uses a **different index name** to keep V1 data untouched. On 404/410 or noindex pages, Workers call token-protected DELETE before acknowledging. Search outputs safe plaintext summaries; the browser does not evaluate untrusted HTML.

## Failure model

| Event | Expected behavior |
|---|---|
| Mac sleeps | Ubuntu A+B retain manager majority; crawler C unavailable |
| Ubuntu B down, Mac awake | A+C can elect manager; replica stored on A permits reads, index likely yellow |
| Ubuntu A down | API/Web/Redis inaccessible even if B+C retain OpenSearch |
| B down AND Mac sleeps | A alone lacks voting majority; search may fail |
| Worker process crash | PEL re-claimed after idle threshold |
| Temporary remote 429/503 | delayed exponential retry |
| Stale HTTP 404/410 | document removed; future check after 7 days |
| Page gains noindex | old document removed and crawl policy followed |

All indexes require backups/snapshots; OpenSearch replicas are not backups. This V2 stack does NOT guarantee controller failover.

## Security and operational boundaries

Run solely on trusted LAN with inbound ACLs, protect Redis credentials/ingest/admin tokens, disable port forwarding and restrict cluster TCP 9300 to member host IPs. OpenSearch Security plugin is disabled for cross-host lab simplicity. Firewall rules must account for Docker port-publishing behavior, which can bypass conventional Ubuntu UFW INPUT rules; validate the actual packet path.

Scrapy obeys robots.txt, common robots meta and X-Robots-Tag. Fetch redirects/cookies are disabled; DNS public IP validation happens before request, but DNS rebinding between validation and connect remains an unsolved TOCTOU issue. Do not let untrusted users freely submit arbitrary URL seeds. V2 is scoped to operator-approved domains. No full canonical/sitemap support or user-agent-specific removal protocol.

For V3: independent API/Redis failover, transactional site scheduler, web archive/WARC, PageRank, LTR, snapshots, full crawler DNS pinning, richer crawl politeness and operator dashboard.
