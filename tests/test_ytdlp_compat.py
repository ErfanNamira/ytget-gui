"""yt-dlp 2026.10+ compatibility regressions (shipped in 2.8.5).

Covers the three defences against "Requested format is not available":
the Deno version gate, the metadata-fetch fallback chain, and the
worker/controller dropping a pinned player client that yields no formats.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ytget_gui import formats
from ytget_gui.queue.model import QueueItem, QueueModel, Status
from ytget_gui.settings import AppSettings, YOUTUBE_PLAYER_CLIENTS, _VALIDATORS
from ytget_gui.workers import fetch_core, proc
from ytget_gui.workers.download_worker import (
    CHALLENGE_SOLVER_FIX_MESSAGE,
    DownloadWorker,
    is_challenge_solver_failure,
)
from ytget_gui.workers.fetch_core import is_format_selection_error, build_command

URL = "https://www.youtube.com/watch?v=TKJysqiyjVU"

FORMAT_ERROR = (
    "ERROR: [youtube] TKJysqiyjVU: Requested format is not available. "
    "Use --list-formats for a list of available formats"
)


def make_settings(tmp: str) -> AppSettings:
    return AppSettings(
        DATA_DIR=Path(tmp) / "data", DOWNLOADS_DIR=Path(tmp) / "dl"
    )


def chain_1080() -> str:
    return formats.video_chain(1080)


def make_item(url: str = URL, code: str = "") -> QueueItem:
    return QueueItem(url=url, format_code=code or chain_1080(), format_label="1080p")


# ----------------------------------------------------------------------
# 1. Format-selection error detection
# ----------------------------------------------------------------------


class FormatSelectionErrorTests(unittest.TestCase):
    def test_matches_the_known_wordings(self) -> None:
        self.assertTrue(is_format_selection_error(FORMAT_ERROR))
        self.assertTrue(is_format_selection_error(
            "ERROR: [youtube] x: Only images are available for download. "
            "Use --list-formats"))
        self.assertTrue(is_format_selection_error(
            "ERROR: [youtube] x: no video formats"))

    def test_ignores_unrelated_failures(self) -> None:
        self.assertFalse(is_format_selection_error(""))
        self.assertFalse(is_format_selection_error(
            "ERROR: Unable to download video subtitles for 'en': "
            "HTTP Error 429: Too Many Requests"))
        self.assertFalse(is_format_selection_error(
            "ERROR: Sign in to confirm you're not a bot"))


# ----------------------------------------------------------------------
# 2. Deno version gate
# ----------------------------------------------------------------------


class _FakeSettings:
    def __init__(self, deno_path) -> None:
        self.DENO_PATH = deno_path


def _deno_output(version: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        [], 0, f"deno {version} (stable, release, x86_64-pc-windows-msvc)\n"
               "v8 14.0.0\ntypescript 5.9.0",
        "",
    )


class DenoVersionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        proc._deno_version_cached.cache_clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.deno = Path(self._tmp.name) / "bin" / "deno.exe"
        self.deno.parent.mkdir()
        self.deno.write_text("fake")

    def tearDown(self) -> None:
        proc._deno_version_cached.cache_clear()

    def _probe(self, version: str):
        """(settings, run inside the mocked probe) for one fake binary."""
        target = self.deno.with_name(f"deno-{version}.exe")
        target.write_text("fake")
        settings = _FakeSettings(target)
        return settings, mock.patch.object(
            proc, "run", return_value=_deno_output(version)
        )

    def test_version_is_parsed_and_supported_above_floor(self) -> None:
        for version in ("2.3.0", "2.5.6"):
            settings, patcher = self._probe(version)
            with patcher:
                self.assertEqual(proc.deno_version(settings), tuple(map(int, version.split("."))))
                self.assertTrue(proc.deno_supported_for_ytdlp(settings))

    def test_old_deno_is_rejected(self) -> None:
        settings, patcher = self._probe("2.1.4")
        with patcher:
            self.assertEqual(proc.deno_version(settings), (2, 1, 4))
            self.assertFalse(proc.deno_supported_for_ytdlp(settings))

    def test_unprovable_deno_keeps_old_behaviour(self) -> None:
        with mock.patch.object(
            proc, "run", side_effect=OSError("no such binary")
        ):
            self.assertIsNone(proc.deno_version(_FakeSettings(self.deno)))
        self.assertTrue(proc.deno_supported_for_ytdlp(_FakeSettings(self.deno)))
        # Missing file: same "do not change behaviour" answer.
        self.assertTrue(
            proc.deno_supported_for_ytdlp(_FakeSettings(Path("nope") / "deno.exe"))
        )

    def test_runtime_flags_pin_only_a_supported_deno(self) -> None:
        settings = _FakeSettings(self.deno)
        with mock.patch.object(
            fetch_core.proc, "deno_supported_for_ytdlp", return_value=True
        ):
            self.assertEqual(
                fetch_core.runtime_flags(settings),
                ["--js-runtimes", f"deno:{self.deno}"],
            )
        with mock.patch.object(
            fetch_core.proc, "deno_supported_for_ytdlp", return_value=False
        ):
            # The old binary exists (so the plain is_file() check passes)
            # but must not be forced onto yt-dlp.
            self.assertEqual(fetch_core.runtime_flags(settings), [])

    def test_old_deno_stays_off_the_subprocess_path(self) -> None:
        settings = _FakeSettings(self.deno)
        with mock.patch.object(
            proc, "deno_supported_for_ytdlp", return_value=False
        ):
            env = proc.tool_env(settings)
            self.assertNotIn(str(self.deno.parent), env.get("PATH", ""))
        with mock.patch.object(
            proc, "deno_supported_for_ytdlp", return_value=True
        ):
            env = proc.tool_env(settings)
            self.assertIn(str(self.deno.parent), env.get("PATH", ""))


# ----------------------------------------------------------------------
# 3. Metadata fetch fallback chain
# ----------------------------------------------------------------------


class FetchFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.settings = make_settings(self._tmp.name)
        self.settings.YOUTUBE_PLAYER_CLIENT = "android"
        self.cookies = Path(self._tmp.name) / "cookies.txt"
        self.cookies.write_text("dummy")
        self.ytdlp = Path(self._tmp.name) / "yt-dlp.exe"
        self.ytdlp.write_text("fake")

    def _payload(self, title: str = "A title") -> str:
        import json

        return json.dumps({
            "id": "TKJysqiyjVU",
            "title": title,
            "formats": [
                {"height": 1080, "vcodec": "avc1.640028", "acodec": "none",
                 "filesize": 1000},
            ],
        })

    def test_fetch_recovers_without_the_pinned_client(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, env, timeout=120, on_process_started=None):
            calls.append(cmd)
            if len(calls) == 1:
                return 1, "", FORMAT_ERROR
            return 0, self._payload(), ""

        with mock.patch.object(fetch_core, "run_yt_dlp", side_effect=fake_run):
            result = fetch_core.fetch_metadata(
                url=URL,
                yt_dlp_path=self.ytdlp,
                ffmpeg_dir=Path(self._tmp.name),
                cookies_path=None,
                proxy_url="",
                settings=self.settings,
            )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.metadata.format_fallback, "player_client")
        self.assertEqual(len(calls), 2)
        self.assertIn("--extractor-args", calls[0])
        self.assertNotIn("--extractor-args", calls[1])

    def test_second_fallback_drops_cookies(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, env, timeout=120, on_process_started=None):
            calls.append(cmd)
            if len(calls) <= 2:
                return 1, "", FORMAT_ERROR
            return 0, self._payload(), ""

        self.settings.COOKIES_FROM_BROWSER = ""  # cookies come from the file
        with mock.patch.object(fetch_core, "run_yt_dlp", side_effect=fake_run):
            result = fetch_core.fetch_metadata(
                url=URL,
                yt_dlp_path=self.ytdlp,
                ffmpeg_dir=Path(self._tmp.name),
                cookies_path=self.cookies,
                proxy_url="",
                settings=self.settings,
            )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.metadata.format_fallback, "cookies")
        self.assertEqual(len(calls), 3)
        self.assertIn("--cookies", calls[0])
        self.assertIn("--cookies", calls[1])
        self.assertNotIn("--cookies", calls[2])

    def test_unrelated_error_is_returned_without_fallback(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, env, timeout=120, on_process_started=None):
            calls.append(cmd)
            return 1, "", "ERROR: Sign in to confirm you're not a bot"

        with mock.patch.object(fetch_core, "run_yt_dlp", side_effect=fake_run):
            result = fetch_core.fetch_metadata(
                url=URL,
                yt_dlp_path=self.ytdlp,
                ffmpeg_dir=Path(self._tmp.name),
                cookies_path=None,
                proxy_url="",
                settings=self.settings,
            )

        self.assertFalse(result.ok)
        self.assertEqual(len(calls), 1)
        self.assertIn("Sign in", result.error or "")

    def test_error_keeps_the_diagnostic_warnings(self) -> None:
        stderr = (
            "WARNING: Skipping client \"android\" since it does not support cookies\n"
            "WARNING: xyz client formats require a GVS PO Token which was not provided\n"
            "WARNING: irrelevant noise\n"
            + FORMAT_ERROR
        )

        def fake_run(cmd, env, timeout=120, on_process_started=None):
            return 1, "", stderr

        with mock.patch.object(fetch_core, "run_yt_dlp", side_effect=fake_run):
            result = fetch_core.fetch_metadata(
                url=URL,
                yt_dlp_path=self.ytdlp,
                ffmpeg_dir=Path(self._tmp.name),
                cookies_path=None,
                proxy_url="",
                settings=self.settings,
            )

        self.assertFalse(result.ok)
        self.assertIn("Requested format is not available", result.error)
        self.assertIn("Skipping client", result.error)
        self.assertIn("PO Token", result.error)
        self.assertNotIn("irrelevant noise", result.error)

    def test_command_keeps_warnings_enabled(self) -> None:
        cmd = build_command(
            URL, self.ytdlp, Path(self._tmp.name), None, "", self.settings
        )
        self.assertNotIn("--no-warnings", cmd)

    def test_payload_carries_the_fallback_flag(self) -> None:
        md = fetch_core.parse_metadata(self._payload())
        md = fetch_core.dataclass_replace(md, format_fallback="player_client")
        payload = fetch_core.metadata_payload(md)
        self.assertEqual(payload["format_fallback"], "player_client")
        import json

        json.dumps(payload)  # must survive the queued-signal round trip


# ----------------------------------------------------------------------
# 4. Worker drops the pinned client on format-selection retries
# ----------------------------------------------------------------------


class WorkerDropClientTests(unittest.TestCase):
    def _worker(self, tmp: str, player_client: str = "android") -> DownloadWorker:
        settings = make_settings(tmp)
        settings.YOUTUBE_PLAYER_CLIENT = player_client
        return DownloadWorker(
            {"url": URL, "format_code": chain_1080()}, settings
        )

    def test_worker_drops_client_flags_on_format_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worker = self._worker(tmp)
            worker._cmd = worker._build_command()
            worker._main_cmd = list(worker._cmd)
            self.assertIn("--extractor-args", worker._cmd)
            self.assertTrue(worker._applied_client_flags)

            worker._record_recent(FORMAT_ERROR + "\n")
            worker._drop_client_if_format_error()

            self.assertNotIn("--extractor-args", worker._cmd)
            self.assertNotIn("player_client=android", " ".join(worker._cmd))
            self.assertEqual(worker._applied_client_flags, [])
            # Settings snapshot stays consistent for any later rebuild.
            self.assertEqual(worker.settings.YOUTUBE_PLAYER_CLIENT, "auto")
            # Idempotent: a second retry does not splice anything else out.
            before = list(worker._cmd)
            worker._drop_client_if_format_error()
            self.assertEqual(worker._cmd, before)

    def test_worker_keeps_client_for_other_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worker = self._worker(tmp)
            worker._cmd = worker._build_command()
            worker._record_recent(
                "ERROR: unable to download video data: HTTP Error 403"
            )
            worker._drop_client_if_format_error()
            self.assertIn("--extractor-args", worker._cmd)

    def test_item_option_reaches_worker_command(self) -> None:
        from ytget_gui.queue.controller import QueueController

        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)
            settings.YOUTUBE_PLAYER_CLIENT = "android"
            model = QueueModel()
            item = make_item()
            item.options["DROP_PLAYER_CLIENT"] = True
            model.add(item)
            controller = QueueController(model, settings)
            worker = controller._build_worker(item)
            cmd = worker._build_command()
            self.assertNotIn("--extractor-args", cmd)
            self.assertEqual(worker._applied_client_flags, [])

            # Without the option the pin is applied as usual.
            plain = make_item()
            model.add(plain)
            worker_plain = controller._build_worker(plain)
            cmd_plain = worker_plain._build_command()
            self.assertIn("--extractor-args", cmd_plain)
            self.assertTrue(
                any("player_client=android" in tok for tok in cmd_plain)
            )

    def test_controller_marks_item_on_format_failure(self) -> None:
        from ytget_gui.queue.controller import QueueController

        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)
            settings.YOUTUBE_PLAYER_CLIENT = "android"
            model = QueueModel()
            item = make_item()
            model.add(item)
            controller = QueueController(model, settings)
            controller._skip_requested = False
            controller._stop_requested = False
            item.last_error = FORMAT_ERROR
            controller._apply_outcome(item, 1)
            self.assertTrue(item.options.get("DROP_PLAYER_CLIENT"))

    def test_controller_leaves_auto_settings_alone(self) -> None:
        from ytget_gui.queue.controller import QueueController

        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)  # player client is "auto"
            model = QueueModel()
            item = make_item()
            model.add(item)
            controller = QueueController(model, settings)
            controller._skip_requested = False
            controller._stop_requested = False
            item.last_error = FORMAT_ERROR
            controller._apply_outcome(item, 1)
            self.assertNotIn("DROP_PLAYER_CLIENT", item.options)

    def test_option_roundtrips_through_the_queue_file(self) -> None:
        item = make_item()
        item.options["DROP_PLAYER_CLIENT"] = True
        restored = QueueItem.from_dict(item.to_dict())
        self.assertTrue(restored.options.get("DROP_PLAYER_CLIENT"))
        hostile = item.to_dict()
        hostile["options"] = {"DROP_PLAYER_CLIENT": True, "EVIL": "yes"}
        self.assertEqual(
            QueueItem.from_dict(hostile).options, {"DROP_PLAYER_CLIENT": True}
        )


# ----------------------------------------------------------------------
# 5. Player-client choice list
# ----------------------------------------------------------------------


class PlayerClientListTests(unittest.TestCase):
    def test_retired_clients_are_gone_and_current_default_offered(self) -> None:
        values = set(YOUTUBE_PLAYER_CLIENTS.values())
        self.assertNotIn("android", values)
        self.assertNotIn("ios", values)
        self.assertIn("auto", values)
        self.assertIn("tv_samsung", values)

    def test_stale_selection_is_normalised_to_auto(self) -> None:
        normalise = _VALIDATORS["YOUTUBE_PLAYER_CLIENT"]
        self.assertEqual(normalise("android"), "auto")
        self.assertEqual(normalise("ios"), "auto")
        self.assertEqual(normalise("tv_samsung"), "tv_samsung")
        self.assertEqual(normalise("auto"), "auto")


# ----------------------------------------------------------------------
# 6. Challenge-solver crash (yt-dlp #18123, fixed in 2026.11.23)
# ----------------------------------------------------------------------

# Condensed from a real 2.8.5 failure log: the EJS solver crashes on the
# player JS, the format URLs are then missing, and only images remain.
SOLVER_CRASH = (
    "WARNING: [youtube] [jsc] Error solving n challenge request using "
    "\"deno\" provider: Error running deno process (returncode: 1): "
    "error: Uncaught (in promise) TypeError: a.addOnDisposeCallback "
    "is not a function\n"
    "WARNING: [youtube] jixHjqDwjAs: n challenge solving failed: "
    "Some formats may be missing.\n"
    "WARNING: [youtube] jixHjqDwjAs: Some web_embedded client https "
    "formats have been skipped as they are missing a URL.\n"
    "WARNING: Only images are available for download. use --list-formats "
    "to see them\n"
    "ERROR: [youtube] jixHjqDwjAs: Requested format is not available. "
    "Use --list-formats for a list of available formats"
)


class ChallengeSolverFailureTests(unittest.TestCase):
    def test_detector_matches_the_real_failure(self) -> None:
        self.assertTrue(is_challenge_solver_failure(SOLVER_CRASH))
        # Our replacement message is recognised from last_error alone.
        self.assertTrue(is_challenge_solver_failure(CHALLENGE_SOLVER_FIX_MESSAGE))

    def test_solver_warning_alone_is_not_a_failure(self) -> None:
        # A crash that leaves other formats usable is only a warning.
        self.assertFalse(is_challenge_solver_failure(
            "WARNING: [youtube] x: n challenge solving failed: "
            "Some formats may be missing."
        ))
        self.assertFalse(is_challenge_solver_failure(
            "ERROR: Uncaught (in promise) TypeError: "
            "a.addOnDisposeCallback is not a function"
        ))

    def test_formats_lost_alone_is_not_a_solver_failure(self) -> None:
        # The pinned-client path (section 4) owns the plain wording.
        self.assertFalse(is_challenge_solver_failure(FORMAT_ERROR))
        self.assertFalse(is_challenge_solver_failure(""))
        self.assertFalse(is_challenge_solver_failure(
            "HTTP Error 429: Too Many Requests"
        ))

    def test_worker_does_not_retry_a_solver_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worker = DownloadWorker(
                {"url": URL, "format_code": chain_1080()}, make_settings(tmp)
            )
            worker._record_recent(SOLVER_CRASH + "\n")
            self.assertFalse(worker._should_retry())

            # A plain format error (pinned client) stays retryable.
            plain = DownloadWorker(
                {"url": URL, "format_code": chain_1080()}, make_settings(tmp)
            )
            plain._record_recent(FORMAT_ERROR + "\n")
            self.assertTrue(plain._should_retry())

    def test_controller_fails_the_item_without_requeue(self) -> None:
        from ytget_gui.queue.controller import QueueController

        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)
            model = QueueModel()
            item = make_item()
            model.add(item)
            controller = QueueController(model, settings)
            controller._skip_requested = False
            controller._stop_requested = False
            item.last_error = SOLVER_CRASH
            controller._apply_outcome(item, 1)
            # Not requeued as PENDING and no retry counter burned.
            self.assertIs(item.status, Status.ERROR)
            self.assertEqual(item.queue_attempts, 0)
            # The item stays in the queue for a manual retry after the
            # yt-dlp update.
            self.assertIn(item, list(model))


if __name__ == "__main__":
    unittest.main()
