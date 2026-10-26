import os
import unittest
from unittest.mock import patch, MagicMock

from fastapi import HTTPException
from services.api.main import INDEX, INDEX_BODY, require_token, app, stats


class APITests(unittest.TestCase):
    def test_requires_separate_tokens(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": "test-secret"}, clear=False):
            require_token("Bearer test-secret", "ADMIN_TOKEN")
            for value in ("Bearer bad", "test-secret", None):
                with self.assertRaises(HTTPException):
                    require_token(value, "ADMIN_TOKEN")

    def test_chinese_icu_mappings(self):
        self.assertEqual(INDEX, "dws-pages-v2")
        self.assertEqual(INDEX_BODY["settings"]["number_of_replicas"], 1)
        self.assertEqual(INDEX_BODY["mappings"]["properties"]["content"]["analyzer"], "dws_icu")

    def test_v2_stats_returns_deadletters_without_name_error(self):
        original_redis = getattr(app.state, "redis", None)
        original_search = getattr(app.state, "search", None)
        mock_r = MagicMock()
        mock_r.scan_iter.return_value = []
        mock_r.xpending.return_value = {"pending": 2}
        mock_r.scard.return_value = 4
        mock_r.zcard.return_value = 1
        mock_r.xlen.return_value = 3
        mock_r.exists.return_value = True
        mock_s = MagicMock()
        mock_s.count.return_value = {"count": 10}
        mock_s.cluster.health.return_value = {"status": "green"}
        app.state.redis = mock_r
        app.state.search = mock_s
        try:
            result = stats()
            self.assertEqual(result["indexed_pages"], 10)
            self.assertEqual(result["pending_acks"], 2)
            self.assertEqual(result["deadletters"], 3)
            self.assertEqual(result["cluster"], "green")
            self.assertEqual(result["scheduled"], 1)
            self.assertTrue(mock_r.exists.called)
            self.assertEqual(mock_r.exists.call_args.args, ("dws:v2:deadletters",))
        finally:
            app.state.redis = original_redis
            app.state.search = original_search


if __name__ == "__main__":
    unittest.main()
