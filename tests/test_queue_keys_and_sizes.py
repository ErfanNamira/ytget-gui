# File: tests/test_queue_keys_and_sizes.py
"""Multi-format queue identity (item 2) and size estimation (item 4)."""
from __future__ import annotations

import unittest

from ytget_gui.formats import estimate_download_size
from ytget_gui.queue.model import QueueItem, QueueModel
from ytget_gui.workers.fetch_core import parse_sizes


URL = "https://example.com/watch?v=abc"


def item(url: str, code: str, label: str = "") -> QueueItem:
    return QueueItem(url=url, title="", format_code=code, format_label=label or code)


class QueueKeyTests(unittest.TestCase):
    def test_key_combines_url_and_format(self) -> None:
        self.assertNotEqual(item(URL, "a").key, item(URL, "b").key)
        self.assertEqual(item(URL, "a").key, item(URL, "a").key)

    def test_same_url_different_formats_both_queue(self) -> None:
        model = QueueModel()
        self.assertTrue(model.add(item(URL, "video")))
        self.assertTrue(model.add(item(URL, "audio")))
        self.assertEqual(len(model), 2)
        self.assertEqual(len(model.items_for_url(URL)), 2)

    def test_same_url_same_format_is_rejected(self) -> None:
        model = QueueModel()
        self.assertTrue(model.add(item(URL, "video")))
        self.assertFalse(model.add(item(URL, "video")))
        self.assertEqual(len(model), 1)

    def test_remove_by_key_keeps_the_other_format(self) -> None:
        model = QueueModel()
        first = item(URL, "video")
        second = item(URL, "audio")
        model.add(first)
        model.add(second)
        self.assertIsNotNone(model.remove(first.key))
        self.assertEqual([i.format_code for i in model], ["audio"])
        self.assertEqual(len(model.items_for_url(URL)), 1)
        self.assertIsNone(model.get(first.key))

    def test_remove_clears_url_bucket_when_empty(self) -> None:
        model = QueueModel()
        only = item(URL, "video")
        model.add(only)
        model.remove(only.key)
        self.assertFalse(model.contains_url(URL))
        self.assertEqual(model.items_for_url(URL), [])

    def test_url_lookup_still_resolves(self) -> None:
        model = QueueModel()
        model.add(item(URL, "video"))
        found = model.get(URL)
        self.assertIsNotNone(found)
        self.assertEqual(found.format_code, "video")

    def test_reorder_by_keys(self) -> None:
        model = QueueModel()
        a, b = item(URL, "video"), item(URL, "audio")
        model.add(a)
        model.add(b)
        model.reorder_by_keys([b.key, a.key])
        self.assertEqual([i.format_code for i in model], ["audio", "video"])

    def test_move_many_accepts_keys(self) -> None:
        model = QueueModel()
        a, b = item(URL, "video"), item(URL, "audio")
        model.add(a)
        model.add(b)
        model.move_many([a.key], to_top=False)
        self.assertEqual([i.format_code for i in model], ["audio", "video"])

    def test_roundtrip_keeps_format_and_size(self) -> None:
        original = item(URL, "video", "1080p")
        original.filesize = 1234
        restored = QueueItem.from_dict(original.to_dict())
        self.assertEqual(restored.key, original.key)
        self.assertEqual(restored.filesize, 1234)

    def test_bad_persisted_size_is_dropped(self) -> None:
        for raw in ("big", -5, 0, None, True):
            data = item(URL, "video").to_dict()
            data["filesize"] = raw
            self.assertIsNone(QueueItem.from_dict(data).filesize)


class ParseSizesTests(unittest.TestCase):
    INFO = {
        "duration": 100,
        "formats": [
            {"height": 1080, "vcodec": "avc1", "acodec": "none", "filesize": 1000},
            {"height": 1080, "vcodec": "vp9", "acodec": "none", "filesize": 1500},
            {"height": 720, "vcodec": "avc1", "acodec": "none", "filesize_approx": 600},
            {"height": None, "vcodec": "none", "acodec": "opus", "filesize": 100},
            {"height": None, "vcodec": "none", "acodec": "mp4a", "filesize": 200},
        ],
    }

    def test_largest_per_height_and_best_audio(self) -> None:
        video, audio = parse_sizes(self.INFO)
        self.assertEqual(video, {1080: 1500, 720: 600})
        self.assertEqual(audio, 200)

    def test_missing_formats(self) -> None:
        self.assertEqual(parse_sizes({}), ({}, None))
        self.assertEqual(parse_sizes({"formats": "nope"}), ({}, None))

    def test_bitrate_fallback_uses_duration(self) -> None:
        video, _ = parse_sizes(
            {
                "duration": 10,
                "formats": [{"height": 480, "vcodec": "avc1", "acodec": "none", "tbr": 800}],
            }
        )
        self.assertEqual(video, {480: 800 * 125 * 10})

    def test_bitrate_without_duration_is_skipped(self) -> None:
        video, _ = parse_sizes(
            {"formats": [{"height": 480, "vcodec": "avc1", "acodec": "none", "tbr": 800}]}
        )
        self.assertEqual(video, {})


class EstimateSizeTests(unittest.TestCase):
    VIDEO = {360: 300, 720: 700, 1080: 1500, 2160: 4000}

    def test_video_plus_audio_under_cap(self) -> None:
        # "1080p" style codes cap the height; audio is merged in.
        total = estimate_download_size(self.VIDEO, 100, "bv*[height<=1080]+ba/b")
        self.assertEqual(total, 1500 + 100)

    def test_uncapped_code_takes_the_best_height(self) -> None:
        self.assertEqual(estimate_download_size(self.VIDEO, 100, "best"), 4000 + 100)

    def test_audio_code_returns_audio_only(self) -> None:
        self.assertEqual(estimate_download_size(self.VIDEO, 100, "bestaudio"), 100)

    def test_progressive_only_site_is_not_double_counted(self) -> None:
        self.assertEqual(estimate_download_size({720: 700}, None, "best"), 700)

    def test_no_data_returns_none(self) -> None:
        self.assertIsNone(estimate_download_size({}, None, "best"))
        self.assertIsNone(estimate_download_size(None, None, "best"))

    def test_everything_above_cap_falls_back_to_smallest(self) -> None:
        total = estimate_download_size({2160: 4000}, 100, "bv*[height<=720]+ba/b")
        self.assertEqual(total, 4100)


if __name__ == "__main__":
    unittest.main()
