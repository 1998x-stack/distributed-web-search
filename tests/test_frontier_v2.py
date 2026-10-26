import json
import unittest
from unittest.mock import MagicMock, patch
from packages.dws_core.frontier_v2 import CrawlJob, FrontierV2, ENQUEUE, FINISH, RETRY, DISPATCH_DUE


class TestFrontierV2(unittest.TestCase):
    def setUp(self):
        self.r = MagicMock()
        self.f = FrontierV2(self.r)
        self.job = CrawlJob("https://example.org/", "example.org", 0, 2, 30)

    def test_job_roundtrip_and_rejects_bad_depth(self):
        self.assertEqual(CrawlJob.from_json(self.job.to_json()), self.job)
        obj = json.loads(self.job.to_json())
        obj["depth"] = 10
        with self.assertRaises(ValueError):
            CrawlJob.from_json(json.dumps(obj))

    def test_enqueue_atomic(self):
        self.r.eval.side_effect = [1, 0]
        self.assertTrue(self.f.enqueue(self.job))
        self.assertFalse(self.f.enqueue(self.job))
        self.assertEqual(self.r.eval.call_args.args[0], ENQUEUE)

    def test_finish_schedules_recrawl_and_parent_ack(self):
        self.r.eval.return_value = 1
        with patch("time.time", return_value=1000):
            children = self.f.finish("1-0", self.job,
                                     ["https://example.org/child"], 86400)
        self.assertEqual(children, 1)
        calls = self.r.eval.call_args_list
        self.assertEqual(calls[-1].args[0], FINISH)
        self.assertEqual(calls[-1].args[-2], 87400)

    def test_retry_uses_due_set_not_sleeping_queue(self):
        with patch("time.time", return_value=1000):
            self.assertTrue(self.f.retry("2-0", self.job, "timeout"))
        call = self.r.eval.call_args.args
        self.assertEqual(call[0], RETRY)
        self.assertEqual(call[-2], 1030)
        self.assertEqual(CrawlJob.from_json(call[-1]).attempt, 1)

    def test_deadletter_after_limit(self):
        attempt4 = CrawlJob(self.job.url, self.job.domain, 0, 2, 30, 4)
        self.assertFalse(self.f.retry("2-0", attempt4, "timeout"))
        self.assertIn("deadletters", self.r.eval.call_args.args[4])

    def test_dispatch_due(self):
        self.r.eval.return_value = 3
        self.assertEqual(self.f.dispatch_due(20), 3)
        self.assertEqual(self.r.eval.call_args.args[0], DISPATCH_DUE)

    def test_stale_finish_cannot_report_success(self):
        self.r.eval.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "Stale completion"):
            self.f.finish("missing-0", self.job, [], 60)

    def test_stale_retry_cannot_report_success(self):
        self.r.eval.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "Stale retry"):
            self.f.retry("missing-0", self.job, "timeout")


if __name__ == "__main__":
    unittest.main()
