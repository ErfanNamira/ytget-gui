"""2.8.4 quality regressions using yt-dlp's real, offline selection engine."""
from __future__ import annotations

import copy
import json
import plistlib
import tempfile
import types
import unittest
from pathlib import Path

from yt_dlp import YoutubeDL

from ytget_gui import _version, formats
from ytget_gui.queue.model import QueueItem, QueueModel
from ytget_gui.settings import AppSettings
from ytget_gui.workers import fetch_core
from ytget_gui.workers.download_worker import DownloadWorker

URL = "https://www.youtube.com/watch?v=PNf4ks0fxig"


def video(fid, height, bitrate, codec="avc1.640028", protocol="https", fps=25, **extra):
    return dict(format_id=str(fid), url=f"https://example.invalid/{fid}.mp4",
                height=height, width=round(height * 16 / 9), fps=fps,
                vcodec=codec, acodec="none", tbr=bitrate, vbr=bitrate,
                ext="mp4", protocol=protocol, **extra)


def audio(fid="251", codec="opus", bitrate=110):
    return dict(format_id=fid, url=f"https://example.invalid/{fid}.webm",
                vcodec="none", acodec=codec, abr=bitrate,
                ext="webm" if codec == "opus" else "m4a")


def sample_formats():
    # Same relevant ladder as the user's report. Extractor preferences and
    # estimates intentionally favour DASH, while HLS has the higher vbr.
    return [video(160, 144, 99), video(269, 144, 196, protocol="m3u8_native"),
            video(134, 360, 406), video(230, 360, 871, protocol="m3u8_native"),
            video(243, 360, 282, codec="vp9"),
            video(605, 360, 567, codec="vp09.00.21.08", protocol="m3u8_native"),
            video(136, 720, 1675), video(232, 720, 2593, protocol="m3u8_native"),
            video(137, 1080, 3395, quality=10, source_preference=10, filesize=45801700),
            video(270, 1080, 5152, protocol="m3u8_native", quality=-1,
                  source_preference=-1, filesize_approx=69552000),
            audio(), audio("140", "mp4a.40.2", 130)]


def select(candidates, selector=None, *, ranked=True):
    opts = {"quiet": True, "no_warnings": True,
            "format": selector or formats.video_chain(1080)}
    if ranked:
        opts.update(format_sort=formats.VIDEO_FORMAT_SORT.split(","), format_sort_force=True)
    with YoutubeDL(opts) as ydl:
        return ydl.process_ie_result({"id": "fixture", "title": "Fixture",
                                     "formats": copy.deepcopy(candidates)}, download=False)


def legacy_code(height=1080, width=None):
    cap = f"[height<={height}]" + (f"[width<={width}]" if width else "")
    return "/".join((
        f"bestvideo{cap}[vcodec^=av01][protocol!*=m3u8]+bestaudio",
        f"bestvideo{cap}[vcodec~='^vp0?9'][protocol!*=m3u8]+bestaudio",
        f"bestvideo{cap}[protocol!*=m3u8]+bestaudio",
        f"bestvideo{cap}+bestaudio", f"best{cap}"))


class QualitySelectionTests(unittest.TestCase):
    def test_old_selector_reproduces_reported_360p_bug(self):
        self.assertEqual(select(sample_formats(), legacy_code(), ranked=False)["format_id"], "243+251")

    def test_sample_selects_270_plus_251(self):
        info = select(sample_formats())
        self.assertEqual(info["format_id"], "270+251")
        self.assertEqual(info["height"], 1080)

    def test_dash_137_still_works_when_270_is_unavailable(self):
        candidates = [f for f in sample_formats() if f["format_id"] != "270"]
        self.assertEqual(select(candidates)["format_id"], "137+251")

    def test_720_av1_cannot_beat_1080_avc(self):
        candidates = [video(1, 720, 2000, "av01.0.08M.08"), video(2, 1080, 3000), audio()]
        self.assertEqual(select(candidates)["format_id"], "2+251")

    def test_360_dash_cannot_beat_1080_hls(self):
        candidates = [video(243, 360, 282, "vp9"),
                      video(270, 1080, 5152, protocol="m3u8_native"), audio()]
        self.assertEqual(select(candidates)["format_id"], "270+251")

    def test_higher_resolution_beats_higher_bitrate(self):
        candidates = [video(1, 720, 9000), video(2, 1080, 3000), audio()]
        self.assertEqual(select(candidates)["format_id"], "2+251")

    def test_framerate_precedes_bitrate_within_resolution(self):
        candidates = [video(1, 1080, 9000, fps=25), video(2, 1080, 3000, fps=60), audio()]
        self.assertEqual(select(candidates)["format_id"], "2+251")

    def test_larger_file_estimate_does_not_override_bitrate(self):
        candidates = [video(1, 1080, 3000, filesize=900000000),
                      video(2, 1080, 4000, filesize_approx=100000000), audio()]
        self.assertEqual(select(candidates)["format_id"], "2+251")

    def test_resolution_cap_is_preserved(self):
        candidates = sample_formats() + [video(999, 2160, 12000)]
        self.assertEqual(select(candidates)["height"], 1080)

    def test_missing_target_height_uses_next_best_below_cap(self):
        candidates = [f for f in sample_formats() if f.get("height", 0) < 1080]
        self.assertEqual(select(candidates)["format_id"], "232+251")

    def test_universal_preset_retains_width_cap(self):
        candidates = [video(1, 1080, 3000), video(2, 1080, 9000), audio()]
        candidates[1]["width"] = 2400
        self.assertEqual(select(candidates, formats.video_chain(1080, 1920))["format_id"], "1+251")

    def test_progressive_1080_beats_separate_360(self):
        candidates = [video(243, 360, 282, "vp9"), video(22, 1080, 5000), audio()]
        candidates[1]["acodec"] = "mp4a.40.2"
        candidates[1]["abr"] = 130
        self.assertEqual(select(candidates)["format_id"], "22")

    def test_progressive_only_site_needs_no_audio_only_stream(self):
        muxed = video(18, 720, 2000)
        muxed["acodec"] = "mp4a.40.2"
        self.assertEqual(select([muxed])["format_id"], "18")

    def test_explicit_format_ids_remain_explicit(self):
        self.assertEqual(select(sample_formats(), "137+251")["format_id"], "137+251")

    def test_webm_output_does_not_select_incompatible_h264(self):
        selector = formats.webm_compatible_selector(formats.video_chain(1080))
        candidates = sample_formats() + [video(248, 1080, 2800, "vp9")]
        self.assertEqual(select(candidates, selector)["format_id"], "248+251")

    def test_webm_progressive_fallback_is_also_codec_safe(self):
        selector = formats.webm_compatible_selector(formats.video_chain(1080))
        self.assertEqual(selector.count("[vcodec~="), 2)
        self.assertEqual(selector.count("[acodec~="), 2)
        self.assertEqual(formats.webm_compatible_selector("137+140"), "137+140")


class PersistedPresetTests(unittest.TestCase):
    def test_all_twelve_builtins_upgrade(self):
        for h, w in ((4320, 7680), (2160, 3840), (1440, 2560),
                     (1080, 1920), (720, 1280), (480, 854)):
            for width in (None, w):
                with self.subTest(height=h, width=width):
                    self.assertEqual(formats.normalise_video_selector(legacy_code(h, width)),
                                     formats.video_chain(h, width))

    def test_custom_selectors_are_untouched(self):
        for code in ("251+270", "137+140", "bestvideo[vcodec^=av01]+bestaudio",
                     "bestaudio", "best", ""):
            self.assertEqual(formats.normalise_video_selector(code), code)

    def test_loaded_queue_identity_matches_new_preset(self):
        old = QueueItem.from_dict({"url": URL, "format_code": legacy_code(), "format_label": "1080p"})
        new = QueueItem(url=URL, format_code=formats.video_chain(1080))
        self.assertEqual(old.key, new.key)
        model = QueueModel()
        self.assertTrue(model.add(old))
        self.assertFalse(model.add(new))

    def test_worker_resolves_old_code_even_without_queue_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = AppSettings(DATA_DIR=Path(tmp) / "data", DOWNLOADS_DIR=Path(tmp) / "dl")
            self.assertEqual(s.resolve_format_code(legacy_code()), formats.video_chain(1080))
            self.assertEqual(s.resolve_format_code("1080p"), formats.video_chain(1080))
            self.assertEqual(s.resolve_format_code("251+270"), "251+270")
            worker = DownloadWorker({"url": URL, "format_code": legacy_code()}, s)
            cmd = worker._build_command()
            self.assertEqual(cmd[cmd.index("-f") + 1], formats.video_chain(1080))
            self.assertEqual(cmd[cmd.index("--format-sort") + 1], formats.VIDEO_FORMAT_SORT)
            self.assertIn("--format-sort-force", cmd)
            self.assertEqual(cmd[-2:], ["--", URL])


class MetadataParityTests(unittest.TestCase):
    def test_runtime_and_cookie_precedence_match_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            s.DENO_PATH = root / "deno"
            s.DENO_PATH.touch()
            s.COOKIES_PATH.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            s.COOKIES_FROM_BROWSER = "firefox"
            metadata = fetch_core.build_command(URL, s.YT_DLP_PATH, s.FFMPEG_PATH.parent,
                                                s.COOKIES_PATH, "", s)
            worker = DownloadWorker({"url": URL, "format_code": "1080p"}, s)
            download = worker._build_command()
            for cmd in (metadata, download):
                self.assertIn("--cookies", cmd)
                self.assertNotIn("--cookies-from-browser", cmd)
                self.assertEqual(cmd[cmd.index("--js-runtimes") + 1], f"deno:{s.DENO_PATH}")

    def test_explicit_browser_override_still_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "cookies.txt"
            cookie.write_text("# cookies\n")
            cmd = fetch_core.build_command(URL, Path("yt-dlp"), Path("."), cookie, "",
                                           types.SimpleNamespace(), cookies_from_browser="firefox",
                                           cookies_profile="Profile A")
            self.assertNotIn("--cookies", cmd)
            self.assertEqual(cmd[cmd.index("--cookies-from-browser") + 1], "firefox:Profile A")

    def test_missing_runtime_not_added(self):
        self.assertEqual(fetch_core.runtime_flags(types.SimpleNamespace(DENO_PATH=Path("/missing/deno"))), [])


class DefensiveDataTests(unittest.TestCase):
    def test_nonfinite_queue_size_does_not_crash_startup(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            item = QueueItem.from_dict({"url": URL, "filesize": value})
            self.assertIsNone(item.filesize)

    def test_above_cap_is_not_advertised_as_available(self):
        self.assertIsNone(formats.estimate_download_size({2160: 4000}, 100, formats.video_chain(720)))


class ReleaseVersionTests(unittest.TestCase):
    def test_release_surfaces_are_consistent(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(_version.__version__, "2.8.4")
        import tomllib
        self.assertEqual(tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"], "2.8.4.0")
        plist = plistlib.loads((root / "Info.plist").read_bytes())
        self.assertEqual(plist["CFBundleVersion"], "2.8.4")
        self.assertEqual(plist["CFBundleShortVersionString"], "2.8.4")
        self.assertIn("filevers=(2, 8, 4, 0)", (root / "version_info.txt").read_text())


if __name__ == "__main__":
    unittest.main()
