"""Offline HTTP/HLS + Opus -> MKV smoke test using the actual worker command.

Requires yt-dlp, ffmpeg (libx264/libopus), and ffprobe on PATH. No YouTube
access or cookies are required. Generated media is confined to a temp folder.
"""
from __future__ import annotations

import functools
import http.server
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from ytget_gui.settings import AppSettings
from ytget_gui.workers.download_worker import DownloadWorker


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


@unittest.skipUnless(all(shutil.which(t) for t in ("yt-dlp", "ffmpeg", "ffprobe")),
                     "yt-dlp, ffmpeg and ffprobe required")
class LocalMediaIntegrationTests(unittest.TestCase):
    def test_hls_video_and_opus_merge_keeps_real_1080p_video_audio_and_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "media"
            media.mkdir()
            ffmpeg = shutil.which("ffmpeg")

            def generate(*args):
                subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args],
                               cwd=media, check=True, capture_output=True, timeout=60)

            generate("-f", "lavfi", "-i", "color=c=blue:s=1920x1080:r=25:d=1",
                     "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                     "-f", "hls", "-hls_time", "0.5", "-hls_list_size", "0", "270.m3u8")
            generate("-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                     "-c:a", "libopus", "251.webm")
            from PIL import Image
            Image.new("RGB", (128, 72), "red").save(media / "cover.jpg")

            handler = functools.partial(_QuietHandler, directory=str(media))
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                fixture = dict(id="local1080", title="Local HLS quality test", uploader="YTGet tests",
                               webpage_url=f"{base}/watch", extractor="generic", extractor_key="Generic",
                               thumbnail=f"{base}/cover.jpg", duration=1,
                               formats=[
                                   dict(format_id="243", url=f"{base}/missing360.webm", ext="webm",
                                        height=360, width=640, fps=25, vcodec="vp9", acodec="none",
                                        vbr=282, tbr=282),
                                   dict(format_id="137", url=f"{base}/missing137.mp4", ext="mp4",
                                        height=1080, width=1920, fps=25, vcodec="avc1.640028",
                                        acodec="none", vbr=3395, tbr=3395),
                                   dict(format_id="270", url=f"{base}/270.m3u8", ext="mp4",
                                        height=1080, width=1920, fps=25, vcodec="avc1.640028",
                                        acodec="none", vbr=5152, tbr=5152, protocol="m3u8_native"),
                                   dict(format_id="251", url=f"{base}/251.webm", ext="webm",
                                        vcodec="none", acodec="opus", abr=110, tbr=110)])
                info_path = root / "fixture.json"
                info_path.write_text(json.dumps(fixture), encoding="utf-8")
                settings = AppSettings(DATA_DIR=root / "profile", DOWNLOADS_DIR=root / "output")
                settings.EXTRA_YTDLP_ARGS = ""
                settings.YT_DLP_PATH = Path(shutil.which("yt-dlp"))
                settings.FFMPEG_PATH = Path(ffmpeg)
                worker = DownloadWorker({"url": f"{base}/watch", "format_code": "1080p"}, settings)
                # Replace only the online extractor input with a local info
                # document. Every real selection/postprocessing flag remains.
                cmd = worker._build_command()[:-2] + ["--load-info-json", str(info_path)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("270+251", result.stdout)
                files = list(settings.DOWNLOADS_DIR.glob("*.mkv"))
                self.assertEqual(len(files), 1, result.stdout + result.stderr)
                probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_streams",
                                        "-show_format", "-of", "json", str(files[0])],
                                       check=True, capture_output=True, text=True, timeout=10)
                data = json.loads(probe.stdout)
                streams = data["streams"]
                self.assertTrue(any(s.get("codec_type") == "video" and s.get("height") == 1080
                                    and s.get("codec_name") == "h264" for s in streams))
                self.assertTrue(any(s.get("codec_type") == "audio" and s.get("codec_name") == "opus"
                                    for s in streams))
                self.assertTrue(any(s.get("tags", {}).get("filename", "").endswith(".png")
                                    for s in streams), streams)
                self.assertGreater(float(data["format"]["duration"]), 0.5)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
