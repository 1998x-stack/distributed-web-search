# Migration from Route B V1 to V2 (safe, staged)

**Never reuse V1 containers, OpenSearch volumes, Redis data directories or cluster IDs for V2.** The code branches are separate. V2 uses `dws:v2:*` and `dws-pages-v2`, plus explicit V2 volumes for controller Redis and both OpenSearch data nodes.

A safe initial approach is to keep V1 stopped and deploy V2 in a separate clone directory, verifying that no conflicting published host ports (3000, 6379, 8000) are active. Do not run V1 and V2 controller Compose concurrently on Ubuntu A under identical external port mappings.

1. Take a cold backup of V1 Redis and OpenSearch persistent volumes and save it off-machine. Confirm you can inspect the archive.
2. Stop V1 container services without deleting volumes: `docker compose -f deploy/controller.yml down` in a V1 checkout **without `-v`**.
3. Clone the `route-B-v2` branch into a distinct folder. Generate new runtime credentials, new OpenSearch node config and deploy.
4. Test V2 new crawling and search first. Existing V1 documents are **not present** in the V2 index.
5. To retain V1 content, separately build a controlled, documented migration pipeline: scroll V1 `dws-pages-v1` index and bulk-write to V2 `dws-pages-v2` with compatible mappings, preserving stable document IDs. This migration is intentionally **not automated in V2**, since it may require older OpenSearch version compatibility and dedup decisions.
6. The old Redis Stream and `seen` keys are not compatible with new V2 retry/recrawl scheduling state. Do not copy them directly.
7. Only decommission V1 volumes after verified data migration and backups.

**No automated backups, PITR, DNS failover, or continuous index replication between V1 and V2 are included.** OpenSearch replica 1 protects against a single data node fault, not deletion or corruption replicated cluster-wide.
