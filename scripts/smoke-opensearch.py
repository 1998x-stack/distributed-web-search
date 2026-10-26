#!/usr/bin/env python3
"""Non-destructive OpenSearch smoke test for a disposable single-node CI container.

WARNING: Creates an index prefixed dws-ci-smoke- on the supplied endpoint.
Use only isolated CI/test clusters. No deletes are performed except cleanup
of the exact temporary index created by this script.
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from opensearchpy import OpenSearch

from services.api.main import INDEX_BODY


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/smoke-opensearch.py http://127.0.0.1:19200")
    endpoint = sys.argv[1]
    # Deliberately require loopback to avoid accidental mutation of real clusters.
    if not (endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")):
        raise SystemExit("Only local disposable OpenSearch endpoints are allowed")
    port = int(endpoint.rsplit(":", 1)[-1])
    client = OpenSearch(hosts=[{"host": "127.0.0.1", "port": port}],
                        use_ssl=False, timeout=10)
    for _ in range(90):
        try:
            if client.ping():
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        raise SystemExit("OpenSearch never became healthy within the smoke-test limit")
    plugins = client.cat.plugins(format="json")
    if not any(x.get("component") == "analysis-icu" for x in plugins):
        raise RuntimeError("OpenSearch ICU analysis plugin not installed")
    index = "dws-ci-smoke-" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]
    try:
        body = json.loads(json.dumps(INDEX_BODY))
        # Single disposable CI node has no replica allocation.
        body["settings"]["number_of_replicas"] = 0
        client.indices.create(index=index, body=body)
        analyzed = client.indices.analyze(index=index, body={
            "analyzer": "dws_icu",
            "text": "中文分布式搜索引擎能够进行检索",
        })
        if not analyzed.get("tokens"):
            raise RuntimeError("ICU analyzer returned no tokens")
        doc = {
            "url": "https://example.org/search",
            "domain": "example.org",
            "title": "中文搜索测试",
            "description": "分布式搜索引擎",
            "content": "中文分布式搜索引擎能够进行检索",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": hashlib.sha256(b"content").hexdigest(),
        }
        client.index(index=index, id="smoke-1", body=doc, refresh="wait_for")
        response = client.search(index=index, body={
            "query": {"multi_match": {
                "query": "分布式搜索引擎", "fields": ["title^4", "description^2", "content"]
            }}
        })
        hits = response["hits"]["hits"]
        if not any(hit["_id"] == "smoke-1" for hit in hits):
            raise RuntimeError("Chinese BM25 search did not retrieve the document")
        print(json.dumps({
            "status": "PASS", "version": client.info()["version"]["number"],
            "analyzer_tokens": len(analyzed["tokens"]),
            "search_hits": len(hits), "index": index
        }, ensure_ascii=False))
    finally:
        client.indices.delete(index=index, ignore=[404])
        client.close()


if __name__ == "__main__":
    main()
