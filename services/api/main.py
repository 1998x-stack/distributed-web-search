"""LAN API: public search/read-only stats, token-authenticated seed/index writes."""
from __future__ import annotations

import hashlib
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit

import redis
from fastapi import FastAPI, Header, HTTPException, Query
from opensearchpy import OpenSearch
from pydantic import BaseModel, Field, HttpUrl

from packages.dws_core.frontier_v2 import CrawlJob, FrontierV2
from packages.dws_core.urls import UnsafeURL, assert_public_url, url_host

INDEX = "dws-pages-v2"

INDEX_BODY = {
    "settings": {"number_of_shards": 2, "number_of_replicas": 1, "refresh_interval": "5s",
                 "analysis": {"analyzer": {"dws_icu": {"type": "icu_analyzer"}}}},
    "mappings": {"dynamic": "strict", "properties": {
        "url": {"type": "keyword", "ignore_above": 2048},
        "domain": {"type": "keyword"},
        "title": {"type": "text", "analyzer": "dws_icu"},
        "description": {"type": "text", "analyzer": "dws_icu"},
        "content": {"type": "text", "analyzer": "dws_icu"},
        "fetched_at": {"type": "date"},
        "content_hash": {"type": "keyword"},
    }},
}


def require_token(value: str | None, expected_env: str) -> None:
    token = os.environ.get(expected_env, "")
    import hmac
    if not token or not value or not hmac.compare_digest(value, f"Bearer {token}"):
        raise HTTPException(401, "Valid bearer token required")


def make_redis():
    return redis.Redis(host=os.environ.get("REDIS_HOST", "redis"),
                       port=int(os.environ.get("REDIS_PORT", "6379")),
                       password=os.environ.get("REDIS_PASSWORD"), decode_responses=True,
                       socket_connect_timeout=3, socket_timeout=5)


def make_search():
    return OpenSearch(hosts=[{"host": os.environ.get("OPENSEARCH_HOST", "opensearch"), "port": 9200}],
                      use_ssl=False, verify_certs=False, timeout=15, max_retries=2,
                      retry_on_timeout=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = make_redis()
    app.state.search = make_search()
    last_error = None
    for _ in range(45):
        try:
            app.state.redis.ping()
            if not app.state.search.indices.exists(index=INDEX):
                app.state.search.indices.create(index=INDEX, body=INDEX_BODY)
            FrontierV2(app.state.redis).initialize()
            break
        except Exception as exc:
            last_error = exc
            import asyncio
            await asyncio.sleep(2)
    else:
        raise RuntimeError("Redis/OpenSearch initialization failed") from last_error
    yield
    app.state.redis.close()
    app.state.search.close()


app = FastAPI(title="Distributed Web Search", version="2.1.0", lifespan=lifespan)


class SeedRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    max_depth: int = Field(default=1, ge=0, le=5)
    max_pages: int = Field(default=100, ge=1, le=10000)


class PageDocument(BaseModel):
    url: str = Field(max_length=2048)
    domain: str = Field(max_length=255)
    title: str = Field(max_length=500)
    description: str = Field(default="", max_length=1200)
    content: str = Field(max_length=300000)


@app.get("/api/v1/health")
def health():
    try:
        app.state.redis.ping()
        if not app.state.search.ping():
            raise RuntimeError("OpenSearch not responsive")
    except Exception:
        raise HTTPException(503, "Service dependency unavailable")
    return {"status": "ok", "index": INDEX}


@app.post("/api/v1/seeds", status_code=202)
def add_seed(seed: SeedRequest, authorization: str | None = Header(default=None)):
    require_token(authorization, "ADMIN_TOKEN")
    try:
        url = assert_public_url(seed.url)
    except UnsafeURL as exc:
        raise HTTPException(422, str(exc)) from exc
    domain = url_host(url)
    job = CrawlJob(url=url, domain=domain, depth=0, max_depth=seed.max_depth,
                   max_pages=seed.max_pages)
    enqueued = FrontierV2(app.state.redis).enqueue(job)
    return {"enqueued": enqueued, "url": url, "domain": domain,
            "note": "Existing URLs are idempotent; V2 revisits URLs on the recrawl schedule."}


@app.post("/api/v1/documents", status_code=201)
def ingest(doc: PageDocument, authorization: str | None = Header(default=None)):
    require_token(authorization, "INGEST_TOKEN")
    try:
        url = assert_public_url(doc.url, allowed_host=doc.domain, resolve=False)
    except UnsafeURL as exc:
        raise HTTPException(422, str(exc)) from exc
    if not doc.title.strip() and not doc.content.strip():
        raise HTTPException(422, "No searchable content")
    document = {
        "url": url, "domain": doc.domain, "title": doc.title,
        "description": doc.description, "content": doc.content,
        "content_hash": hashlib.sha256(doc.content.encode()).hexdigest(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    doc_id = hashlib.sha256(url.encode()).hexdigest()
    app.state.search.index(index=INDEX, id=doc_id, body=document, refresh=False)
    return {"id": doc_id, "indexed": True}


@app.get("/api/v1/search")
def search(q: str = Query(default="", max_length=200),
           page: int = Query(default=1, ge=1, le=100),
           size: int = Query(default=10, ge=1, le=20)):
    q = q.strip()
    if not q:
        return {"q": q, "total": 0, "page": page, "size": size, "results": [], "took_ms": 0}
    response = app.state.search.search(index=INDEX, body={
        "from": (page - 1) * size, "size": size, "track_total_hits": True,
        "query": {"multi_match": {"query": q, "type": "best_fields",
                                  "fields": ["title^4", "description^2", "content"]}},
        "_source": ["url", "domain", "title", "description", "content", "fetched_at"],
    })
    hits = response.get("hits", {})
    results = []
    for hit in hits.get("hits", []):
        data = hit["_source"]
        results.append({
            "url": data["url"], "title": data.get("title") or data["url"],
            "domain": data["domain"],
            "snippet": (data.get("description") or data.get("content") or "")[:260],
            "score": round(float(hit.get("_score") or 0), 3),
            "fetched_at": data.get("fetched_at"),
        })
    return {"q": q, "total": hits.get("total", {}).get("value", 0),
            "page": page, "size": size, "took_ms": response.get("took", 0),
            "results": results}


@app.delete("/api/v1/documents")
def delete_document(url: str = Query(max_length=2048),
                    authorization: str | None = Header(default=None)):
    require_token(authorization, "INGEST_TOKEN")
    try:
        url = assert_public_url(url, resolve=False)
    except UnsafeURL as exc:
        raise HTTPException(422, str(exc)) from exc
    doc_id = hashlib.sha256(url.encode()).hexdigest()
    # idempotent: missing documents are okay (e.g. first fetch returned 404)
    app.state.search.delete(index=INDEX, id=doc_id, ignore=[404])
    return {"deleted_or_absent": True, "url": url}


@app.get("/api/v1/cluster")
def cluster():
    health = app.state.search.cluster.health()
    nodes = app.state.search.nodes.info()
    return {
        "cluster_name": health.get("cluster_name"),
        "status": health.get("status"),
        "number_of_nodes": health.get("number_of_nodes"),
        "number_of_data_nodes": health.get("number_of_data_nodes"),
        "active_shards": health.get("active_shards"),
        "unassigned_shards": health.get("unassigned_shards"),
        "nodes": sorted(node["name"] for node in nodes.get("nodes", {}).values()),
    }


@app.get("/api/v1/stats")
def stats():
    r = app.state.redis
    workers = []
    for key in r.scan_iter(match="dws:v2:worker:*", count=100):
        raw = r.get(key)
        if raw:
            import json
            try:
                workers.append(json.loads(raw))
            except ValueError:
                pass
        if len(workers) >= 100:
            break
    pending = 0
    try:
        pending = r.xpending(FrontierV2.stream, FrontierV2.group)["pending"]
    except redis.RedisError:
        pass
    return {"indexed_pages": app.state.search.count(index=INDEX)["count"],
            "queued_events_total": r.xlen(FrontierV2.stream),
            "pending_acks": pending,
            "known_urls": r.scard(FrontierV2.seen),
            "scheduled": r.zcard(FrontierV2.due),
            "active_urls": r.scard(FrontierV2.active),
            "deadletters": r.xlen(FrontierV2.dead) if r.exists(FrontierV2.dead) else 0,
            "workers": workers,
            "cluster": app.state.search.cluster.health().get("status", "unknown")}
