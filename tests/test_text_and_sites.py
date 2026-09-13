"""Tests for ytget_gui.utils.text and ytget_gui.sites."""

import unittest

from ytget_gui import sites
from ytget_gui.utils import text as text_utils


class ShortTests(unittest.TestCase):
    def test_leaves_short_text_alone(self):
        self.assertEqual(text_utils.short("hello", 10), "hello")

    def test_truncates_with_suffix(self):
        result = text_utils.short("abcdefghijklmnop", 8)
        self.assertLessEqual(len(result), 8)
        self.assertTrue(result.endswith("..."))

    def test_limit_shorter_than_the_suffix(self):
        self.assertEqual(text_utils.short("abcdef", 2), "ab")

    def test_handles_empty(self):
        self.assertEqual(text_utils.short("", 5), "")


class ClampTests(unittest.TestCase):
    # clamp() shortens label text with a single-character ellipsis; it is
    # not the numeric clamp the original tests assumed.
    def test_leaves_short_text_alone(self):
        self.assertEqual(text_utils.clamp("hello", 10), "hello")

    def test_truncates_to_limit_plus_ellipsis(self):
        result = text_utils.clamp("abcdefghijklmnop", 8)
        self.assertEqual(result, "abcdefgh\u2026")

    def test_handles_empty(self):
        self.assertEqual(text_utils.clamp("", 5), "")


class WhitespaceTests(unittest.TestCase):
    def test_collapses_runs(self):
        self.assertEqual(text_utils.collapse_whitespace("a   b\n\tc"), "a b c")

    def test_strips_edges(self):
        self.assertEqual(text_utils.collapse_whitespace("  x  "), "x")


class CacheKeyTests(unittest.TestCase):
    def test_strips_unsafe_path_characters(self):
        key = text_utils.cache_key('a/b\\c:d*e?f"g<h>i|j')
        for char in '/\\:*?"<>|':
            with self.subTest(char=char):
                self.assertNotIn(char, key)

    def test_respects_max_len(self):
        self.assertLessEqual(len(text_utils.cache_key("x" * 500, max_len=32)), 32)

    def test_stable(self):
        self.assertEqual(text_utils.cache_key("same"), text_utils.cache_key("same"))


class UrlDigestTests(unittest.TestCase):
    def test_deterministic_and_distinct(self):
        a = text_utils.url_digest("https://example.test/1")
        b = text_utils.url_digest("https://example.test/2")
        self.assertEqual(a, text_utils.url_digest("https://example.test/1"))
        self.assertNotEqual(a, b)


class HumanBytesTests(unittest.TestCase):
    def test_scales_units(self):
        self.assertIn("B", text_utils.human_bytes(512))
        # Binary units: 2048 bytes is 2.0 KiB.
        self.assertIn("KIB", text_utils.human_bytes(2048).upper())
        self.assertIn("MIB", text_utils.human_bytes(5 * 1024 * 1024).upper())

    def test_zero(self):
        self.assertTrue(text_utils.human_bytes(0))


class SiteTests(unittest.TestCase):
    def test_host_of(self):
        self.assertEqual(
            sites.host_of("https://www.youtube.com/watch?v=x"), "youtube.com"
        )

    def test_site_key_for_known(self):
        self.assertEqual(sites.site_key_for("https://youtu.be/abc"), "youtube")

    def test_site_key_for_unknown(self):
        self.assertFalse(sites.site_key_for("https://nowhere.invalid/x"))

    def test_always_allowed_ignores_enabled_list(self):
        self.assertTrue(sites.is_site_enabled("https://youtu.be/abc", []))

    def test_respects_enabled_list(self):
        url = "https://vimeo.com/12345"
        key = sites.site_key_for(url)
        if key and key not in sites.ALWAYS_ALLOWED_KEYS:
            self.assertFalse(sites.is_site_enabled(url, []))
            self.assertTrue(sites.is_site_enabled(url, [key]))

    def test_unknown_site_is_disabled(self):
        self.assertFalse(sites.is_site_enabled("https://nowhere.invalid/x", []))

    def test_accepts_tuple_and_set(self):
        # is_site_enabled no longer builds a set internally, so it must still
        # accept any container the callers pass.
        url = "https://vimeo.com/12345"
        key = sites.site_key_for(url)
        if key and key not in sites.ALWAYS_ALLOWED_KEYS:
            self.assertTrue(sites.is_site_enabled(url, (key,)))
            self.assertTrue(sites.is_site_enabled(url, {key}))

    def test_handles_none_enabled_keys(self):
        self.assertFalse(sites.is_site_enabled("https://vimeo.com/1", None))


if __name__ == "__main__":
    unittest.main()
