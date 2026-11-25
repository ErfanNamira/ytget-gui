# File: ytget_gui/workers/proc.py
"""Subprocess helpers shared by every worker.

Each worker previously reimplemented hidden-console launching and process
termination. The copies drifted: `_detect_flat_playlist` and
`_convert_avif_to_jpg` flashed a console window on Windows because they
called `subprocess.run` with no startupinfo, and `spotdl_worker.cancel()`
only terminated spotdl itself, orphaning the yt-dlp/ffmpeg children it had
spawned. Centralising both fixes all callers at once.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# yt-dlp 2026.10.26+ rejects Deno below 2.3.0 as a JS challenge runtime and
# then silently falls back to YouTube's JS-less clients, which can expose no
# downloadable formats at all ("Requested format is not available"). Deno is
# only pinned/forwarded when it clears this floor.
DENO_MIN_VERSION = (2, 3, 0)
_DENO_VERSION_RE = re.compile(r"deno\s+(\d+)\.(\d+)\.(\d+)")


@lru_cache(maxsize=8)
def _deno_version_cached(
    path_str: str, mtime_ns: int, size: int
) -> Optional[Tuple[int, int, int]]:
    """Probe `deno --version` once per binary state.

    Keyed on mtime/size so an in-session update (the binary is replaced by
    the update manager) re-probes instead of serving a stale verdict.
    """
    try:
        result = run([path_str, "--version"], timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    match = _DENO_VERSION_RE.search(result.stdout or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def deno_version(settings) -> Optional[Tuple[int, int, int]]:
    """Version tuple of the configured Deno, or None when unprovable.

    Callers treat None as "keep the old behaviour": a missing probe must not
    strip a working runtime, only a proven-too-old one.
    """
    raw = getattr(settings, "DENO_PATH", None)
    if not raw:
        return None
    try:
        path = Path(raw)
        if not path.is_file():
            return None
        stat = path.stat()
        return _deno_version_cached(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def deno_supported_for_ytdlp(settings) -> bool:
    """True when Deno should be pinned for yt-dlp's JS challenges."""
    version = deno_version(settings)
    # Unknown version: assume fine rather than silently dropping the runtime.
    return version is None or version >= DENO_MIN_VERSION


def hidden_console_kwargs() -> Dict[str, Any]:
    """Popen kwargs that suppress a console window on Windows."""
    if not IS_WINDOWS:
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def spawn(
    cmd: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[Path] = None,
    merge_stderr: bool = True,
    capture: bool = True,
    own_process_group: bool = True,
) -> subprocess.Popen:
    """Launch a child process configured for cancellable, quiet operation.

    `own_process_group` puts the child in its own POSIX session so the whole
    tree (yt-dlp plus the ffmpeg/aria2c it spawns) can be signalled together.
    Without it, terminate() reaches only the direct child and the grandchildren
    keep writing to disk after a cancel.
    """
    kwargs: Dict[str, Any] = dict(hidden_console_kwargs())
    kwargs["stdin"] = subprocess.DEVNULL

    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT if merge_stderr else subprocess.PIPE
        # Unbuffered so progress lines surface immediately rather than in
        # 8 KiB blocks.
        kwargs["bufsize"] = 0

    if env is not None:
        kwargs["env"] = dict(env)
    if cwd is not None:
        kwargs["cwd"] = str(cwd)
    if own_process_group and not IS_WINDOWS:
        kwargs["start_new_session"] = True

    return subprocess.Popen(list(cmd), **kwargs)


def run(
    cmd: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    timeout: float = 30.0,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Blocking helper for short auxiliary commands (--version probes, etc.).

    Always decodes with errors="replace": a `text=True` run raises
    UnicodeDecodeError on Windows consoles using a non-UTF-8 code page, which
    previously turned a harmless version probe into an exception.
    """
    completed = subprocess.run(
        list(cmd),
        capture_output=True,
        timeout=timeout,
        env=dict(env) if env is not None else None,
        check=check,
        **hidden_console_kwargs(),
    )
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        _decode(completed.stdout),
        _decode(completed.stderr),
    )


def _decode(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace")


def terminate_tree(proc: Optional[subprocess.Popen], *, grace: float = 2.0) -> None:
    """Stop a process and every descendant it created.

    Windows: `taskkill /T` walks the tree; TerminateProcess does not.
    POSIX: signal the process group created by spawn(own_process_group=True),
    escalating SIGTERM -> SIGKILL after `grace` seconds.
    """
    if proc is None or proc.poll() is not None:
        return

    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
                **hidden_console_kwargs(),
            )
            _reap(proc, grace)
            return

        pgid = os.getpgid(proc.pid)
        if pgid != proc.pid:
            proc.terminate()
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                proc.kill()
                _reap(proc, grace)
            return
        os.killpg(pgid, signal.SIGTERM)
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        _reap(proc, grace)
        return
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log.debug("Tree kill failed (%s); falling back to direct kill", exc)

    # Fallback: the process may already be gone, or we may lack permission to
    # signal the group (rare, but possible under some sandboxes).
    try:
        proc.terminate()
        _reap(proc, grace)
    except OSError:
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _reap(proc: subprocess.Popen, grace: float) -> None:
    """Wait briefly so the child does not linger as a zombie."""
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        pass


def prepend_path(env: Dict[str, str], directories: Iterable[Any]) -> Dict[str, str]:
    """Prepend directories to PATH, preserving order and skipping duplicates."""
    current = env.get("PATH", "")
    existing = [p for p in current.split(os.pathsep) if p]
    seen = set(existing)

    prefix: list[str] = []
    for directory in directories:
        if not directory:
            continue
        text = str(directory)
        if text in seen:
            continue
        prefix.append(text)
        seen.add(text)

    if prefix:
        env["PATH"] = os.pathsep.join(prefix + existing)

    # A frozen build can inherit an environment with no PATHEXT, which makes
    # Windows unable to resolve "yt-dlp" to "yt-dlp.exe" via PATH lookup.
    if IS_WINDOWS and not env.get("PATHEXT"):
        env["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"

    return env


def tool_env(settings, *, extra_dirs: Iterable[Any] = ()) -> Dict[str, str]:
    """Environment for yt-dlp/spotdl/ffmpeg: PATH augmented, SSL trust applied."""
    from ytget_gui.workers import ssl_utils

    env = os.environ.copy()

    directories: list[Any] = [
        getattr(settings, "INTERNAL_DIR", None),
        getattr(settings, "BASE_DIR", None),
    ]

    for attr in ("DENO_PATH", "FFMPEG_PATH"):
        value = getattr(settings, attr, None)
        if not value:
            continue
        if attr == "DENO_PATH" and not deno_supported_for_ytdlp(settings):
            # Keep a too-old Deno off PATH so yt-dlp's own runtime discovery
            # can find a usable one (a newer system Deno, Node >= 22, ...)
            # instead of latching onto ours and degrading YouTube extraction.
            continue
        try:
            path = Path(value)
            if path.is_file():
                directories.append(path.parent)
        except OSError:
            pass

    # PhantomJS is only added when explicitly requested: it is legacy, and
    # putting it on PATH unconditionally lets yt-dlp pick it over Deno.
    if getattr(settings, "USE_PHANTOMJS", False):
        phantom = getattr(settings, "PHANTOMJS_PATH", None)
        if phantom:
            try:
                path = Path(phantom)
                if path.is_file():
                    directories.append(path.parent)
            except OSError:
                pass

    directories.extend(extra_dirs)
    prepend_path(env, directories)

    try:
        _verify, _args, ssl_env = ssl_utils.resolve_ssl_config(settings)
        env.update(ssl_env)
    except Exception as exc:  # noqa: BLE001 - env building must never be fatal
        log.debug("SSL env resolution failed: %s", exc)

    return env
