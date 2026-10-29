"""User-selectable video codec/bitrate ordering, persistence and UI regressions."""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from yt_dlp import YoutubeDL
from ytget_gui import formats
from ytget_gui.settings import AppSettings
from ytget_gui.workers.download_worker import DownloadWorker
from tests.test_v284_quality import video, audio, sample_formats


def choose(candidates, codec="auto", priority="balanced", container="mkv", selector=None):
    selector = selector or formats.video_chain(1080)
    if container == "webm":
        selector = formats.webm_compatible_selector(selector)
    with YoutubeDL({"quiet": True, "no_warnings": True, "format": selector,
                   "format_sort": formats.video_format_sort(codec, priority, container).split(","),
                   "format_sort_force": True}) as ydl:
        info = ydl.process_ie_result(dict(id="test", title="Test", formats=copy.deepcopy(candidates)),
                                     download=False)
        return info["format_id"]


class VideoPreferenceSelectionTests(unittest.TestCase):
    def test_default_keeps_previous_sort(self):
        self.assertEqual(formats.video_format_sort(), formats.VIDEO_FORMAT_SORT)

    def test_highest_bitrate_can_precede_higher_fps(self):
        ladder = [video(1, 1080, 3000, fps=60), video(2, 1080, 5000, fps=25), audio()]
        self.assertEqual(choose(ladder), "1+251")
        self.assertEqual(choose(ladder, priority="bitrate"), "2+251")

    def test_each_preferred_codec_wins_within_same_resolution(self):
        ladder = [video(1, 1080, 1000, "av01.0.08M.08"),
                  video(2, 1080, 2000, "vp09.00.50.08"),
                  video(3, 1080, 9000, "avc1.640028"), audio()]
        for codec, expected in (("av1", "1"), ("vp9", "2"), ("h264", "3")):
            with self.subTest(codec=codec):
                self.assertEqual(choose(ladder, codec, "codec"), expected + "+251")

    def test_codec_first_can_precede_fps(self):
        ladder = [video(1, 1080, 3000, "av01.0.08M.08", fps=25),
                  video(2, 1080, 5000, fps=60), audio()]
        self.assertEqual(choose(ladder, "av1", "codec"), "1+251")

    def test_codec_never_causes_lower_resolution(self):
        ladder = [video(1, 360, 6000, "av01.0.08M.08"), video(2, 1080, 3000), audio()]
        for mode in ("balanced", "bitrate", "codec"):
            self.assertEqual(choose(ladder, "av1", mode), "2+251")

    def test_higher_bitrate_never_causes_lower_resolution(self):
        ladder = [video(1, 720, 10000), video(2, 1080, 3000), audio()]
        self.assertEqual(choose(ladder, priority="bitrate"), "2+251")

    def test_missing_codec_falls_back_instead_of_failing(self):
        self.assertEqual(choose([video(1, 1080, 3000), audio()], "av1", "codec"), "1+251")

    def test_highest_bitrate_mode_outweighs_preferred_codec(self):
        ladder = [video(1, 1080, 1000, "av01.0.08M.08"), video(2, 1080, 6000), audio()]
        self.assertEqual(choose(ladder, "av1", "bitrate"), "2+251")

    def test_preferred_codec_breaks_equal_bitrate_ties(self):
        ladder = [video(1, 1080, 3000, "av01.0.08M.08"), video(2, 1080, 3000), audio()]
        self.assertEqual(choose(ladder, "h264", "bitrate"), "2+251")

    def test_cap_applies_in_all_modes(self):
        ladder = [video(1, 1080, 3000), video(2, 2160, 10000, "av01.0.08M.08"), audio()]
        for mode in ("balanced", "bitrate", "codec"):
            self.assertEqual(choose(ladder, "av1", mode), "1+251")

    def test_webm_ignores_incompatible_h264_preference(self):
        ladder = [video(1, 1080, 2000, "av01.0.08M.08"),
                  video(2, 1080, 3000, "vp9"), video(3, 1080, 6000), audio()]
        self.assertEqual(choose(ladder, "h264", "codec", "webm"), "1+251")

    def test_audio_ranking_not_changed(self):
        for codec in ("auto", "av1", "vp9", "h264"):
            for mode in ("balanced", "bitrate", "codec"):
                self.assertTrue(choose(sample_formats(), codec, mode).endswith("+251"))

    def test_explicit_ids_are_preserved(self):
        self.assertEqual(choose(sample_formats(), "vp9", "codec", selector="137+251"), "137+251")

    def test_invalid_values_are_safe(self):
        self.assertEqual(formats.video_format_sort("bad", "bad"), formats.VIDEO_FORMAT_SORT)


class VideoPreferenceSettingsTests(unittest.TestCase):
    def test_save_load_and_download_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            s.apply({"VIDEO_CODEC": "vp9", "VIDEO_SELECTION_PRIORITY": "codec"})
            self.assertTrue(s.save_config())
            restored = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            self.assertEqual(restored.VIDEO_CODEC, "vp9")
            self.assertEqual(restored.VIDEO_SELECTION_PRIORITY, "codec")
            worker = DownloadWorker({"url": "https://youtube.com/watch?v=PNf4ks0fxig",
                                     "format_code": "1080p"}, restored)
            cmd = worker._build_command()
            self.assertEqual(cmd[cmd.index("--format-sort") + 1], "res,vcodec:vp9.2,fps,vbr")
            self.assertIn("--format-sort-force", cmd)

    def test_older_configs_get_compatible_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            s.CONFIG_PATH.write_text('{"_schema": "2.8.3"}')
            s.load_config()
            self.assertEqual(s.VIDEO_CODEC, "auto")
            self.assertEqual(s.VIDEO_SELECTION_PRIORITY, "balanced")

    def test_corrupt_config_values_are_sanitised(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = AppSettings(DATA_DIR=Path(tmp) / "data", DOWNLOADS_DIR=Path(tmp) / "dl")
            s.apply({"VIDEO_CODEC": "bad", "VIDEO_SELECTION_PRIORITY": "bad"})
            self.assertEqual(s.VIDEO_CODEC, "auto")
            self.assertEqual(s.VIDEO_SELECTION_PRIORITY, "balanced")


class VideoPreferenceDialogTests(unittest.TestCase):
    def test_dialog_load_edit_reset_save_and_webm_warning(self):
        # Existing tests may have created QCoreApplication; widgets require
        # QApplication, so run this UI check in its own isolated process.
        code = '''
from pathlib import Path
import tempfile
from PySide6.QtWidgets import QApplication
from ytget_gui.settings import AppSettings
from ytget_gui.dialogs.preferences import PreferencesDialog
app = QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    s = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
    s.VIDEO_CODEC = "vp9"
    s.VIDEO_SELECTION_PRIORITY = "bitrate"
    dialog = PreferencesDialog(None, s)
    assert dialog.get_settings()["VIDEO_CODEC"] == "vp9"
    assert dialog.get_settings()["VIDEO_SELECTION_PRIORITY"] == "bitrate"
    assert "then video bitrate, then frame rate" in dialog.video_quality_hint.text()
    dialog.video_codec.setCurrentIndex(3)
    dialog.video_container.setCurrentText(".webm")
    assert "H.264 is not supported in WebM" in dialog.video_quality_hint.text()
    dialog._reset()
    assert dialog.get_settings()["VIDEO_CODEC"] == "vp9"
    assert dialog.get_settings()["VIDEO_SELECTION_PRIORITY"] == "bitrate"
    assert dialog.video_container.currentText() == ".mkv"
    assert "H.264 is not supported in WebM" not in dialog.video_quality_hint.text()
    dialog.video_codec.setCurrentIndex(1)
    dialog.video_priority.setCurrentIndex(2)
    dialog.apply()
    restored = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
    assert restored.VIDEO_CODEC == "av1"
    assert restored.VIDEO_SELECTION_PRIORITY == "codec"
    dialog.close()
print("Preference UI passed")
'''
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Preference UI passed", result.stdout)
