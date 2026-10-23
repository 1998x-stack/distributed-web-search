import unittest
from unittest.mock import patch

from packages.dws_core.urls import UnsafeURL, assert_public_url, normalize_url, url_host


class UrlTests(unittest.TestCase):
    def test_normalize(self):
        u = normalize_url("HTTPS://Example.COM:443/a?utm_source=ads&x=1&fbclid=hi#frag")
        self.assertEqual(u, "https://example.com/a?x=1")
        self.assertEqual(url_host(u), "example.com")

    def test_invalid_input(self):
        for bad in (
            "javascript:alert(1)", "file:///etc/passwd", "ftp://example.com/",
            "http://user:pass@example.com/", "http://bad_host.local",
            "https://example.com:99999/", "/relative/without/base",
        ):
            with self.subTest(bad=bad), self.assertRaises(UnsafeURL):
                # Invalid hostname suffix is tested by assert_public_url.
                assert_public_url(bad, resolve=False)

    def test_public_dns(self):
        def public(*_args, **_kwargs):
            return [(None, None, None, None, ("93.184.215.14", 443))]
        with patch("socket.getaddrinfo", side_effect=public):
            self.assertEqual(assert_public_url("https://example.org/index"),
                             "https://example.org/index")

    def test_private_dns_is_blocked(self):
        def private(*_args, **_kwargs):
            return [(None, None, None, None, ("192.168.1.100", 80))]
        with patch("socket.getaddrinfo", side_effect=private):
            with self.assertRaises(UnsafeURL):
                assert_public_url("http://example.org/")

    def test_mixed_dns_is_blocked(self):
        with patch("socket.getaddrinfo", return_value=[
            (None, None, None, None, ("93.184.215.14", 80)),
            (None, None, None, None, ("127.0.0.1", 80)),
        ]):
            with self.assertRaises(UnsafeURL):
                assert_public_url("http://example.org/")

    def test_cross_domain_forbidden(self):
        with self.assertRaises(UnsafeURL):
            assert_public_url("https://other.example.org", allowed_host="example.org", resolve=False)


if __name__ == "__main__":
    unittest.main()
