# Route B V2 — acceptance criteria

## Automated tests (CI)

- Python V1+V2 unit tests, including URL/public DNS checks, atomic frontier calls and generated OpenSearch YAML node roles.
- Real Redis 7.4 ephemeral DB 15 integration test executes Lua atomic enqueue/finish/recrawl/retry; verifies stream PEL and next job attempt.
- Three Compose templates syntax-checked with per-node environment values and generated OpenSearch configs.
- Next.js production build, Bash syntax/compileall.
- **CI does not launch a three-machine OpenSearch cluster, real crawlers or benchmark a network.**

## Live cluster acceptance

| Check | Pass condition |
|---|---|
| Network | A/B/C bidirectional TCP 9300 connectivity within trusted LAN |
| OpenSearch nodes | 3 discovered when Mac online; 2 data nodes |
| Replica layout | 2 primary shards and 2 replicas, assigned across A/B |
| Healthy index | Green with both Ubuntu nodes online |
| Worker heartbeats | ubuntu-a, ubuntu-b, macos-c all appear |
| Crawling | URLs from A's seed fetched by at least two Workers |
| Search | A's Web queries return independently crawled results |
| Recrawl | A test page is updated and automatically refreshed after recrawl interval |
| Error retry | Temporary 503 fetch results in due-set delayed retry |
| Permission | robots.txt disallow excluded, noindex page never indexed |
| Obsolete data | 404 / 410 previously indexed document removed |
| Mac sleeping | A/B still serving searches, majority remains |
| Ubuntu B offline | With Mac awake, A still serves replica-backed search; degraded/yellow allowed |
| Ubuntu A offline | Website outage acknowledged; **not HA** |

Run `bash scripts/cluster-inspect.sh` on Ubuntu A and inspect `/api/v1/stats` for `scheduled`, `active_urls`, `deadletters`, `workers`, `cluster`. Trigger tests on authorized/controlled pages only; avoid high-frequency crawling.

## Explicit unresolved capabilities

V2 does not implement atomic cross-store OpenSearch+Redis transactions (uses idempotent replay), enterprise-level TLS between nodes, Redis HA, dedicated multiple API instances, site-level scheduling priorities, near-duplicate SimHash, robots directives scoped precisely to all user agents, canonical URL graph, sitemap discovery or semantic reranking. These are V3+ features; absence is intentional and should not be misrepresented.
