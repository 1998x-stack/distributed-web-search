import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from services.api.main import INDEX, INDEX_BODY, require_token


class APITests(unittest.TestCase):
    def test_requires_separate_tokens(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": "test-secret"}, clear=False):
            require_token("Bearer test-secret", "ADMIN_TOKEN")
            for value in ("Bearer bad", "test-secret", None):
                with self.assertRaises(HTTPException):
                    require_token(value, "ADMIN_TOKEN")

    def test_chinese_icu_mappings(self):
        self.assertEqual(INDEX, "dws-pages-v1")
        self.assertEqual(INDEX_BODY["settings"]["number_of_replicas"], 0)
        self.assertEqual(INDEX_BODY["mappings"]["properties"]["content"]["analyzer"], "dws_icu")


if __name__ == "__main__":
    unittest.main()
