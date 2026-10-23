import unittest
from unittest.mock import MagicMock

from packages.dws_core.frontier import CrawlJob, Frontier


class FrontierTests(unittest.TestCase):
    def test_job_roundtrip(self):
        job = CrawlJob("https://example.org/", "example.org", 0, 2, 100)
        self.assertEqual(CrawlJob.from_json(job.to_json()), job)

    def test_bad_job_rejected(self):
        with self.assertRaises(ValueError):
            CrawlJob.from_json('{"url":"https://elsewhere.org/","domain":"example.org","depth":0,"max_depth":2,"max_pages":100}')

    def test_seed_is_idempotent_via_lua(self):
        r = MagicMock()
        r.eval.side_effect = [1, 0]
        f = Frontier(r)
        job = CrawlJob("https://example.org", "example.org", 0, 1, 40)
        self.assertTrue(f.enqueue(job))
        self.assertFalse(f.enqueue(job))
        self.assertEqual(r.eval.call_count, 2)
        first_args = r.eval.call_args_list[0].args
        self.assertEqual(first_args[1], 3)
        self.assertEqual(first_args[-1], job.to_json().replace('"url":"https://example.org"', '"url":"https://example.org/"'))

    def test_requeue_then_ack(self):
        r = MagicMock()
        r.eval.return_value = 1
        f = Frontier(r)
        parent = CrawlJob("https://example.org/", "example.org", 0, 1, 20)
        self.assertEqual(f.enqueue_children_and_ack("172-0", parent, ["https://example.org/a"]), 1)
        r.xack.assert_called_once_with(f.stream, f.group, "172-0")

    def test_no_children_at_max_depth(self):
        r = MagicMock()
        f = Frontier(r)
        parent = CrawlJob("https://example.org/", "example.org", 1, 1, 20)
        self.assertEqual(f.enqueue_children_and_ack("172-0", parent, ["https://example.org/a"]), 0)
        r.eval.assert_not_called()


if __name__ == "__main__":
    unittest.main()
