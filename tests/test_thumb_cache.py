# File: tests/test_thumb_cache.py
"""Thumbnail cache housekeeping.

Removing a queue item has to take its cached image with it; otherwise the
cache grows for the life of the install and a re-added URL shows the old
picture.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from ytget_gui.workers import thumb_fetcher as tf
except ImportError as exc:  # pragma: no cover - PySide6 absent
    tf = None
    _IMPORT_ERROR = str(exc)


@unittest.skipIf(tf is None, "PySide6 not available")
class CacheStemTests(unittest.TestCase):
    def test_video_id_drives_the_stem(self) -> None:
        stem = tf.cache_stem("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(stem, "dQw4w9WgXcQ")

    def test_same_video_different_urls_share_a_stem(self) -> None:
        a = tf.cache_stem("https://www.youtube.com/watch?v=abc123def&list=PL9")
        b = tf.cache_stem("https://youtu.be/abc123def")
        self.assertEqual(a, b)

    def test_non_youtube_url_still_yields_a_stable_stem(self) -> None:
        url = "https://vimeo.com/76979871"
        self.assertTrue(tf.cache_stem(url))
        self.assertEqual(tf.cache_stem(url), tf.cache_stem(url))


@unittest.skipIf(tf is None, "PySide6 not available")
class PurgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self._tmp.name)
        self.manager = tf.ThumbManager.__new__(tf.ThumbManager)
        # Bypass QObject/executor construction: purge only needs the cache dir
        # and the cancellation bookkeeping.
        self.manager.cache_dir = self.cache
        self.manager._lock = __import__("threading").Lock()
        self.manager._pending = set()
        self.manager._active = {}
        self.manager._futures = {}
        self.manager._stopped = False

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _touch(self, name: str) -> Path:
        path = self.cache / name
        path.write_bytes(b"fake-image")
        return path

    def test_purge_deletes_the_cached_image(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        cached = self._touch("dQw4w9WgXcQ.jpg")
        self.manager.purge(url)
        self.assertFalse(cached.exists())

    def test_purge_deletes_every_cached_extension(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        files = [self._touch(f"dQw4w9WgXcQ{ext}") for ext in (".jpg", ".webp", ".png")]
        self.manager.purge(url)
        for path in files:
            self.assertFalse(path.exists(), path.name)

    def test_purge_honours_an_explicit_path(self) -> None:
        # A yt-dlp-resolved id can differ from the one parsed out of the URL,
        # so the stored thumb_path must be deleted too.
        url = "https://example.com/video/1"
        recorded = self._touch("unrelated-stem.jpg")
        self.manager.purge(url, str(recorded))
        self.assertFalse(recorded.exists())

    def test_purge_leaves_other_items_alone(self) -> None:
        keep = self._touch("someOtherId.jpg")
        self.manager.purge("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(keep.exists())

    def test_purge_is_idempotent_and_ignores_missing_files(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.manager.purge(url)
        self.manager.purge(url, str(self.cache / "nope.jpg"))

    def test_purge_ignores_empty_url(self) -> None:
        keep = self._touch("dQw4w9WgXcQ.jpg")
        self.manager.purge("")
        self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
