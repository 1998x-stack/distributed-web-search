"""Redis Streams URL frontier. At-least-once delivery; OpenSearch IDs are idempotent."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from redis.exceptions import ResponseError

from .urls import normalize_url, url_host

ENQUEUE_LUA = """
local url = ARGV[1]
local site = ARGV[2]
local limit = tonumber(ARGV[3])
if redis.call('SCARD', KEYS[2]) >= limit then return 0 end
if redis.call('SISMEMBER', KEYS[1], url) == 1 then return 0 end
redis.call('SADD', KEYS[1], url)
redis.call('SADD', KEYS[2], url)
redis.call('XADD', KEYS[3], '*', 'payload', ARGV[4])
return 1
"""
RATE_LUA = """
local now = tonumber(ARGV[1])
local gap = tonumber(ARGV[2])
local old = tonumber(redis.call('GET', KEYS[1]) or '0')
local slot = math.max(now, old)
redis.call('SET', KEYS[1], slot + gap, 'PX', math.max(60000, gap * 4))
return slot - now
"""


@dataclass(frozen=True)
class CrawlJob:
    url: str
    domain: str
    depth: int
    max_depth: int
    max_pages: int

    def to_json(self) -> str:
        return json.dumps(vars(self), separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "CrawlJob":
        raw = json.loads(payload)
        job = cls(**raw)
        if (job.depth < 0 or job.depth > job.max_depth or job.max_depth > 5
                or not 1 <= job.max_pages <= 10000
                or url_host(job.url) != job.domain):
            raise ValueError("Invalid stream job")
        return job


class Frontier:
    stream = "dws:v1:frontier"
    group = "dws-workers"
    dead_stream = "dws:v1:deadletters"

    def __init__(self, redis_client):
        self.r = redis_client

    def initialize(self) -> None:
        try:
            self.r.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    def _sitekey(domain: str) -> str:
        return "dws:v1:site:" + hashlib.sha256(domain.encode()).hexdigest()

    def enqueue(self, job: CrawlJob) -> bool:
        if url_host(job.url) != job.domain:
            return False
        job = CrawlJob(normalize_url(job.url), job.domain, job.depth, job.max_depth, job.max_pages)
        return bool(self.r.eval(ENQUEUE_LUA, 3, "dws:v1:seen",
                                self._sitekey(job.domain), self.stream,
                                job.url, job.domain, job.max_pages, job.to_json()))

    def enqueue_children_and_ack(self, message_id: str, parent: CrawlJob, urls: list[str]) -> int:
        # Inflight may be replayed after a crash; URL SADD makes children idempotent.
        queued = 0
        if parent.depth < parent.max_depth:
            for url in urls[:150]:
                child = CrawlJob(url, parent.domain, parent.depth + 1,
                                 parent.max_depth, parent.max_pages)
                queued += int(self.enqueue(child))
        self.r.xack(self.stream, self.group, message_id)
        self.r.hdel("dws:v1:attempts", message_id)
        return queued

    def ack(self, message_id: str) -> None:
        self.r.xack(self.stream, self.group, message_id)
        self.r.hdel("dws:v1:attempts", message_id)

    def deadletter(self, message_id: str, payload: str, reason: str) -> None:
        p = self.r.pipeline(transaction=True)
        p.xadd(self.dead_stream, {"payload": payload, "reason": reason[:200]})
        p.xack(self.stream, self.group, message_id)
        p.hdel("dws:v1:attempts", message_id)
        p.execute()

    def reserve_domain_delay_ms(self, domain: str, gap_ms: int) -> int:
        now = int(time.time() * 1000)
        return int(self.r.eval(RATE_LUA, 1, "dws:v1:rate:" + domain, now, gap_ms))

    def read_new(self, consumer: str, count: int = 4, block_ms: int = 1000):
        return self.r.xreadgroup(self.group, consumer, {self.stream: ">"}, count=count, block=block_ms)

    def reclaim(self, consumer: str, idle_ms: int = 120000, count: int = 8):
        # redis-py returns (next-id, list[(id, fields)], deleted_ids).
        return self.r.xautoclaim(self.stream, self.group, consumer, min_idle_time=idle_ms,
                                start_id="0-0", count=count)[1]

    def attempt(self, message_id: str) -> int:
        return int(self.r.hincrby("dws:v1:attempts", message_id, 1))
