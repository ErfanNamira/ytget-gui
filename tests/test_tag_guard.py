"""Duplicate-title protection: tag snapshot/restore, log handling, archive.

The end-to-end case drives a real DownloadWorker against local file:// URLs
so it needs yt-dlp and ffmpeg on PATH; the rest needs ffmpeg only to create
small audio files.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ytget_gui.workers import download_worker as dw
from ytget_gui.workers import tag_guard

FFMPEG = shutil.which("ffmpeg")
YTDLP = shutil.which("yt-dlp")
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
A_URL = "https://www.youtube.com/watch?v=AAAAAAAAAAA"
B_URL = "https://www.youtube.com/watch?v=BBBBBBBBBBB"

_CODECS = {
    "mp3": ["-c:a", "libmp3lame"],
    "opus": ["-c:a", "libopus"],
    "flac": ["-c:a", "flac"],
    "m4a": ["-c:a", "aac"],
}


def _make_tagged(folder: Path, ext: str, url: str = A_URL) -> Path:
    from mutagen import File
    from mutagen.flac import Picture

    path = folder / f"song.{ext}"
    subprocess.run(
        [FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=d=1",
         *_CODECS[ext], str(path)],
        check=True,
    )
    audio = File(path)
    if audio.tags is None:
        audio.add_tags()
    if ext == "mp3":
        from mutagen.id3 import APIC, TIT2, TXXX

        audio.tags.add(APIC(mime="image/png", type=3, data=PNG))
        audio.tags.add(TXXX(desc="purl", text=url))
        audio.tags.add(TIT2(text="Original"))
    elif ext == "m4a":
        from mutagen.mp4 import MP4Cover

        audio.tags["covr"] = [MP4Cover(PNG, MP4Cover.FORMAT_PNG)]
        audio.tags["\xa9cmt"] = [url]
        audio.tags["\xa9nam"] = ["Original"]
    else:
        pic = Picture()
        pic.data, pic.type, pic.mime = PNG, 3, "image/png"
        if ext == "flac":
            audio.add_picture(pic)
        else:
            audio["METADATA_BLOCK_PICTURE"] = [base64.b64encode(pic.write()).decode()]
        audio["purl"] = [url]
        audio["title"] = ["Original"]
    audio.save()
    return path


def _retag_like_ytdlp(path: Path) -> None:
    """What yt-dlp's metadata step does to the other upload's file."""
    tmp = path.with_name(f"retag{path.suffix}")
    subprocess.run(
        [FFMPEG, "-loglevel", "error", "-y", "-i", str(path), "-map", "0:a",
         "-c", "copy", "-map_metadata", "-1", "-metadata", "title=Intruder",
         "-metadata", f"purl={B_URL}", str(tmp)],
        check=True,
    )
    os.replace(tmp, path)


def _fingerprint(path: Path):
    from mutagen import File

    audio = File(path)
    return (
        sorted((str(k), repr(v)) for k, v in audio.tags.items()),
        [p.data for p in getattr(audio, "pictures", []) or []],
    )


@unittest.skipUnless(FFMPEG, "ffmpeg required")
class SnapshotRestoreTests(unittest.TestCase):
    def test_round_trip_every_supported_format(self) -> None:
        for ext in ("mp3", "opus", "flac", "m4a"):
            with self.subTest(ext=ext), tempfile.TemporaryDirectory() as tmp:
                path = _make_tagged(Path(tmp), ext)
                before = _fingerprint(path)
                probe = tag_guard.probe(path)
                self.assertIn("AAAAAAAAAAA", probe.source_text)
                self.assertIsNotNone(probe.snapshot)
                self.assertFalse(tag_guard.changed_since(path, probe.snapshot))

                _retag_like_ytdlp(path)
                self.assertTrue(tag_guard.changed_since(path, probe.snapshot))
                self.assertTrue(tag_guard.restore(path, probe.snapshot))
                self.assertEqual(_fingerprint(path), before)
                self.assertFalse(tag_guard.changed_since(path, probe.snapshot))

    def test_unreadable_file_is_unknown_not_an_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.opus"
            path.write_bytes(b"not audio")
            probe = tag_guard.probe(path)
            self.assertIsNone(probe.snapshot)
            self.assertEqual(dw._owner_of(probe.source_text, "BBBBBBBBBBB"), "unknown")


class OwnerTests(unittest.TestCase):
    def test_owner_classification(self) -> None:
        self.assertEqual(dw._owner_of(A_URL, "AAAAAAAAAAA"), "same")
        self.assertEqual(dw._owner_of(A_URL, "BBBBBBBBBBB"), "other")
        self.assertEqual(dw._owner_of("", "BBBBBBBBBBB"), "unknown")
        self.assertEqual(dw._owner_of(None, "BBBBBBBBBBB"), "unknown")
        self.assertEqual(dw._owner_of("no url here", "BBBBBBBBBBB"), "unknown")


def _stub_worker(**extra):
    """A DownloadWorker without Qt/thread setup, for the pure helpers."""
    import threading

    worker = dw.DownloadWorker.__new__(dw.DownloadWorker)
    worker._probes = {}
    worker._probe_lock = threading.Lock()
    worker._archive_lines = None
    worker._existing = {}
    worker._phase = "main"
    worker._entry_id = ""
    worker._logged = []
    worker.add_log = lambda text, colour="": worker._logged.append(text)
    for key, value in extra.items():
        setattr(worker, key, value)
    return worker


@unittest.skipUnless(FFMPEG, "ffmpeg required")
class ReaderScanTests(unittest.TestCase):
    def test_marker_split_across_reads_is_probed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _make_tagged(Path(tmp), "mp3")
            worker = _stub_worker()
            line = f"[download] {path} has already been downloaded\n".encode()
            cut = len(line) // 2
            tail = worker._scan_for_existing(b"", b"[info] x\n" + line[:cut])
            self.assertEqual(worker._probes, {})
            tail = worker._scan_for_existing(tail, line[cut:] + b"[Metadata] ...")
            self.assertEqual(tail, b"[Metadata] ...")
            probe = worker._probes[str(path)]
            self.assertIn("AAAAAAAAAAA", probe.source_text)
            self.assertIsNotNone(probe.snapshot)

    def test_tail_is_bounded(self) -> None:
        worker = _stub_worker()
        tail = worker._scan_for_existing(b"", b"x" * 100_000)
        self.assertLessEqual(len(tail), dw._MARKER_TAIL_LIMIT)


class ExplainErrorTests(unittest.TestCase):
    def test_known_existing_file_error_is_explained_once(self) -> None:
        worker = _stub_worker(_entry_id="BBBBBBBBBBB")
        worker._existing["BBBBBBBBBBB"] = {"path": "/m/Ocean.opus", "owner": "other"}
        self.assertTrue(worker._explain_existing_error())
        self.assertIn("saved separately", worker._logged[-1])
        self.assertFalse(worker._explain_existing_error())  # second error shown as-is

    def test_unknown_owner_and_followups_are_not_hidden(self) -> None:
        worker = _stub_worker(_entry_id="BBBBBBBBBBB")
        worker._existing["BBBBBBBBBBB"] = {"path": "/m/Ocean.opus", "owner": "unknown"}
        self.assertFalse(worker._explain_existing_error())
        worker._existing["BBBBBBBBBBB"]["owner"] = "other"
        worker._phase = "followup"
        self.assertFalse(worker._explain_existing_error())


class ArchiveTests(unittest.TestCase):
    def test_record_is_idempotent_and_unrecord_removes_only_that_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "archive.txt"
            archive.write_text("youtube AAAAAAAAAAA\nyoutube BBBBBBBBBBB\n", encoding="utf-8")
            worker = _stub_worker()
            worker._record_archive(archive, "youtube", "CCCCCCCCCCC")
            worker._record_archive(archive, "youtube", "CCCCCCCCCCC")
            worker._record_archive(archive, "youtube", "AAAAAAAAAAA")
            self.assertEqual(
                archive.read_text(encoding="utf-8").splitlines(),
                ["youtube AAAAAAAAAAA", "youtube BBBBBBBBBBB", "youtube CCCCCCCCCCC"],
            )
            worker._unrecord_archive(archive, "youtube", "BBBBBBBBBBB")
            self.assertEqual(
                archive.read_text(encoding="utf-8").splitlines(),
                ["youtube AAAAAAAAAAA", "youtube CCCCCCCCCCC"],
            )
            # The cache follows the file, so the entry can be recorded again.
            worker._record_archive(archive, "youtube", "BBBBBBBBBBB")
            self.assertIn("youtube BBBBBBBBBBB", archive.read_text(encoding="utf-8"))


@unittest.skipUnless(FFMPEG, "ffmpeg required")
class FollowupTargetTests(unittest.TestCase):
    def test_existing_disambiguated_file_of_same_entry_counts_as_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            original = _make_tagged(folder, "opus")
            job = {"id": "BBBBBBBBBBB", "path": original}
            self.assertFalse(dw.DownloadWorker._followup_target_exists(job))
            other = folder / "sub"
            other.mkdir()
            made = _make_tagged(other, "opus", url=B_URL)
            made.rename(folder / "song [BBBBBBBBBBB].opus")
            self.assertTrue(dw.DownloadWorker._followup_target_exists(job))


@unittest.skipUnless(FFMPEG and YTDLP, "ffmpeg and yt-dlp required")
class EndToEndCollisionTests(unittest.TestCase):
    """Two different uploads that resolve to the same filename."""

    def _run(self, settings, url):
        from PySide6.QtCore import QCoreApplication, QTimer

        app = QCoreApplication.instance() or QCoreApplication([])
        worker = dw.DownloadWorker(
            {"url": url, "title": "song", "format_code": self.fmt_code}, settings
        )
        # file:// sources use the generic extractor; map ids back to them.
        worker._entry_url = lambda entry, ie: self.urls[entry]
        result, logs = {}, []
        worker.log.connect(lambda text, colour: logs.append(text))
        worker.finished.connect(lambda code: (result.setdefault("code", code), app.quit()))
        QTimer.singleShot(0, worker.run)
        QTimer.singleShot(60_000, app.quit)
        app.exec()
        return result.get("code"), logs

    def _settings(self, root: Path):
        from ytget_gui.settings import AppSettings

        s = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
        s.YT_DLP_PATH = Path(YTDLP)
        s.FFMPEG_PATH = Path(FFMPEG)
        s.ENABLE_ARCHIVE = False
        s.SHOW_YTDLP_LOGS = False  # the default; reconciliation must still work
        s.COOKIES_FROM_BROWSER = ""
        s.YOUTUBE_PLAYER_CLIENT = "auto"
        s.EXTRA_YTDLP_ARGS = (
            '--enable-file-urls '
            '--parse-metadata "webpage_url:.*/(?P<id>[^/]+)/[^/]+$" '
            '--parse-metadata "id:(?P<meta_purl>.+)" '
            '--replace-in-metadata meta_purl "^" "https://www.youtube.com/watch?v="'
        )
        return s

    def test_mp3_original_keeps_its_tags_and_second_upload_is_saved(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        self.fmt_code = "bestaudio"  # MP3
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.urls = {}
            for vid, freq in (("AAAAAAAAAAA", 440), ("BBBBBBBBBBB", 880)):
                (root / vid).mkdir()
                src = root / vid / "song.opus"
                subprocess.run([FFMPEG, "-loglevel", "error", "-f", "lavfi", "-i",
                                f"sine=f={freq}:d=1", "-c:a", "libopus", str(src)], check=True)
                self.urls[vid] = src.as_uri()
            settings = self._settings(root)

            code, _ = self._run(settings, self.urls["AAAAAAAAAAA"])
            self.assertEqual(code, 0)
            code, logs = self._run(settings, self.urls["BBBBBBBBBBB"])
            self.assertEqual(code, 0, logs)

            original = root / "dl" / "song.mp3"
            second = root / "dl" / "song [BBBBBBBBBBB].mp3"
            self.assertTrue(second.is_file(), logs)
            self.assertIn("AAAAAAAAAAA", dw._source_tag_text(original))
            self.assertNotIn("BBBBBBBBBBB", dw._source_tag_text(original))
            self.assertIn("BBBBBBBBBBB", dw._source_tag_text(second))
            self.assertTrue(any("Restored the original tags" in l for l in logs), logs)


if __name__ == "__main__":
    unittest.main()
