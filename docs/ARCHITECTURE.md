# Route B V1 — Engineering architecture

## Three-host LAN topology

```text
              192.168.1.0/24 (example LAN)
                         |
  Ubuntu A (always online)
  ┌──────────────────────────────────────────────────────┐
  │ Next.js :3000 ←→ FastAPI :8000 ←→ OpenSearch (local) │
  │                          ↑                          │
  │ Redis Streams :6379 ↔ Scrapy Worker A                │
  └───────────────┬───────────────────┬──────────────────┘
                  │                   │
          Ubuntu B                    macOS C
       Scrapy Worker B              Scrapy Worker C
          Redis/API                   Redis/API
```

- **Control plane** runs only on Ubuntu A: Web search, FastAPI indexing API, OpenSearch 3 (1 shard / 0 replicas), Redis 7 AOF, and Worker A.
- **Worker plane**: Ubuntu A/B/Mac all use the same `dws:v1:frontier` Redis Stream and consumer group `dws-workers`. Each Worker is a Scrapy 2.13 spider process; no per-node URL static splits.
- **Storage**: Indexed documents in OpenSearch (persistent named volume), queue+dedup+attempts in Redis (AOF named volume). There is **no relational database in V1**. Redis sets store URL history and per-host page cap, so they are not infinitely scalable.
- **Query flow**: browser Next.js same-origin rewrite → FastAPI GET `/api/v1/search` → OpenSearch ICU/BM25 → safe text result view.
- **Ingestion flow**: authorized seed POST → atomic Redis Lua SADD+XADD → Scrapy HTTP GET → trafilatura clean text → authenticated `POST /api/v1/documents` → OpenSearch stable SHA-256 document ID → emit same-host child URLs → XACK.
- **Failure recovery**: Messages are only acknowledged after document ingestion. At-least-once delivery plus idempotent document IDs and URL set gives safe replay; `XAUTOCLAIM` retries PEL entries after 120 seconds. A per-message attempt counter deadletters after four delivery attempts. Pending tasks may be retried after a slow response, so duplicate downloads are possible.
- **Global politeness**: Redis Lua reserves per-domain fetch slots (`DOMAIN_DELAY_MS`, default 3000). Local Scrapy also honors `robots.txt`, `noindex`-relevant page information is not yet fully enforced (see limitations below), limits active downloads and disables auto-redirect.
- **Scope**: Each submitted seed is an exact-host crawl with max_depth and max_pages. Links to other hosts are ignored, avoiding unbounded uncontrolled internet crawling.
- **Search index**: `analysis-icu` for multilingual tokenizer and BM25 default similarity. Title boosted 4×, description 2×, content normal. No embedding/GPU dependencies.

## Messages and idempotency

A job is JSON:

```json
{"url":"https://example.org/","domain":"example.org","depth":0,"max_depth":1,"max_pages":100}
```

Redis key families:

| Key | Data type | Function |
|---|---|---|
| `dws:v1:frontier` | Stream | Durable task stream |
| `dws-workers` | Consumer Group | Distributed delivery and PEL |
| `dws:v1:seen` | Set | Global exact normalized URL dedup |
| `dws:v1:site:SHA256(domain)` | Set | Per-host page cap |
| `dws:v1:rate:domain` | String TTL | Global slot reservations |
| `dws:v1:attempts` | Hash | Retry count per message |
| `dws:v1:deadletters` | Stream | Unprocessed/broken tasks |
| `dws:v1:worker:ID` | String TTL | Worker heartbeat |

Caveat: acknowledged stream entries are not automatically pruned in V1. Growth should be monitored (`XLEN`, AOF and memory) before increasing crawl volume.

## Security boundaries

- The public search path is read-only. `/api/v1/seeds` requires `ADMIN_TOKEN`, and `/api/v1/documents` requires a distinct `INGEST_TOKEN`.
- URL policy accepts HTTP(S) only, no URL userinfo, no non-global IP literals, and no localhost/.local/.internal. Before every Scrapy request, public DNS answers are checked (fails closed on mixed public/private addresses). Scrapy redirects/meta refresh and cookies are disabled.
- This is **not** complete DNS-rebinding protection: an attacker-controlled DNS answer may change between validation and socket connect. Use worker egress firewall/network isolation and a verified resolver/IP-pinning transport before exposing unrestricted self-service crawl to untrusted users.
- Redis password and API tokens travel over plain HTTP/Redis across the LAN; trust boundary is the private LAN only. Do not forward ports to the Internet. For untrusted LAN, add TLS, VPN overlay or reverse proxies.
- OpenSearch's security plugin is disabled in a Docker internal network. Port 9200 is never published to host.
- Default Compose binds API, Web, Redis to Ubuntu A's specific LAN IP rather than 0.0.0.0, but other clients on the LAN can see search/read-only stats.
- robots.txt obeying is enabled, and operators should only crawl authorized/allowed sites. Index-level `noindex` and X-Robots-Tag parsing **must** be implemented before crawling third-party sites at scale.
- Raw HTML is not returned in results; results use plain text and React escaping.

## Known V1 tradeoffs

1. Single OpenSearch node = no index failover. Redis and API on Ubuntu A are also single points of failure.
2. Search may not show a just-indexed document immediately; OpenSearch refreshes periodically.
3. URL dedup is exact after normalization; content hashes are stored but **near-duplicate merging is not implemented**.
4. Not a web-scale full internet crawler. No URL prioritization, PageRank, sitemap, canonical URL resolution or periodic recrawl.
5. A domain's site cap is global for this run and sticky in Redis. A repeat seed may be rejected as already seen.
6. Scrapy's robots.txt middleware applies per worker and does not share robots caches across processes; fetches for robots itself are not globally rate-coordinated across origins perfectly.
7. Workers can hit memory, AOF, network or indexing bottlenecks; monitor before raising concurrency.
8. `REDIS_PASSWORD`/tokens in Compose environment and env files are convenient for a trusted lab; production should move to secrets management.
9. In V1, `robots.txt` obeying does not cover all `noindex` meta/HTTP directives; see recommended patch before public launch.

## V2 milestones

- Atomic delayed/revisit URL frontier with domain fairness, checkpoint recovery and recrawl.
- Distributed OpenSearch with proper voting, replicas and failover plus 2nd control-plane host.
- HTML noindex/follow handling, X-Robots-Tag, canonical URL, sitemap/RSS, site owner removal API.
- Near-duplicate SimHash, PageRank, snapshots/WARC, search quality and anti-spam evaluation.
- OTel/Prometheus metrics, token rotation, TLS, user authentication and admin console.
