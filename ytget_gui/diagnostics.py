"""Offline dependency checks. No secrets, configuration dumps, or network calls."""
from __future__ import annotations
import importlib.util
import importlib.metadata
import platform
import sys
import tempfile
from pathlib import Path
from ytget_gui._version import __version__


def main() -> int:
    print(f"YTGet {__version__} · Python {platform.python_version()} · {platform.system()} {platform.machine()}")
    failed = False
    for module, distribution in [("PySide6", "PySide6"), ("yt_dlp", "yt-dlp"),
                                  ("requests", "requests"), ("mutagen", "mutagen"),
                                  ("PIL", "Pillow"), ("packaging", "packaging")]:
        found = importlib.util.find_spec(module) is not None
        try:
            version = importlib.metadata.version(distribution) if found else "MISSING"
        except importlib.metadata.PackageNotFoundError:
            version = "present"
        print(f"{'OK  ' if found else 'FAIL'} {distribution}: {version}")
        failed |= not found
    from ytget_gui.settings import AppSettings
    from ytget_gui.workers import proc
    settings = AppSettings()
    for name, target in [("Profile", settings.DATA_DIR), ("Downloads", settings.DOWNLOADS_DIR)]:
        try:
            target.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=target):
                pass
            print(f"OK   {name} folder is writable: {target}")
        except OSError as exc:
            failed = True
            print(f"FAIL {name} folder: {exc}")
    for name, path, required in [("yt-dlp", settings.YT_DLP_PATH, True),
                                 ("FFmpeg", settings.FFMPEG_PATH, True),
                                 ("FFprobe", settings.FFPROBE_PATH, True),
                                 ("Deno", settings.DENO_PATH, False)]:
        ok = Path(path).is_file()
        detail = "not found"
        if ok:
            try:
                flag = "-version" if name in ("FFmpeg", "FFprobe") else "--version"
                result = proc.run([str(path), flag], timeout=10)
                ok = result.returncode == 0
                detail = (result.stdout or result.stderr).splitlines()[0][:180]
            except Exception as exc:
                ok, detail = False, str(exc)
        print(f"{'OK  ' if ok else ('FAIL' if required else 'WARN')} {name}: {detail}")
        failed |= required and not ok
    for module, label in [("spotdl", "Spotify support"), ("browser_cookie3", "Cookie export")]:
        found = importlib.util.find_spec(module) is not None
        print(f"{'OK  ' if found else 'INFO'} {label}: {'installed' if found else 'optional extra not installed'}")
    print("Network access, desktop rendering, and real-site downloads are not tested by this check.")
    print("See START_HERE.md for setup and TROUBLESHOOTING.md for fixes.")
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
