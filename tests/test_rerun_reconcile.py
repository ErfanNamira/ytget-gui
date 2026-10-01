"""Duplicate-title / rerun reconciliation helpers and async queue saving."""

import json
import shutil
import subprocess
import types
import unittest
from pathlib import Path
import tempfile

from ytget_gui.queue.model import QueueItem, QueueModel
from ytget_gui.workers import download_worker as dw


class FollowupCommandTests(unittest.TestCase):
    def test_retargets_single_entry_with_unique_name(self):
        stub = types.SimpleNamespace(_main_cmd=[
            "yt-dlp", "--ignore-config", "--download-archive", "a.txt",
            "--yes-playlist", "-o", "/d/%(playlist_title)s/%(title)s.%(ext)s",
            "--no-abort-on-error", "--playlist-items", "1-5",
            "--parse-metadata", "playlist_index:%(track_number)s",
            "--embed-thumbnail", "--", "https://example.com/list",
        ])
        job = {"id": "0jIVvxAak0U", "url": "https://www.youtube.com/watch?v=0jIVvxAak0U",
               "path": Path("/d/100% Hits/Ocean.opus"), "index": 10}
        cmd = dw.DownloadWorker._followup_command(stub, job)
        for gone in ("--download-archive", "--yes-playlist", "--playlist-items",
                     "--no-abort-on-error", "https://example.com/list"):
            self.assertNotIn(gone, cmd)
        self.assertIn("--embed-thumbnail", cmd)
        self.assertEqual(cmd[cmd.index("-o") + 1],
                         str(Path("/d/100%% Hits") / "Ocean [0jIVvxAak0U].%(ext)s"))
        self.assertIn("%(playlist_index|10)s:%(track_number)s", cmd)
        self.assertEqual(cmd[-2:], ["--", job["url"]])


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
class SourceTagTests(unittest.TestCase):
    def test_reads_purl_from_opus(self):
        from mutagen.oggopus import OggOpus

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.opus"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                            "sine=d=1", "-c:a", "libopus", str(path)], check=True)
            audio = OggOpus(path)
            audio["purl"] = ["https://www.youtube.com/watch?v=mhjyJ-boh0I"]
            audio.save()
            self.assertIn("mhjyJ-boh0I", dw._source_tag_text(path))


class AsyncSaveTests(unittest.TestCase):
    def test_latest_snapshot_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "queue.json"
            model = QueueModel(target)
            model.add(QueueItem(url="https://www.youtube.com/watch?v=aaaaaaaaaaa"))
            model.save_async()
            model.add(QueueItem(url="https://www.youtube.com/watch?v=bbbbbbbbbbb"))
            model.save()  # synchronous save supersedes the queued one
            self.assertEqual(len(json.loads(target.read_text())), 2)
            self.assertNotIn("produced_files", target.read_text())


if __name__ == "__main__":
    unittest.main()
