# File: ytget_gui/utils/paths.py

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, os.PathLike, Path]


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) bundle."""
    return bool(getattr(sys, "frozen", False))


def get_base_path() -> Path:
    """Directory the app treats as its own root (config, cookies, binaries).

    For a frozen build this must be the directory containing the executable,
    NOT sys._MEIPASS. _MEIPASS is a temporary extraction directory that is
    deleted on exit -- writing config.json/cookies.txt/queue.json there means
    every setting silently evaporates when the app closes. The previous
    implementation preferred _MEIPASS, so packaged builds could not persist
    anything.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bundle_path() -> Path:
    """Read-only directory holding bundled resources (icons, etc.).

    This *is* _MEIPASS under PyInstaller. Use it for reading assets only.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return get_base_path()


def get_data_path() -> Path:
    """Per-user state. YTGET_DATA_DIR explicitly enables a portable profile."""
    override = os.environ.get("YTGET_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if is_windows():
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        return root / "YTGet"
    if is_macos():
        return Path.home() / "Library/Application Support/YTGet"
    root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    if not root.is_absolute():
        root = Path.home() / ".local/share"
    return root / "ytget"


def executable_name(base: str) -> str:
    """Append `.exe` on Windows, leave unchanged elsewhere."""
    return f"{base}.exe" if is_windows() else base


def which_or_path(candidate: PathLike, exe_name: str) -> Path:
    """Resolve an executable: explicit candidate, then PATH, then candidate.

    The final fallback deliberately returns a non-existent path so callers can
    surface a clear "not found at <path>" error rather than a bare None.
    """
    cand = Path(candidate)
    if cand.is_file():
        return cand

    found = shutil.which(exe_name)
    if found:
        return Path(found)

    return cand


def resolve_tool(
    env_var: str,
    bundled: Path,
    exe_name: str,
) -> Path:
    """Resolve a helper binary via env override -> PATH -> bundled candidate."""
    override = os.getenv(env_var)
    if override:
        p = Path(override).expanduser()
        if p.is_file():
            return p
    return which_or_path(bundled, exe_name)


def default_downloads_dir() -> Path:
    """Always use user-writable storage, even before Downloads exists."""
    return Path.home() / "Downloads"


def is_usable_file(path: Optional[PathLike]) -> bool:
    """True only for an existing, non-empty regular file.

    Guards against the `Path("")` -> `Path(".")` trap: an empty settings field
    used to serialise to "." which `.exists()` reports True for and whose
    `st_size` is nonzero, so cleared cookie/archive fields produced
    `--cookies .` and `--download-archive .` on every yt-dlp invocation.
    """
    if not path:
        return False
    try:
        p = Path(path)
        if str(p) in ("", "."):
            return False
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def is_writable_dir(path: Optional[PathLike]) -> bool:
    if not path:
        return False
    try:
        p = Path(path)
        return p.is_dir() and os.access(p, os.W_OK)
    except OSError:
        return False


def ensure_dir(path: PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_stem(name: str, max_len: int = 180) -> str:
    """Sanitise a string for use as a filename stem (no path separators)."""
    import re

    if not name:
        return "Unknown"
    name = "".join(ch for ch in name if ord(ch) >= 32)
    name = re.sub(r'[\\/:*?"<>|]', " ", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(" .")

    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if name.split(".", 1)[0].upper() in reserved:
        name += "_"

    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")

    return name or "Unknown"


def platform_label() -> str:
    return f"{platform.system()} {platform.release()}"
