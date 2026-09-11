"""Argument parsing for direct subprocess lists; never invokes a shell."""
from __future__ import annotations
import shlex
import sys

# These can execute code, add hidden targets, or break the queue protocol.
# Ordinary output/format/network options remain available to advanced users.
BLOCKED = frozenset({
    "--exec", "--exec-before-download", "--config-locations", "--config-location",
    "--plugin-dirs", "--plugin-dir", "--batch-file", "-a", "--load-info-json",
    "--update", "-U", "--update-to", "--rm-cache-dir", "--print-to-file",
    "--simulate", "-s", "--skip-download", "--no-download", "--print", "-O",
    "--dump-json", "-j", "--dump-single-json", "-J", "--get-url", "-g",
    "--get-title", "--get-filename", "--get-format", "--get-id", "--get-thumbnail",
    "--get-description", "--get-duration", "--progress-template", "--no-progress",
    "--no-newline", "--quiet", "-q", "--help", "-h", "--version",
    "--list-formats", "-F", "--list-subs", "--list-thumbnails", "--list-extractors",
})

def split_arguments(raw: str, *, windows: bool | None = None) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if "\0" in text or "\n" in text or "\r" in text:
        raise ValueError("Extra arguments must be a single line without control characters.")
    parser = shlex.shlex(text, posix=True)
    parser.whitespace_split = True
    parser.commenters = ""
    if windows if windows is not None else sys.platform == "win32":
        parser.escape = ""
    try:
        return list(parser)
    except ValueError as exc:
        raise ValueError("Unclosed quote in extra arguments. Quote paths containing spaces.") from exc

def parse_ytdlp_args(raw: str) -> list[str]:
    args = split_arguments(raw)
    for token in args:
        key = token.split("=", 1)[0]
        # Block abbreviations too: yt-dlp's optparse accepts unique prefixes.
        forbidden = key in BLOCKED or (key.startswith("--") and any(v.startswith(key) for v in BLOCKED))
        # Protect attached/clustered short aliases (-aFILE, -qj, etc.).
        if token.startswith("-") and not token.startswith("--") and len(token) > 1:
            forbidden = forbidden or any(("-" + ch) in BLOCKED for ch in token[1:])
        if forbidden or token == "--":
            raise ValueError(f"{key} is not supported in GUI extra arguments; it changes execution or queue reporting.")
    return args
