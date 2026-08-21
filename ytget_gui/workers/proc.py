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
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


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
        os.killpg(pgid, signal.SIGTERM)
        try:
            proc.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
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
        if value:
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
