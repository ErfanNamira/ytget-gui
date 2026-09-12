"""Tests for ytget_gui.utils.validators.

The rate-limit and playlist-items validators are the ones users can feed
arbitrary text from Preferences, so they get the most edge cases.
"""

import unittest

from ytget_gui.utils import validators as v


class SupportedUrlTests(unittest.TestCase):
    def test_youtube_variants(self):
        for url in (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtu.be/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        ):
            with self.subTest(url=url):
                self.assertTrue(v.is_supported_url(url))
                self.assertTrue(v.is_youtube_url(url))

    def test_youtube_music_detection(self):
        self.assertTrue(v.is_youtube_music_url("https://music.youtube.com/watch?v=x"))
        self.assertFalse(v.is_youtube_music_url("https://www.youtube.com/watch?v=x"))

    def test_spotify(self):
        url = "https://open.spotify.com/track/abc"
        self.assertTrue(v.is_spotify_url(url))
        self.assertTrue(v.is_supported_url(url))

    def test_rejects_junk(self):
        for url in ("", "   ", "not a url", "ftp://example.com", None):
            with self.subTest(url=url):
                self.assertFalse(v.is_supported_url(url or ""))

    def test_rejects_lookalike_host(self):
        # Substring matching on the host would wrongly accept these.
        self.assertFalse(v.is_youtube_url("https://youtube.com.evil.test/watch?v=x"))

    def test_short_url_strips_whitespace(self):
        # Regression: untrimmed input made urlparse see a scheme of " https".
        self.assertTrue(v.is_short_video_url("  https://www.youtube.com/shorts/abc  "))

    def test_short_url_negative(self):
        self.assertFalse(v.is_short_video_url("https://www.youtube.com/watch?v=abc"))

    def test_playlist_url(self):
        self.assertTrue(
            v.is_playlist_url("https://www.youtube.com/playlist?list=PL123")
        )
        self.assertFalse(v.is_playlist_url("https://www.youtube.com/watch?v=abc"))


class RateLimitTests(unittest.TestCase):
    def test_valid(self):
        for value in ("50K", "1.5M", "2G", "1024", "4.5m"):
            with self.subTest(value=value):
                self.assertTrue(v.is_valid_rate_limit(value))

    def test_bare_suffix_is_rejected_not_raised(self):
        # Regression: this raised ValueError out of the validator instead of
        # returning False, crashing the Preferences dialog.
        for value in ("K", "M", ".", ".M"):
            with self.subTest(value=value):
                self.assertFalse(v.is_valid_rate_limit(value))

    def test_empty_is_allowed_as_unset(self):
        self.assertTrue(v.is_valid_rate_limit(""))
        self.assertTrue(v.is_valid_rate_limit("   "))

    def test_zero_and_negative(self):
        self.assertFalse(v.is_valid_rate_limit("0"))
        self.assertFalse(v.is_valid_rate_limit("-5M"))

    def test_garbage(self):
        for value in ("fast", "50KB/s", "1..5M", "50 K"):
            with self.subTest(value=value):
                self.assertFalse(v.is_valid_rate_limit(value))


class PlaylistItemsTests(unittest.TestCase):
    def test_valid_forms(self):
        for value in ("1", "1,3,5", "1-5", "2-", "-4", "1,3-7,10", ""):
            with self.subTest(value=value):
                self.assertTrue(v.is_valid_playlist_items(value))

    def test_invalid_forms(self):
        for value in ("abc", "1-2-3", "1,,2", "0-", "-", "1..3"):
            with self.subTest(value=value):
                self.assertFalse(v.is_valid_playlist_items(value))


class TimecodeTests(unittest.TestCase):
    def test_valid(self):
        for value in ("00:00", "1:30", "01:02:03"):
            with self.subTest(value=value):
                self.assertTrue(v.is_valid_timecode(value))

    def test_invalid(self):
        for value in ("xx:yy", "1:2:3:4", ""):
            with self.subTest(value=value):
                self.assertFalse(v.is_valid_timecode(value))

    def test_conversion(self):
        self.assertEqual(v.timecode_to_seconds("01:02:03"), 3723)
        self.assertEqual(v.timecode_to_seconds("1:30"), 90)


class MiscValidatorTests(unittest.TestCase):
    def test_dateafter(self):
        self.assertTrue(v.is_valid_dateafter("20240101"))
        self.assertFalse(v.is_valid_dateafter("2024-01-01"))

    def test_proxy(self):
        self.assertTrue(v.is_valid_proxy("http://127.0.0.1:8080"))
        self.assertTrue(v.is_valid_proxy(""))
        self.assertFalse(v.is_valid_proxy("127.0.0.1:8080"))

    def test_sub_langs(self):
        self.assertTrue(v.is_valid_sub_langs("en,fr"))
        self.assertTrue(v.is_valid_sub_langs(""))


if __name__ == "__main__":
    unittest.main()