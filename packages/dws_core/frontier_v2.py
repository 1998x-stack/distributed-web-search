"""V2 URL frontier: atomic dedup, durable delayed retries, and scheduled recrawls.

All queue mutations are Lua-atomic, Redis Stream entries are deleted only AFTER
acknowledgement, and document IDs are stable across at-least-once deliveries.
Redis itself remains one controller-host SPOF in V2.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from redis.exceptions import ResponseError

from .urls import normalize_url, url_host


ENQUEUE = """
local url=ARGV[1]
local limit=tonumber(ARGV[2])
if redis.call('SISMEMBER',KEYS[1],url)==1 then return 0 end
if redis.call('SCARD',KEYS[2])>=limit then return 0 end
redis.call('SADD',KEYS[1],url)
redis.call('SADD',KEYS[2],url)
redis.call('SADD',KEYS[3],url)
redis.call('HSET',KEYS[4],url,ARGV[3])
redis.call('XADD',KEYS[5],'*','payload',ARGV[3])
return 1
"""

FINISH = """
if redis.call('XACK',KEYS[1],ARGV[1],ARGV[2]) ~= 1 then return 0 end
redis.call('XDEL',KEYS[1],ARGV[2])
redis.call('SREM',KEYS[2],ARGV[3])
if tonumber(ARGV[4])>0 then
  redis.call('HSET',KEYS[4],ARGV[3],ARGV[5])
  redis.call('ZADD',KEYS[3],ARGV[4],ARGV[3])
end
return 1
"""

RETRY = """
if redis.call('XACK',KEYS[1],ARGV[1],ARGV[2]) ~= 1 then return 0 end
redis.call('XDEL',KEYS[1],ARGV[2])
redis.call('SREM',KEYS[2],ARGV[3])
redis.call('HSET',KEYS[4],ARGV[3],ARGV[5])
redis.call('ZADD',KEYS[3],ARGV[4],ARGV[3])
return 1
"""

DEADLETTER = """
redis.call('XADD',KEYS[3],'*','payload',ARGV[3],'reason',ARGV[4])
if redis.call('XACK',KEYS[1],ARGV[1],ARGV[2]) ~= 1 then return 0 end
redis.call('XDEL',KEYS[1],ARGV[2])
local url=ARGV[5]
if url == '' then
  local ok,doc=pcall(cjson.decode,ARGV[3])
  if ok and type(doc)=='table' and type(doc.url)=='string' then url=doc.url end
end
if url ~= '' then redis.call('SREM',KEYS[2],url) end
return 1
"""

DISPATCH_DUE = """
local ready=redis.call('ZRANGEBYSCORE',KEYS[1],'-inf',ARGV[1],'LIMIT',0,tonumber(ARGV[2]))
local dispatched=0
for _,url in ipairs(ready) do
  if redis.call('SISMEMBER',KEYS[2],url)==1 then
    redis.call('ZADD',KEYS[1],tonumber(ARGV[1])+60,url)
  else
    local payload=redis.call('HGET',KEYS[3],url)
    redis.call('ZREM',KEYS[1],url)
    if payload then
      redis.call('SADD',KEYS[2],url)
      redis.call('XADD',KEYS[4],'*','payload',payload)
      dispatched=dispatched+1
    end
  end
end
return dispatched
"""

RATE = """
local now=tonumber(ARGV[1])
local gap=tonumber(ARGV[2])
local prev=tonumber(redis.call('GET',KEYS[1]) or '0')
local slot=math.max(now,prev)
redis.call('SET',KEYS[1],slot+gap,'PX',math.max(60000,slot+gap-now+60000))
return slot-now
"""


@dataclass(frozen=True)
class CrawlJob:
    url: str
    domain: str
    depth: int
    max_depth: int
    max_pages: int
    attempt: int = 0

    def to_json(self) -> str:
        return json.dumps(vars(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "CrawlJob":
        data = json.loads(raw)
        job = cls(**data)
        if (job.depth < 0 or job.depth > job.max_depth or not 0 <= job.max_depth <= 5
                or not 1 <= job.max_pages <= 10000 or not 0 <= job.attempt <= 12
                or normalize_url(job.url) != job.url
                or url_host(job.url) != job.domain):
            raise ValueError("Invalid V2 job")
        return job


class FrontierV2:
    stream = "dws:v2:frontier"
    group = "dws-v2-workers"
    due = "dws:v2:due"
    seen = "dws:v2:seen"
    active = "dws:v2:active"
    payloads = "dws:v2:payloads"
    dead = "dws:v2:deadletters"

    def __init__(self, client):
        self.r = client

    @staticmethod
    def site_key(domain: str) -> str:
        return "dws:v2:site:" + hashlib.sha256(domain.encode()).hexdigest()

    def initialize(self):
        try:
            self.r.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def enqueue(self, job: CrawlJob) -> bool:
        if url_host(job.url) != job.domain:
            return False
        canonical = normalize_url(job.url)
        job = CrawlJob(canonical, job.domain, job.depth, job.max_depth, job.max_pages, 0)
        return bool(self.r.eval(ENQUEUE, 5, self.seen, self.site_key(job.domain),
                                self.active, self.payloads, self.stream,
                                job.url, job.max_pages, job.to_json()))

    def finish(self, message_id: str, job: CrawlJob, links: list[str],
               recrawl_seconds: int = 86400) -> int:
        # Children dedup is atomic. Parent remains pending when any child enqueue fails.
        added = 0
        if job.depth < job.max_depth:
            for url in links[:150]:
                if url_host(url) == job.domain:
                    child = CrawlJob(url, job.domain, job.depth+1,
                                     job.max_depth, job.max_pages)
                    added += int(self.enqueue(child))
        fresh = CrawlJob(job.url, job.domain, job.depth,
                         job.max_depth, job.max_pages, 0)
        at = int(time.time()) + recrawl_seconds if recrawl_seconds else 0
        accepted = self.r.eval(FINISH, 4, self.stream, self.active, self.due, self.payloads,
                    self.group, message_id, job.url, at, fresh.to_json())
        if not accepted:
            raise RuntimeError("Stale completion: stream message was already acknowledged")
        return added

    def retry(self, message_id: str, job: CrawlJob, reason: str,
              base_delay_seconds: int = 30, max_attempts: int = 4) -> bool:
        next_attempt = job.attempt + 1
        if next_attempt > max_attempts:
            self.deadletter(message_id, job, reason)
            return False
        next_job = CrawlJob(job.url, job.domain, job.depth, job.max_depth,
                            job.max_pages, next_attempt)
        # Backoff uses next_attempt, capped at 1 hour.
        delay = min(3600, base_delay_seconds * (2 ** (next_attempt-1)))
        accepted = self.r.eval(RETRY, 4, self.stream, self.active, self.due, self.payloads,
                    self.group, message_id, job.url, int(time.time())+delay,
                    next_job.to_json())
        if not accepted:
            raise RuntimeError("Stale retry: stream message was already acknowledged")
        return True

    def deadletter(self, message_id: str, job: CrawlJob, reason: str):
        accepted = self.r.eval(DEADLETTER, 3, self.stream, self.active, self.dead,
                    self.group, message_id, job.to_json(), reason[:200], job.url)
        if not accepted:
            raise RuntimeError("Stale deadletter: stream message was already acknowledged")

    def deadletter_raw(self, message_id: str, payload: str, reason: str):
        accepted = self.r.eval(DEADLETTER, 3, self.stream, self.active, self.dead,
                    self.group, message_id, payload, reason[:200], "")
        if not accepted:
            raise RuntimeError("Stale invalid-message acknowledgement")

    def read_new(self, consumer: str, count: int = 4, block_ms: int = 1000):
        return self.r.xreadgroup(self.group, consumer,
                                 {self.stream: ">"}, count=count, block=block_ms)

    def reclaim(self, consumer: str, idle_ms: int = 120000, count: int = 4):
        return self.r.xautoclaim(self.stream, self.group, consumer,
                                 min_idle_time=idle_ms, start_id="0-0", count=count)[1]

    def dispatch_due(self, limit: int = 50) -> int:
        return int(self.r.eval(DISPATCH_DUE, 4, self.due, self.active,
                               self.payloads, self.stream, int(time.time()), limit))

    def reserve_domain_delay_ms(self, domain: str, gap_ms: int) -> int:
        now = int(time.time()*1000)
        return int(self.r.eval(RATE, 1, "dws:v2:rate:"+domain,
                               now, gap_ms))
