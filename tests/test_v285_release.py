"""2.8.5 regressions: codec-aware sizes, type changes, subtitle 429, card width,
request pacing, change-type dialog width."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ytget_gui.formats import estimate_download_size
from ytget_gui.queue.model import QueueItem, QueueModel, Status
from ytget_gui.settings import AppSettings, REQUEST_PACING_PRESETS  # noqa: F401 - used by pacing tests
from ytget_gui.workers.fetch_core import Metadata, metadata_payload, parse_metadata
from ytget_gui.workers.download_worker import DownloadWorker, is_subtitle_rate_limited

URL = "https://www.youtube.com/watch?v=KW2uFSpW3wo"

SUBS_429 = (
    "ERROR: Unable to download video subtitles for 'en': "
    "HTTP Error 429: Too Many Requests"
)


# ----------------------------------------------------------------------
# 1. Codec-aware size estimates
# ----------------------------------------------------------------------


class CodecAwareEstimateTests(unittest.TestCase):
    LADDER = {
        "av01": {360: 60, 720: 260, 1080: 420},
        "vp9": {360: 90, 720: 400, 1080: 700},
        "avc": {360: 150, 720: 700, 1080: 1500},
    }
    OVERALL = {360: 150, 720: 700, 1080: 1500}
    CHAIN_1080 = "bestvideo*[height<=1080]+bestaudio/best[height<=1080]"

    def test_av1_preference_quotes_av1_stream(self) -> None:
        total = estimate_download_size(
            self.OVERALL, 100, self.CHAIN_1080,
            codec_sizes=self.LADDER, codec="av1",
        )
        self.assertEqual(total, 420 + 100)

    def test_h264_preference_quotes_avc_stream(self) -> None:
        total = estimate_download_size(
            self.OVERALL, 100, self.CHAIN_1080,
            codec_sizes=self.LADDER, codec="h264",
        )
        self.assertEqual(total, 1500 + 100)

    def test_auto_keeps_the_largest_stream(self) -> None:
        total = estimate_download_size(
            self.OVERALL, 100, self.CHAIN_1080,
            codec_sizes=self.LADDER, codec="auto",
        )
        self.assertEqual(total, 1500 + 100)

    def test_missing_family_falls_back_to_overall(self) -> None:
        total = estimate_download_size(
            self.OVERALL, 100, self.CHAIN_1080,
            codec_sizes={"vp9": {1080: 700}}, codec="av1",
        )
        self.assertEqual(total, 1500 + 100)

    def test_family_below_cap_only(self) -> None:
        # AV1 stops at 720 on this site; the estimate must not quote an
        # above-cap AV1 height nor fall back silently to the 1080 AVC one.
        ladder = {"av01": {720: 260}, "avc": {1080: 1500}}
        total = estimate_download_size(
            self.OVERALL, 100, self.CHAIN_1080,
            codec_sizes=ladder, codec="av1",
        )
        self.assertEqual(total, 260 + 100)

    def test_webm_h264_prefers_any_codec(self) -> None:
        # AVC cannot be stream-copied into WebM, so the preference is void;
        # the built-in chain itself then restricts the estimate to AV1/VP9.
        total = estimate_download_size(
            self.OVERALL, 100, self.CHAIN_1080,
            codec_sizes=self.LADDER, codec="h264", container=".webm",
        )
        self.assertEqual(total, 700 + 100)

    def test_payload_carries_codec_sizes(self) -> None:
        payload = metadata_payload(
            Metadata(
                title="t",
                video_id="v",
                thumb_url="",
                is_playlist=False,
                video_sizes={1080: 1500},
                audio_size=100,
                codec_sizes={"av01": {1080: 420}},
            )
        )
        self.assertEqual(payload["codec_sizes"], {"av01": {1080: 420}})
        self.assertEqual(payload["video_sizes"], {1080: 1500})
        json.dumps(payload)  # must survive the queued-signal round trip


class ParseMetadataCodecTests(unittest.TestCase):
    def test_codec_ladders_parsed_from_info_json(self) -> None:
        info = {
            "id": "KW2uFSpW3wo",
            "title": "BURN 500 CALORIES",
            "duration": 1800,
            "formats": [
                {"height": 1080, "vcodec": "avc1.640028", "acodec": "none", "filesize": 1000},
                {"height": 1080, "vcodec": "vp09.00.50.08", "acodec": "none", "filesize": 700},
                {"height": 1080, "vcodec": "av01.0.08M.08", "acodec": "none", "filesize": 420},
                {"height": None, "vcodec": "none", "acodec": "opus", "filesize": 100},
            ],
        }
        md = parse_metadata(json.dumps(info))
        self.assertEqual(md.video_sizes, {1080: 1000})
        self.assertEqual(md.audio_size, 100)
        self.assertEqual(
            md.codec_sizes,
            {"avc": {1080: 1000}, "vp9": {1080: 700}, "av01": {1080: 420}},
        )


# ----------------------------------------------------------------------
# 2. Change recording type for queued items
# ----------------------------------------------------------------------


def make_item(url: str, code: str, label: str = "") -> QueueItem:
    return QueueItem(url=url, format_code=code, format_label=label or code)


class ChangeFormatTests(unittest.TestCase):
    def test_change_rekeys_in_place_and_resets_run_state(self) -> None:
        model = QueueModel()
        first = make_item(URL, formats_code_4320(), "YouTube 4320p (8K)")
        first.title = "Workout"
        first.filesize = 9_000_000_000
        first.status = Status.ERROR
        first.last_error = "boom"
        first.queue_attempts = 2
        first.output_path = "C:\\old.webm"
        second = make_item(URL, "bestaudio", "Single Audio (MP3)")
        model.add(first)
        model.add(second)

        self.assertTrue(
            model.change_format(first, formats_code_1080(), "YouTube 1080p (FHD)")
        )
        # Position preserved, keys/index updated.
        self.assertEqual(
            [i.format_code for i in model], [formats_code_1080(), "bestaudio"]
        )
        self.assertIs(model.get(f"{URL}\n{formats_code_1080()}"), first)
        self.assertIsNone(model.get(f"{URL}\n{formats_code_4320()}"))
        # Details kept, run state cleared.
        self.assertEqual(first.title, "Workout")
        self.assertEqual(first.format_label, "YouTube 1080p (FHD)")
        self.assertIs(first.status, Status.PENDING)
        self.assertEqual(first.queue_attempts, 0)
        self.assertEqual(first.last_error, "")
        self.assertEqual(first.output_path, "")
        self.assertIsNone(first.filesize)
        # Old key's row no longer resolves; URL bucket still fans out.
        self.assertEqual(len(model.items_for_url(URL)), 2)

    def test_change_to_already_queued_format_is_refused(self) -> None:
        model = QueueModel()
        first = make_item(URL, formats_code_4320())
        second = make_item(URL, formats_code_1080())
        model.add(first)
        model.add(second)

        self.assertFalse(
            model.change_format(first, formats_code_1080(), "YouTube 1080p (FHD)")
        )
        self.assertEqual(first.format_code, formats_code_4320())
        self.assertEqual(len(model), 2)

    def test_change_to_same_format_is_refused(self) -> None:
        model = QueueModel()
        only = make_item(URL, formats_code_1080())
        model.add(only)
        self.assertFalse(model.change_format(only, formats_code_1080(), "x"))
        self.assertEqual(only.format_label, formats_code_1080())

    def test_disable_subs_option_roundtrips(self) -> None:
        item = make_item(URL, formats_code_1080())
        item.options["DISABLE_SUBS"] = True
        restored = QueueItem.from_dict(item.to_dict())
        self.assertTrue(restored.options.get("DISABLE_SUBS"))
        # Unknown keys still rejected.
        hostile = item.to_dict()
        hostile["options"] = {"DISABLE_SUBS": True, "EVIL": "yes"}
        self.assertEqual(
            QueueItem.from_dict(hostile).options, {"DISABLE_SUBS": True}
        )


def formats_code_1080() -> str:
    from ytget_gui.formats import video_chain

    return video_chain(1080)


def formats_code_4320() -> str:
    from ytget_gui.formats import video_chain

    return video_chain(4320)


class ControllerChangeFormatTests(unittest.TestCase):
    def _controller(self, model: QueueModel):
        from ytget_gui.queue.controller import QueueController
        from ytget_gui.settings import AppSettings

        settings = AppSettings(
            DATA_DIR=Path(tempfile.mkdtemp()), DOWNLOADS_DIR=Path(tempfile.mkdtemp())
        )
        return QueueController(model, settings)

    def test_change_formats_reports_and_persists(self) -> None:
        model = QueueModel()
        a = make_item(URL, formats_code_4320(), "YouTube 4320p (8K)")
        b = make_item("https://example.com/watch?v=zzz", "bestaudio")
        model.add(a)
        model.add(b)
        controller = self._controller(model)

        changed = controller.change_formats(
            [a.key, b.key, "missing-key"], formats_code_1080(), "YouTube 1080p (FHD)"
        )
        self.assertEqual(changed, 2)
        self.assertEqual(a.format_code, formats_code_1080())
        self.assertEqual(a.format_label, "YouTube 1080p (FHD)")

    def test_subtitle_429_failure_marks_item_to_skip_subs(self) -> None:
        from ytget_gui.queue.controller import QueueController
        from ytget_gui.settings import AppSettings

        model = QueueModel()
        item = make_item(URL, formats_code_1080())
        model.add(item)
        with tempfile.TemporaryDirectory() as tmp:
            settings = AppSettings(
                DATA_DIR=Path(tmp) / "data", DOWNLOADS_DIR=Path(tmp) / "dl"
            )
            controller = QueueController(model, settings)
            controller._skip_requested = False
            controller._stop_requested = False
            item.last_error = SUBS_429
            controller._apply_outcome(item, 1)
            self.assertTrue(item.options.get("DISABLE_SUBS"))
            # Failed item is requeued, not dropped.
            self.assertIn(item, list(model))

    def test_option_reaches_worker_snapshot_command(self) -> None:
        # _build_worker applies item options onto the settings snapshot; a
        # DISABLE_SUBS item must not see --write-subs in its command.
        from ytget_gui.queue.controller import QueueController
        from ytget_gui.settings import AppSettings
        from ytget_gui.workers.download_worker import DownloadWorker

        model = QueueModel()
        item = make_item("https://example.com/watch?v=abc", formats_code_1080())
        item.options["DISABLE_SUBS"] = True
        model.add(item)
        with tempfile.TemporaryDirectory() as tmp:
            settings = AppSettings(
                DATA_DIR=Path(tmp) / "data", DOWNLOADS_DIR=Path(tmp) / "dl"
            )
            settings.WRITE_SUBS = True
            settings.SUB_LANGS = "en"
            controller = QueueController(model, settings)
            worker = controller._build_worker(item)
            self.assertIsInstance(worker, DownloadWorker)
            cmd = worker._build_command()
            self.assertNotIn("--write-subs", cmd)
            self.assertNotIn("--sub-langs", cmd)

            # Without the flag, subtitles are requested as usual.
            plain = make_item("https://example.com/watch?v=def", formats_code_1080())
            worker_plain = controller._build_worker(plain)
            cmd_plain = worker_plain._build_command()
            self.assertIn("--write-subs", cmd_plain)


# ----------------------------------------------------------------------
# 3. Subtitle rate-limit detection and in-worker retry handling
# ----------------------------------------------------------------------


class SubtitleRateLimitTests(unittest.TestCase):
    def test_matches_video_and_auto_captions_variants(self) -> None:
        self.assertTrue(is_subtitle_rate_limited(SUBS_429))
        self.assertTrue(
            is_subtitle_rate_limited(
                "ERROR: Unable to download subtitles for 'de': "
                "HTTP Error 429: Too Many Requests"
            )
        )
        self.assertTrue(
            is_subtitle_rate_limited(
                "ERROR: Unable to download automatic captions for 'en': "
                "HTTP Error 429"
            )
        )

    def test_ignores_other_failures(self) -> None:
        self.assertFalse(is_subtitle_rate_limited(""))
        self.assertFalse(
            is_subtitle_rate_limited("HTTP Error 429: Too Many Requests")
        )
        self.assertFalse(
            is_subtitle_rate_limited(
                "ERROR: Unable to download video subtitles for 'en': "
                "HTTP Error 404: Not Found"
            )
        )
        self.assertFalse(
            is_subtitle_rate_limited("ERROR: unable to download video data")
        )
        # A 429 on a different line does not disable subtitles.
        self.assertFalse(
            is_subtitle_rate_limited(
                "HTTP Error 429: Too Many Requests\n"
                "ERROR: Unable to download video subtitles for 'en': "
                "HTTP Error 404"
            )
        )

    def test_worker_drops_subtitle_flags_on_rate_limited_retry(self) -> None:
        from ytget_gui.settings import AppSettings

        with tempfile.TemporaryDirectory() as tmp:
            settings = AppSettings(
                DATA_DIR=Path(tmp) / "data", DOWNLOADS_DIR=Path(tmp) / "dl"
            )
            settings.WRITE_SUBS = True
            settings.SUB_LANGS = "en"
            worker = DownloadWorker(
                {"url": URL, "format_code": formats_code_1080()}, settings
            )
            worker._cmd = worker._build_command()
            worker._main_cmd = list(worker._cmd)
            self.assertIn("--write-subs", worker._cmd)

            worker._record_recent(
                "[info] Downloading subtitles: en\n" + SUBS_429 + "\n"
            )
            worker._drop_subs_if_rate_limited()

            self.assertTrue(getattr(worker.settings, "DISABLE_SUBS", False))
            self.assertNotIn("--write-subs", worker._cmd)
            self.assertNotIn("--sub-langs", worker._cmd)
            self.assertNotIn("en", worker._cmd[worker._cmd.index("--") - 1 :])
            # The rest of the command is untouched.
            self.assertEqual(
                worker._cmd, worker._without_flags(worker._main_cmd, [])
            )
            self.assertEqual(worker._subtitle_flags(), [])

    def test_worker_keeps_subs_when_429_is_elsewhere(self) -> None:
        from ytget_gui.settings import AppSettings

        with tempfile.TemporaryDirectory() as tmp:
            settings = AppSettings(
                DATA_DIR=Path(tmp) / "data", DOWNLOADS_DIR=Path(tmp) / "dl"
            )
            settings.WRITE_SUBS = True
            worker = DownloadWorker({"url": URL, "format_code": "bestaudio"}, settings)
            worker._cmd = worker._build_command()
            worker._record_recent(
                "ERROR: unable to download video data: HTTP Error 429"
            )
            worker._drop_subs_if_rate_limited()
            self.assertFalse(getattr(worker.settings, "DISABLE_SUBS", False))
            self.assertIn("--write-subs", worker._cmd)


# ----------------------------------------------------------------------
# 4. Queue card width bounding (UI, isolated process)
# ----------------------------------------------------------------------


class QueueCardWidthTests(unittest.TestCase):
    def test_long_titles_cannot_widen_the_queue(self) -> None:
        code = '''
from PySide6.QtWidgets import QApplication
from ytget_gui.queue.model import QueueItem, Status
from ytget_gui.widgets.queue_card import QueueCard

app = QApplication([])
url = "https://www.youtube.com/watch?v=KW2uFSpW3wo&pp=" + "x" * 200
title = "Nobadaddiction - BURN 500 CALORIES With This Standing Cardio " \
        "Workout - 30 Min Fat Burn (No Jumping, No Equipment)" + " " + "y" * 200
item = QueueItem(url=url, title=title, format_code="best", format_label="best")
item.status = Status.ERROR
item.last_error = "HTTP Error 429: Too Many Requests " * 5
card = QueueCard(item)
hint = card.sizeHint()
assert hint.width() <= 900, hint.width()

# Once hosted at a narrow width, both text lines elide to fit it. The card
# is hosted the way the queue list hosts it (geometry set by a parent) --
# a top-level resize/activate would fall back to its own size hint.
from PySide6.QtWidgets import QWidget

host = QWidget()
card.setParent(host)
card.setGeometry(0, 0, 380, hint.height())
host.show()
app.processEvents()
assert card.width() <= 380, card.width()
assert card.title_lbl.fontMetrics().horizontalAdvance(card.title_lbl.text()) <= 384
assert card.meta_lbl.fontMetrics().horizontalAdvance(card.meta_lbl.text()) <= 384
assert not card.title_lbl.wordWrap()
print("Card width passed")
'''
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            timeout=60, env=env, cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Card width passed", result.stdout)


# ----------------------------------------------------------------------
# 5. Request pacing preset (Advanced › Request pacing)
# ----------------------------------------------------------------------


class RequestPacingPresetTests(unittest.TestCase):
    def _worker(self, settings) -> DownloadWorker:
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.instance() or QCoreApplication([])
        return DownloadWorker(
            {"url": URL, "title": "t", "format_code": "best"}, settings
        )

    def _settings(self, **overrides):
        from ytget_gui.settings import AppSettings

        with tempfile.TemporaryDirectory() as tmp:
            settings = AppSettings(
                DATA_DIR=Path(tmp) / "data", DOWNLOADS_DIR=Path(tmp) / "dl"
            )
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def test_sleep_preset_flags_reach_command(self) -> None:
        worker = self._worker(self._settings(REQUEST_PACING="sleep", EXTRA_YTDLP_ARGS=""))
        cmd = worker._build_command()
        for flag, value in (
            ("--sleep-subtitles", "5"),
            ("--sleep-requests", "0.75"),
            ("--sleep-interval", "10"),
            ("--max-sleep-interval", "20"),
        ):
            self.assertIn(flag, cmd)
            self.assertEqual(cmd[cmd.index(flag) + 1], value)

    def test_off_by_default_adds_no_pacing_flags(self) -> None:
        worker = self._worker(self._settings(EXTRA_YTDLP_ARGS=""))
        cmd = worker._build_command()
        self.assertFalse([tok for tok in cmd if tok.startswith("--sleep")])

    def test_custom_values_reach_command(self) -> None:
        worker = self._worker(
            self._settings(
                REQUEST_PACING="custom",
                EXTRA_YTDLP_ARGS="",
                SLEEP_SUBTITLES=2,
                SLEEP_REQUESTS=1.5,
                SLEEP_INTERVAL=3,
                MAX_SLEEP_INTERVAL=8,
            )
        )
        cmd = worker._build_command()
        for flag, value in (
            ("--sleep-subtitles", "2"),
            ("--sleep-requests", "1.5"),
            ("--sleep-interval", "3"),
            ("--max-sleep-interval", "8"),
        ):
            self.assertIn(flag, cmd)
            self.assertEqual(cmd[cmd.index(flag) + 1], value)

    def test_custom_defaults_match_sleep_preset(self) -> None:
        # A fresh Custom selection emits exactly the recommended spacing.
        settings = self._settings(REQUEST_PACING="custom", EXTRA_YTDLP_ARGS="")
        self.assertEqual(
            DownloadWorker._custom_pacing_flags(settings),
            REQUEST_PACING_PRESETS["sleep"],
        )

    def test_custom_clamps_max_below_interval(self) -> None:
        # yt-dlp requires max >= base; the worker repairs an inverted pair.
        worker = self._worker(
            self._settings(
                REQUEST_PACING="custom",
                EXTRA_YTDLP_ARGS="",
                SLEEP_INTERVAL=10,
                MAX_SLEEP_INTERVAL=4,
            )
        )
        cmd = worker._build_command()
        self.assertEqual(cmd[cmd.index("--sleep-interval") + 1], "10")
        self.assertEqual(cmd[cmd.index("--max-sleep-interval") + 1], "10")

    def test_validator_accepts_custom_and_clamps_numbers(self) -> None:
        from ytget_gui.settings import _VALIDATORS

        self.assertEqual(_VALIDATORS["REQUEST_PACING"]("custom"), "custom")
        self.assertEqual(_VALIDATORS["REQUEST_PACING"]("bogus"), "off")
        self.assertEqual(_VALIDATORS["SLEEP_REQUESTS"]("junk"), 0.75)
        self.assertEqual(_VALIDATORS["SLEEP_REQUESTS"]("-5"), 0.0)
        self.assertEqual(_VALIDATORS["SLEEP_INTERVAL"](99999), 3600.0)
        self.assertEqual(_VALIDATORS["SLEEP_SUBTITLES"](2), 2.0)

    def test_extra_arguments_take_precedence_over_preset(self) -> None:
        # The preset is appended before the user's extra arguments, so a
        # typed --sleep-interval overrides the preset's (last value wins).
        worker = self._worker(
            self._settings(REQUEST_PACING="sleep", EXTRA_YTDLP_ARGS="--sleep-interval 60")
        )
        cmd = worker._build_command()
        self.assertEqual(cmd.count("--sleep-interval"), 2)
        self.assertEqual(cmd[cmd.index("--sleep-interval") + 1], "10")
        self.assertEqual(cmd[cmd.index("--sleep-interval", cmd.index("--sleep-interval") + 1) + 1], "60")

    def test_validator_normalises_unknown_preset(self) -> None:
        from ytget_gui.settings import _VALIDATORS

        self.assertEqual(_VALIDATORS["REQUEST_PACING"]("bogus"), "off")
        self.assertEqual(_VALIDATORS["REQUEST_PACING"]("sleep"), "sleep")


# ----------------------------------------------------------------------
# 6. Change-recording-type dialog width
# ----------------------------------------------------------------------


class ChangeTypeDialogWidthTests(unittest.TestCase):
    def test_dialog_is_about_30_percent_wider(self) -> None:
        code = '''
from PySide6.QtWidgets import QApplication
from ytget_gui.main_window import _change_type_dialog, _TYPE_DIALOG_WIDEN
from ytget_gui.formats import build_resolution_presets

app = QApplication([])
presets = list(build_resolution_presets().keys())
dialog, box = _change_type_dialog(None, 2, "1080p (FHD \u00b7 720p (HD", presets, presets[0])
hint = dialog.sizeHint().width()
expected = int(hint * _TYPE_DIALOG_WIDEN)
assert dialog.minimumWidth() == expected, (dialog.minimumWidth(), expected)
assert dialog.minimumWidth() >= hint * 1.25, (dialog.minimumWidth(), hint)
assert box.count() == len(presets)
assert box.currentText() == presets[0]
print("Dialog width passed")
'''
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            timeout=60, env=env, cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dialog width passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
