"""Scrapy 2.13 async start() consumes Redis Streams across three LAN hosts.

No per-worker static URL assignment. Every worker can claim a newly queued
URL. Acknowledgement occurs after idempotent OpenSearch indexing succeeds.
Unacked work can be claimed after the lease expires; delivery is at least once.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from urllib.parse import urlsplit

import httpx
import redis
import scrapy
import trafilatura
from scrapy.exceptions import IgnoreRequest
from twisted.python.failure import Failure

from packages.dws_core.frontier_v2 import CrawlJob, FrontierV2
from packages.dws_core.urls import UnsafeURL, assert_public_url, normalize_url
from .policy import robots_directives

LOG = logging.getLogger(__name__)


def redis_connection() -> redis.Redis:
    return redis.Redis(host=os.environ["REDIS_HOST"], port=6379,
                       password=os.environ["REDIS_PASSWORD"], decode_responses=True,
                       socket_connect_timeout=4, socket_timeout=8)


class SafetyAndRateMiddleware:
    """Reject private/loopback destinations; take one global domain slot.

    DNS validation cannot eliminate time-of-check/time-of-use DNS rebinding:
    deploy outbound firewall restrictions as a further boundary if crawling
    arbitrary untrusted hosts.
    """

    def __init__(self):
        self.frontier = FrontierV2(redis_connection())
        self.gap_ms = max(1000, int(os.environ.get("DOMAIN_DELAY_MS", "3000")))

    async def process_request(self, request: scrapy.Request, spider: scrapy.Spider):
        job_json = request.meta.get("job_payload")
        allowed = CrawlJob.from_json(job_json).domain if job_json else None
        try:
            safe_url = await asyncio.to_thread(assert_public_url, request.url, allowed)
            if safe_url != normalize_url(request.url):
                raise UnsafeURL("Non-canonical request URL")
        except (UnsafeURL, ValueError) as exc:
            raise IgnoreRequest("Unsafe destination: " + str(exc)) from exc
        domain = urlsplit(safe_url).hostname
        delay = await asyncio.to_thread(self.frontier.reserve_domain_delay_ms, domain, self.gap_ms)
        if delay > 0:
            await asyncio.sleep(delay / 1000)
        return None


class IngestPipeline:
    def __init__(self):
        self.frontier = FrontierV2(redis_connection())
        self.url = os.environ["API_URL"].rstrip("/") + "/api/v1/documents"
        self.token = os.environ["INGEST_TOKEN"]

    async def process_item(self, item: dict, spider: scrapy.Spider):
        msg_id = item.pop("_message_id")
        job = CrawlJob.from_json(item.pop("_job_payload"))
        links = item.pop("_links")
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(self.url, json=item, headers={
                    "Authorization": "Bearer " + self.token,
                })
                response.raise_for_status()
            count = await asyncio.to_thread(self.frontier.finish, msg_id, job, links,
                                             int(os.environ.get("RECRAWL_SECONDS", "86400")))
            spider.crawler.stats.inc_value("dws/indexed", 1)
            spider.crawler.stats.inc_value("dws/discovered", count)
        except Exception as exc:
            # If Redis is unavailable the PEL retains ownership for XAUTOCLAIM.
            LOG.exception("Index or queue commit failed: %s", job.url)
            spider.crawler.stats.inc_value("dws/ingest_errors", 1)
            try:
                await asyncio.to_thread(self.frontier.retry, msg_id, job, str(exc))
            except Exception:
                LOG.exception("Unable to schedule retry; message remains pending")
        finally:
            spider.inflight = max(0, spider.inflight - 1)
        return item


class LanWebSpider(scrapy.Spider):
    name = "lanweb"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worker_id = os.environ["WORKER_ID"]
        self.frontier = FrontierV2(redis_connection())
        self.inflight = 0
        self.capacity = max(1, int(os.environ.get("WORKER_CONCURRENCY", "4")))
        self.last_reclaim = 0.0
        self.last_heartbeat = 0.0

    async def start(self):
        await asyncio.to_thread(self.frontier.initialize)
        LOG.info("Worker %s connected to Redis Streams group %s",
                 self.worker_id, FrontierV2.group)
        while True:
            now = time.monotonic()
            if now - self.last_heartbeat > 10:
                await asyncio.to_thread(self.heartbeat)
                self.last_heartbeat = now
            if self.inflight >= self.capacity:
                await asyncio.sleep(0.25)
                continue
            messages = []
            if now - self.last_reclaim > 20:
                self.last_reclaim = now
                messages = await asyncio.to_thread(self.frontier.reclaim, self.worker_id,
                                                   120000, min(4, self.capacity - self.inflight))
            if not messages:
                data = await asyncio.to_thread(self.frontier.read_new, self.worker_id,
                                               min(4, self.capacity - self.inflight), 1000)
                messages = data[0][1] if data else []
            for message_id, fields in messages:
                payload = fields.get("payload", "")
                try:
                    job = CrawlJob.from_json(payload)
                except Exception as exc:
                    LOG.warning("Bad stream payload %s: %s", message_id, exc)
                    await asyncio.to_thread(self.frontier.deadletter_raw, message_id, payload, "invalid job")
                    continue
                self.inflight += 1
                yield scrapy.Request(job.url, callback=self.parse_page,
                                     errback=self.fetch_error, dont_filter=True,
                                     meta={"_message_id": message_id, "job_payload": payload,
                                           "handle_httpstatus_all": True})

    def heartbeat(self):
        self.frontier.r.set("dws:v2:worker:" + self.worker_id,
                            json.dumps({"id": self.worker_id, "inflight": self.inflight,
                                        "seen_at": int(time.time())}), ex=35)

    async def accept_without_index(self, message_id: str, job: CrawlJob,
                                   recrawl_seconds: int = 86400):
        await asyncio.to_thread(self.frontier.finish, message_id, job, [],
                                recrawl_seconds)
        self.inflight = max(0, self.inflight - 1)

    async def reschedule(self, message_id: str, job: CrawlJob, reason: str):
        try:
            await asyncio.to_thread(self.frontier.retry, message_id, job, reason)
        except Exception:
            LOG.exception("Retry scheduling failed; Redis PEL will recover the job")
        finally:
            self.inflight = max(0, self.inflight - 1)

    async def parse_page(self, response: scrapy.http.Response):
        message_id = response.meta["_message_id"]
        raw_job = response.meta["job_payload"]
        job = CrawlJob.from_json(raw_job)
        status = response.status
        if status in (429, 500, 502, 503, 504):
            LOG.warning("Transient response %s for %s", status, job.url)
            await self.reschedule(message_id, job, "http " + str(status))
            return
        if status in (404, 410):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    result = await client.delete(
                        os.environ["API_URL"].rstrip("/") + "/api/v1/documents",
                        params={"url": job.url},
                        headers={"Authorization": "Bearer " + os.environ["INGEST_TOKEN"]})
                    result.raise_for_status()
                await self.accept_without_index(message_id, job, 86400 * 7)
            except Exception as exc:
                await self.reschedule(message_id, job, "delete " + str(exc))
            return
        if status != 200:
            await self.accept_without_index(message_id, job, 86400 * 7)
            return
        if not isinstance(response, scrapy.http.HtmlResponse) or "html" not in response.headers.get(b"Content-Type", b"").decode().lower():
            await self.accept_without_index(message_id, job, 86400 * 7)
            return
        title = (response.css("title::text").get() or "").strip()[:500]
        description = (response.css('meta[name="description"]::attr(content)').get() or "").strip()[:1200]
        content = (trafilatura.extract(response.text, include_comments=False,
                                      include_tables=True, favor_precision=True) or "").strip()[:300000]
        directives = robots_directives(response)
        if not title and not content and "noindex" not in directives:
            await self.accept_without_index(message_id, job)
            return
        links = []
        if job.depth < job.max_depth and "nofollow" not in directives:
            for href in response.css("a::attr(href)").getall()[:500]:
                try:
                    child = normalize_url(href, response.url)
                    if urlsplit(child).hostname == job.domain:
                        links.append(child)
                except (UnsafeURL, ValueError):
                    continue
        if "noindex" in directives:
            # Remove a previously indexed version; noindex pages must not linger.
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    deleted = await client.delete(
                        os.environ["API_URL"].rstrip("/") + "/api/v1/documents",
                        params={"url": job.url},
                        headers={"Authorization": "Bearer " + os.environ["INGEST_TOKEN"]})
                    deleted.raise_for_status()
                await asyncio.to_thread(self.frontier.finish,
                                        message_id, job, links[:150],
                                        int(os.environ.get("RECRAWL_SECONDS", "86400")))
            except Exception as exc:
                await self.reschedule(message_id, job, "noindex cleanup " + str(exc))
                return
            self.inflight = max(0, self.inflight - 1)
            return
        yield {
            "url": job.url, "domain": job.domain, "title": title,
            "description": description, "content": content,
            "_message_id": message_id, "_job_payload": raw_job, "_links": links[:150],
        }

    async def fetch_error(self, failure: Failure):
        request = failure.request
        msg_id = request.meta["_message_id"]
        payload = request.meta["job_payload"]
        job = CrawlJob.from_json(payload)
        if failure.check(IgnoreRequest):
            LOG.info("Denied by security policy or robots.txt: %s", request.url)
            await self.accept_without_index(msg_id, job, 86400 * 7)
        else:
            LOG.warning("Transient fetch error for %s: %s", request.url, failure.value)
            await self.reschedule(msg_id, job, str(failure.value))
