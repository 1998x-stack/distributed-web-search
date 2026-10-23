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

from packages.dws_core.frontier import CrawlJob, Frontier
from packages.dws_core.urls import UnsafeURL, assert_public_url, normalize_url

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
        self.frontier = Frontier(redis_connection())
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
        self.frontier = Frontier(redis_connection())
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
            count = await asyncio.to_thread(self.frontier.enqueue_children_and_ack,
                                            msg_id, job, links)
            spider.crawler.stats.inc_value("dws/indexed", 1)
            spider.crawler.stats.inc_value("dws/discovered", count)
        except Exception:
            # Leave message in PEL; XAUTOCLAIM reassigns it to another worker.
            LOG.exception("Index or queue commit failed: %s", job.url)
            spider.crawler.stats.inc_value("dws/ingest_errors", 1)
        finally:
            spider.inflight = max(0, spider.inflight - 1)
        return item


class LanWebSpider(scrapy.Spider):
    name = "lanweb"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worker_id = os.environ["WORKER_ID"]
        self.frontier = Frontier(redis_connection())
        self.inflight = 0
        self.capacity = max(1, int(os.environ.get("WORKER_CONCURRENCY", "4")))
        self.last_reclaim = 0.0
        self.last_heartbeat = 0.0

    async def start(self):
        await asyncio.to_thread(self.frontier.initialize)
        LOG.info("Worker %s connected to Redis Streams group %s",
                 self.worker_id, Frontier.group)
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
                    await asyncio.to_thread(self.frontier.deadletter, message_id, payload, "invalid job")
                    continue
                attempts = await asyncio.to_thread(self.frontier.attempt, message_id)
                if attempts > 4:
                    await asyncio.to_thread(self.frontier.deadletter, message_id, payload,
                                            "retry limit exceeded")
                    continue
                self.inflight += 1
                yield scrapy.Request(job.url, callback=self.parse_page,
                                     errback=self.fetch_error, dont_filter=True,
                                     meta={"_message_id": message_id, "job_payload": payload,
                                           "handle_httpstatus_all": True})

    def heartbeat(self):
        self.frontier.r.set("dws:v1:worker:" + self.worker_id,
                            json.dumps({"id": self.worker_id, "inflight": self.inflight,
                                        "seen_at": int(time.time())}), ex=35)

    async def terminal(self, message_id: str, reason: str, job_payload: str):
        await asyncio.to_thread(self.frontier.deadletter, message_id, job_payload, reason)
        self.inflight = max(0, self.inflight - 1)

    async def accept_without_index(self, message_id: str):
        await asyncio.to_thread(self.frontier.ack, message_id)
        self.inflight = max(0, self.inflight - 1)

    async def parse_page(self, response: scrapy.http.Response):
        message_id = response.meta["_message_id"]
        raw_job = response.meta["job_payload"]
        job = CrawlJob.from_json(raw_job)
        status = response.status
        if status in (429, 500, 502, 503, 504):
            LOG.warning("Transient response %s for %s (leave pending)", status, job.url)
            self.inflight -= 1
            return
        if status != 200:
            await self.accept_without_index(message_id)
            return
        if not isinstance(response, scrapy.http.HtmlResponse) or "html" not in response.headers.get(b"Content-Type", b"").decode().lower():
            await self.accept_without_index(message_id)
            return
        title = (response.css("title::text").get() or "").strip()[:500]
        description = (response.css('meta[name="description"]::attr(content)').get() or "").strip()[:1200]
        content = (trafilatura.extract(response.text, include_comments=False,
                                      include_tables=True, favor_precision=True) or "").strip()[:300000]
        if not title and not content:
            await self.accept_without_index(message_id)
            return
        links = []
        if job.depth < job.max_depth:
            for href in response.css("a::attr(href)").getall()[:500]:
                try:
                    child = normalize_url(href, response.url)
                    if urlsplit(child).hostname == job.domain:
                        links.append(child)
                except (UnsafeURL, ValueError):
                    continue
        yield {
            "url": job.url, "domain": job.domain, "title": title,
            "description": description, "content": content,
            "_message_id": message_id, "_job_payload": raw_job, "_links": links[:150],
        }

    async def fetch_error(self, failure: Failure):
        request = failure.request
        msg_id = request.meta["_message_id"]
        payload = request.meta["job_payload"]
        if failure.check(IgnoreRequest):
            LOG.info("Denied by security policy or robots.txt: %s", request.url)
            await self.accept_without_index(msg_id)
        else:
            LOG.warning("Transient fetch error for %s: %s", request.url, failure.value)
            # The PEL retains the job for safe delayed re-claim.
            self.inflight = max(0, self.inflight - 1)
