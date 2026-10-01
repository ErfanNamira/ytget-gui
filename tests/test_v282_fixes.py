"""Regression tests for the 2.8.2 performance and reliability fixes."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from ytget_gui.queue.model import QueueItem, QueueModel, Status
from ytget_gui.workers import fetch_core

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class RemoveCompletedTests(unittest.TestCase):
    def test_only_the_completed_format_is_removed(self) -> None:
        model = QueueModel()
        video = QueueItem(url=URL, format_code="1080")
        audio = QueueItem(url=URL, format_code="audio_mp3", status=Status.COMPLETED)
        model.add(video)
        model.add(audio)

        removed = model.remove_completed()

        self.assertEqual(removed, [audio])
        self.assertEqual(list(model), [video])
        self.assertIs(model.get(video.key), video)
        self.assertIsNone(model.get(audio.key))
        self.assertEqual(model.items_for_url(URL), [video])

    def test_remove_many_keeps_order_and_indexes(self) -> None:
        model = QueueModel()
        items = [
            QueueItem(url=f"https://www.youtube.com/watch?v=vid{i:08d}")
            for i in range(10)
        ]
        for item in items:
            model.add(item)

        removed = model.remove_many([items[7].key, items[2].key, items[7].key, "nope"])

        self.assertEqual(removed, [items[2], items[7]])
        self.assertEqual(list(model), [i for n, i in enumerate(items) if n not in (2, 7)])
        self.assertFalse(model.contains(items[2].key))
        self.assertFalse(model.contains_url(items[7].url))

    def test_bare_url_token_resolves_to_each_format_in_turn(self) -> None:
        model = QueueModel()
        a = QueueItem(url=URL, format_code="a")
        b = QueueItem(url=URL, format_code="b")
        model.add(a)
        model.add(b)
        self.assertEqual(model.remove_many([URL, URL]), [a, b])
        self.assertFalse(model)


class ParseMetadataTests(unittest.TestCase):
    def test_single_document_fast_path(self) -> None:
        doc = {"id": "dQw4w9WgXcQ", "title": "Song", "duration": 212,
               "formats": [{"vcodec": "avc1", "acodec": "none", "height": 1080,
                            "filesize": 1000}]}
        md = fetch_core.parse_metadata(json.dumps(doc))
        self.assertEqual(md.title, "Song")
        self.assertEqual(md.video_sizes, {1080: 1000})

    def test_multi_line_output_still_parsed(self) -> None:
        text = 'WARNING: noise\n{"id": "a", "title": "One"}\n{"id": "b", "title": "Two"}\n'
        md = fetch_core.parse_metadata(text)
        self.assertEqual(md.title, "One")

    def test_garbage_raises(self) -> None:
        with self.assertRaises(fetch_core.MetadataError):
            fetch_core.parse_metadata("{not json")


class TitleQueueCancelTests(unittest.TestCase):
    def test_cancel_between_pop_and_launch_is_honoured(self) -> None:
        from ytget_gui.workers.title_fetch_manager import TitleFetchQueue

        settings = types.SimpleNamespace(
            YT_DLP_PATH=Path("/nonexistent/yt-dlp"), FFMPEG_PATH=Path("/x/ffmpeg"),
            COOKIES_PATH=None, PROXY_URL="",
        )
        queue = TitleFetchQueue(settings)
        seen = {}

        def fake_fetch(**kwargs):
            seen["cancelled"] = kwargs["cancel_event"].is_set()
            return fetch_core.FetchResult(None, fetch_core.CANCELLED, None, None)

        emitted = []
        queue.metadata_fetched.connect(lambda *a: emitted.append(a))
        queue.error.connect(lambda *a: emitted.append(a))

        original = queue._fetch_one

        def cancel_then_fetch(url):
            queue.cancel(url)  # arrives after the pop, before the launch
            original(url)

        with mock.patch.object(fetch_core, "fetch_metadata", side_effect=fake_fetch):
            queue._fetch_one = cancel_then_fetch
            queue.enqueue_many([URL])

        self.assertTrue(seen["cancelled"])
        self.assertEqual(emitted, [])
        self.assertIsNone(queue._current_url)


class ThumbCacheFirstTests(unittest.TestCase):
    def test_cached_thumbnail_needs_no_network(self) -> None:
        from ytget_gui.workers import thumb_fetcher as tf

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "dQw4w9WgXcQ.jpg").write_bytes(b"\xff\xd8jpeg")
            settings = types.SimpleNamespace(LOG_THUMBNAILS=False)
            fetcher = tf.ThumbFetcher(URL, cache, settings)
            with mock.patch.object(tf._SESSION, "head") as head, \
                 mock.patch.object(tf._SESSION, "get") as get:
                path = fetcher._fetch()
            self.assertEqual(Path(path).name, "dQw4w9WgXcQ.jpg")
            head.assert_not_called()
            get.assert_not_called()


class DownloadWorkerTests(unittest.TestCase):
    def test_output_tracking_is_unique_and_ordered(self) -> None:
        from ytget_gui.workers import download_worker as dw

        stub = types.SimpleNamespace(_outputs=[], _output_set=set())
        add = lambda p: dw.DownloadWorker._add_output(stub, p)  # noqa: E731
        for path in ("a.webm", "b.m4a", "a.webm", "c.mkv", "b.m4a"):
            add(path)
        self.assertEqual(stub._outputs, ["a.webm", "b.m4a", "c.mkv"])

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script")
    def test_flat_playlist_probe_is_cancellable(self) -> None:
        from ytget_gui.workers import download_worker as dw

        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "yt-dlp"
            fake.write_text("#!/bin/sh\nsleep 20\necho 'Top songs'\n")
            fake.chmod(0o755)
            settings = types.SimpleNamespace(YT_DLP_PATH=fake, YT_MUSIC_METADATA=True)
            worker = types.SimpleNamespace(
                settings=settings, _env=None, _process=None,
                _proc_lock=threading.Lock(), cancelled=False,
            )
            result = {}

            def run():
                result["flat"] = dw.DownloadWorker._detect_flat_playlist_if_needed(
                    worker, "https://music.youtube.com/playlist?list=X",
                    is_playlist=True, is_audio=True, is_yt_music=True,
                )

            thread = threading.Thread(target=run)
            thread.start()
            for _ in range(100):
                with worker._proc_lock:
                    live = worker._process
                if live is not None:
                    break
                threading.Event().wait(0.02)
            self.assertIsNotNone(live, "probe never registered its process")
            worker.cancelled = True
            from ytget_gui.workers import proc
            proc.terminate_tree(live, grace=1.0)
            thread.join(5)
            self.assertFalse(thread.is_alive(), "probe ignored cancellation")
            self.assertFalse(result["flat"])
            self.assertIsNone(worker._process)


class AutostartPlistTests(unittest.TestCase):
    def test_arguments_are_xml_escaped(self) -> None:
        from xml.etree import ElementTree

        from ytget_gui import autostart

        with tempfile.TemporaryDirectory() as tmp:
            plist = Path(tmp) / "agent.plist"
            with mock.patch.object(autostart, "_plist_path", return_value=plist), \
                 mock.patch.object(autostart, "_launchctl") as launchctl:
                ok, _ = autostart._mac_set(True, ["/Apps/Tom & Jerry/YTGet", "--delay", "<5>"])
            self.assertTrue(ok)
            launchctl.assert_called_once()
            root = ElementTree.fromstring(plist.read_text(encoding="utf-8").split("\n", 2)[2])
            strings = [e.text for e in root.iter("string")]
            self.assertIn("/Apps/Tom & Jerry/YTGet", strings)
            self.assertIn("<5>", strings)


if __name__ == "__main__":
    unittest.main()
