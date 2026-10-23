"""Real Redis Lua integration tests on dedicated CI database 15 only.

Run with DWS_TEST_REDIS_URL=redis://localhost:6379/15. The suite FLUSHDBs this
database and MUST NEVER target an existing production Redis database.
"""
import os
import unittest
from unittest.mock import patch

from packages.dws_core.frontier_v2 import CrawlJob, FrontierV2

TEST_URL = os.environ.get("DWS_TEST_REDIS_URL")


@unittest.skipUnless(TEST_URL, "requires disposable DWS_TEST_REDIS_URL")
class RedisIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import redis
        cls.r = redis.Redis.from_url(TEST_URL, decode_responses=True)
        if cls.r.connection_pool.connection_kwargs.get("db") != 15:
            raise RuntimeError("Integration tests are destructive: require dedicated Redis DB 15")
        cls.r.ping()
        cls.r.flushdb()
        cls.front = FrontierV2(cls.r)
        cls.front.initialize()

    @classmethod
    def tearDownClass(cls):
        if TEST_URL:
            cls.r.flushdb()
            cls.r.close()

    def test_a_enqueue_complete_revisit(self):
        job = CrawlJob("https://example.org/path-a", "example.org", 0, 1, 50)
        self.assertTrue(self.front.enqueue(job))
        self.assertFalse(self.front.enqueue(job))
        messages = self.front.read_new("worker-a", block_ms=10)
        self.assertTrue(messages)
        item_id = messages[0][1][0][0]
        self.assertEqual(self.front.finish(item_id, job, [], recrawl_seconds=60), 0)
        self.assertEqual(self.r.xpending(self.front.stream, self.front.group)["pending"], 0)
        self.assertEqual(self.r.zcard(self.front.due), 1)
        with patch("time.time", return_value=10**10):
            self.assertEqual(self.front.dispatch_due(20), 1)
        replay = self.front.read_new("worker-b", block_ms=10)
        self.assertEqual(CrawlJob.from_json(replay[0][1][0][1]["payload"]).url, job.url)

    def test_b_retry_exponential(self):
        job = CrawlJob("https://example.org/path-b", "example.org", 0, 1, 50)
        self.assertTrue(self.front.enqueue(job))
        msg = self.front.read_new("worker-a", block_ms=10)[0][1][0]
        self.assertTrue(self.front.retry(msg[0], job, "timeout", base_delay_seconds=15))
        self.assertEqual(self.r.xpending(self.front.stream, self.front.group)["pending"], 1)
        # path-a is still unacked on worker-b; path-b successfully delayed
        with patch("time.time", return_value=10**10):
            self.assertEqual(self.front.dispatch_due(20), 1)
        next_msg = self.front.read_new("worker-b", block_ms=10)[0][1][0]
        self.assertEqual(CrawlJob.from_json(next_msg[1]["payload"]).attempt, 1)


if __name__ == "__main__":
    unittest.main()
