# Route B V2 engineering hardening review

This report covers an **incremental implementation branch** based on `route-B-v2`. Changes are restricted to `route-B-v2-hardening`; `route-B-v2`, `route-B-v1` and `route-A` are not modified.

## Observed defects fixed

| Severity | Finding | Root cause | Correction / regression gate |
|---|---|---|---|
| P0 | `GET /api/v1/stats` raises `NameError` when Redis deadletter stream exists | V2's API still referenced deleted V1 `Frontier` type | Use `FrontierV2.dead`, assert stats response with mocked real app state |
| P1 | Host-wide politeness limiter under-enforces throttling on large queues | Redis key TTL expired earlier than the last reserved fetch slot | Extend TTL beyond last reserved slot; live Redis 30-reservation test |
| P1 | Already-ACKed Redis jobs could mutate ZSET/active state again | Lua completion/retry/deadletter scripts ignored `XACK` result | Refuse stale acknowledgements and ensure deadletters are inserted only after successful ACK; live Redis regression tests |
| P1 | No actual OpenSearch startup or ICU search coverage in CI | Original checks only compiled code and Docker Compose structure | Build real OpenSearch 3.9 image, install plugin, create temporary Chinese index, perform analyzed BM25 query |
| P1 | Next.js/React dependencies lagged security releases | Versions pinned in Oct 2025 | Upgrade Next.js 15.5.7 -> 15.5.28 and React/ReactDOM 19.2.0 -> 19.2.9; run Next.js production build |

The live search smoke test uses one **temporary single-node OpenSearch process on an ephemeral GitHub Actions runner**, not a fabricated 3-node LAN result. Its generated temporary index is deleted in a `finally` block, and it rejects non-loopback OpenSearch endpoints to avoid modifying live production clusters.

## Evidence

- GitHub Actions job `python`: Python unit and real Redis Lua integration tests.
- Job `compose`: three-host generated YAML and Compose syntax.
- Job `web`: Next.js production bundle.
- Job `opensearch-smoke`: production ICU Docker build, single-node startup and actual Chinese query.
- See [workflow](../.github/workflows/route-b-ci.yml) and GitHub Actions runs for **each commit SHA**, as any new commit starts its own verification cycle.

## Known blockers not solved by this patch

1. **Three physical hosts have not been accessed/tested**: OpenSearch cross-host peer discovery, majority during macOS sleep and actual shard placement need a three-host acceptance run; see [VERIFY_V2.md](VERIFY_V2.md).
2. **Control-plane SPOF**: Redis, FastAPI, Next.js are only on Ubuntu A. Replicated OpenSearch shards are not a substitute for HA of the application.
3. **DNS rebinding / SSRF TOCTOU**: Scrapy validates DNS before fetching but does not pin connections to the validated address. V2 should only accept seeds from trusted operators with network egress ACLs.
4. **Worker lease race**: XACK-based stale check prevents *already acknowledged* duplicate state transitions. A reclaimed message may still be under execution by the previous worker; the queue is at-least-once and does not implement a full consumer-owner fencing token or cross-store transaction.
5. **Redis state scalability**: Exact-URL Sets and the payload hash grow with indexed domains; benchmark resource growth before scaling beyond modest corpora.
6. **HTTPS/auth**: Redis and worker ingestion use trusted-LAN plaintext endpoints. Never expose 6379, 8000 or 9300 to public Internet.
7. **Reproducibility**: The web dependencies use pinned direct versions, but the repo still lacks a committed npm lockfile. Container rebuilds can resolve changing transitive packages.

## Release gates for deploying on three machines

- All four CI jobs succeed at the final commit.
- Both Ubuntu data nodes join the same OpenSearch cluster and replica placement is green.
- A, B and Mac report independent worker IDs.
- Crawl a small permitted test corpus; verify document counts/search matches and shared rate limiting.
- Stop a worker and verify pending claim/recrawl with the same indexed document ID.
- Test Mac sleep, then test B down only with Mac awake; document unavailability of controller A if it stops.
- Block untrusted inbound LAN traffic with a verified host firewall / Docker-aware ruleset.

Scope of this pass: eliminate demonstrated defects and add a real search-engine smoke test without destructive changes to the existing branches or data.
