import unittest
from scrapy.http import HtmlResponse
from scrapy import Request

from services.worker.policy import robots_directives


def response(markup, headers=None):
    return HtmlResponse(url="https://example.org/",
                        request=Request("https://example.org/"),
                        body=markup.encode(), encoding="utf-8",
                        headers=headers or {"Content-Type": "text/html"})


class RobotsIndexPolicyTests(unittest.TestCase):
    def test_meta_noindex(self):
        r = response('<html><head><meta name="robots" content="noindex, follow"></head></html>')
        self.assertEqual(robots_directives(r), {"noindex"})

    def test_meta_none(self):
        r = response('<META NAME="robots" CONTENT="none">')
        self.assertEqual(robots_directives(r), {"noindex", "nofollow"})

    def test_header_nofollow(self):
        r = response("<html></html>", {"X-Robots-Tag": "googlebot: nofollow, noindex"})
        self.assertEqual(robots_directives(r), {"noindex", "nofollow"})

    def test_unrestricted(self):
        self.assertEqual(robots_directives(response("<html><head><title>hello</title></head></html>")), set())


if __name__ == "__main__":
    unittest.main()
