"""Tests for ytget_gui.formats selector building."""

import unittest

from ytget_gui import formats


class DedupeTests(unittest.TestCase):
    def test_removes_repeats_preserving_order(self):
        self.assertEqual(formats.dedupe_chain("a/b/a/c"), "a/b/c")

    def test_handles_empty(self):
        self.assertEqual(formats.dedupe_chain(""), "")


class BestFallbackTests(unittest.TestCase):
    def test_appends_capped_fallback(self):
        chain = formats.ensure_best_fallback("bestvideo[height<=1080]+bestaudio")
        self.assertTrue(chain.endswith("best[height<=1080]"))

    def test_empty_becomes_best(self):
        self.assertEqual(formats.ensure_best_fallback(""), "best")

    def test_idempotent(self):
        once = formats.ensure_best_fallback("bestvideo[height<=720]+bestaudio")
        twice = formats.ensure_best_fallback(once)
        self.assertEqual(once, twice)


class VideoChainTests(unittest.TestCase):
    def test_includes_height_cap_and_audio(self):
        chain = formats.video_chain(1080)
        self.assertIn("height<=1080", chain)
        self.assertIn("bestaudio", chain)

    def test_is_cached(self):
        self.assertIs(formats.video_chain(1080), formats.video_chain(1080))


class HeightParsingTests(unittest.TestCase):
    def test_heights_in(self):
        parsed = formats.heights_in("bestvideo[height<=1080]/best[height<=720]")
        self.assertEqual(parsed, [1080, 720])

    def test_heights_in_empty(self):
        self.assertEqual(formats.heights_in(""), [])
        self.assertEqual(formats.heights_in("bestaudio"), [])

    def test_max_height(self):
        self.assertEqual(formats.max_height_in("best[height<=480]"), 480)
        self.assertIsNone(formats.max_height_in("bestaudio"))


class CodeClassificationTests(unittest.TestCase):
    def test_audio_codes(self):
        self.assertTrue(formats.is_audio_code("bestaudio"))
        self.assertTrue(formats.is_audio_code("audio_flac"))
        self.assertFalse(formats.is_audio_code("1080p"))

    def test_spotify_code(self):
        self.assertTrue(formats.is_spotify_code(formats.SPOTIFY_FORMAT_CODE))
        self.assertFalse(formats.is_spotify_code("bestaudio"))

    def test_presets_are_non_empty(self):
        presets = formats.build_resolution_presets()
        self.assertTrue(presets)
        for label, selector in presets.items():
            with self.subTest(label=label):
                self.assertTrue(selector)


if __name__ == "__main__":
    unittest.main()
