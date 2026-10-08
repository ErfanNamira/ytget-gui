# File: ytget_gui/filename_rules.py
"""Filename templates, chosen per source site and per recording type.

Until 2.8.2 one "Filename format" setting applied to every download, so a
user who wanted "Artist - Track# Title" for music and "Uploader - Title" for
videos had to switch the template every time the recording type changed.

A rule now exists for each (source, media) pair:

    youtube_video   youtube_audio
    ytmusic_video   ytmusic_audio
    other_video     other_audio

Every rule defaults to "global", which means "use the general Filename
format", so an existing configuration behaves exactly as before until the
user opts in. A rule can otherwise pick the smart default, any preset, or its
own custom template.

This module is deliberately Qt-free so the worker, the settings loader, the
preferences dialog and the tests all share one implementation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ytget_gui.sites import site_key_for

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

FILENAME_FORMAT_PRESETS: Dict[str, str] = {
    "title_only": "%(title)s",
    "artist_title": "%(artist)s - %(title)s",
    "title_artist": "%(title)s - %(artist)s",
    "artist_album_title": "%(artist)s - %(album)s - %(title)s",
    # The layout requested on GitHub for music: "artist - track# title".
    # Alternatives keep it useful outside YouTube Music: the uploader stands
    # in for a missing artist and the playlist position for a missing track.
    "artist_track_title": "%(artist,uploader)s - %(track_number,playlist_index)s %(title)s",
    "track_title": "%(track_number)s - %(title)s",
    "album_track_title": "%(album)s - %(track_number)s - %(title)s",
    "playlist_index_title": "%(playlist_index)s - %(title)s",
    "uploader_title": "%(uploader)s - %(title)s",
    "channel_title": "%(channel)s - %(title)s",
    "date_title": "%(upload_date)s - %(title)s",
    "id_title": "%(id)s - %(title)s",
}

# (label, stored value) in display order. "default" is the smart per-type
# naming the app has always used; "custom" reads the matching template field.
FILENAME_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Default", "default"),
    ("Title only", "title_only"),
    ("Artist - Title", "artist_title"),
    ("Title - Artist", "title_artist"),
    ("Artist - Album - Title", "artist_album_title"),
    ("Artist - Track # Title", "artist_track_title"),
    ("Track # - Title", "track_title"),
    ("Album - Track # - Title", "album_track_title"),
    ("Playlist # - Title", "playlist_index_title"),
    ("Uploader - Title", "uploader_title"),
    ("Channel - Title", "channel_title"),
    ("Upload Date - Title", "date_title"),
    ("Video/Track ID - Title", "id_title"),
    ("Custom template\u2026", "custom"),
)

GLOBAL_CHOICE = "global"
RULE_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Use general setting", GLOBAL_CHOICE),
) + FILENAME_CHOICES

_GLOBAL_VALUES = frozenset(value for _label, value in FILENAME_CHOICES)
_RULE_VALUES = frozenset(value for _label, value in RULE_CHOICES)

assert all(
    value in ("default", "custom") or value in FILENAME_FORMAT_PRESETS
    for _label, value in FILENAME_CHOICES
), "FILENAME_CHOICES references a preset that does not exist"

# ---------------------------------------------------------------------------
# Rule slots
# ---------------------------------------------------------------------------

SOURCES: Tuple[Tuple[str, str], ...] = (
    ("youtube", "YouTube"),
    ("ytmusic", "YouTube Music"),
    ("other", "Other sites"),
)
MEDIA: Tuple[Tuple[str, str], ...] = (
    ("video", "Video"),
    ("audio", "Audio"),
)
RULE_KEYS: Tuple[str, ...] = tuple(
    f"{source}_{media}" for source, _ in SOURCES for media, _ in MEDIA
)


def default_rules() -> Dict[str, Dict[str, str]]:
    return {key: {"format": GLOBAL_CHOICE, "custom": ""} for key in RULE_KEYS}


def normalise_global_choice(value: Any) -> str:
    text = str(value or "")
    return text if text in _GLOBAL_VALUES else "default"


def normalise_rules(raw: Any) -> Dict[str, Dict[str, str]]:
    """Sanitise a stored rule table.

    Unknown slots are dropped, missing ones are added as "global", and a
    stale or hand-edited choice falls back to "global" -- never to a value
    that could change how an existing user's files are named.
    """
    rules = default_rules()
    if not isinstance(raw, Mapping):
        return rules
    for key in RULE_KEYS:
        entry = raw.get(key)
        if isinstance(entry, str):
            entry = {"format": entry}
        if not isinstance(entry, Mapping):
            continue
        choice = str(entry.get("format") or GLOBAL_CHOICE)
        custom = str(entry.get("custom") or "").strip()[:MAX_TEMPLATE_LENGTH]
        rules[key] = {
            "format": choice if choice in _RULE_VALUES else GLOBAL_CHOICE,
            "custom": custom,
        }
    return rules


def has_overrides(rules: Any) -> bool:
    return any(
        entry.get("format") != GLOBAL_CHOICE
        for entry in normalise_rules(rules).values()
    )


def source_for(url: str) -> str:
    """"youtube", "ytmusic" or "other" for a URL."""
    key = site_key_for(url)
    return key if key in ("youtube", "ytmusic") else "other"


def rule_key(url: str, is_audio: bool) -> str:
    return f"{source_for(url)}_{'audio' if is_audio else 'video'}"


def effective_choice(settings: Any, url: str, is_audio: bool) -> Tuple[str, str]:
    """(choice, custom template) that applies to one download."""
    rules = getattr(settings, "FILENAME_RULES", None)
    entry = None
    if isinstance(rules, Mapping):
        entry = rules.get(rule_key(url, is_audio))
    choice = str((entry or {}).get("format") or GLOBAL_CHOICE)
    if choice == GLOBAL_CHOICE or choice not in _RULE_VALUES:
        choice = normalise_global_choice(getattr(settings, "FILENAME_FORMAT", "default"))
        custom = str(getattr(settings, "CUSTOM_FILENAME_TEMPLATE", "") or "")
    else:
        custom = str((entry or {}).get("custom") or "")
    custom = custom.strip()
    if choice == "custom" and not custom:
        # An empty custom field is treated as "not configured" rather than
        # producing a file literally named ".mkv".
        choice = "default"
    return choice, custom


def resolve_template(
    settings: Any, url: str, is_audio: bool, default_template: str
) -> Tuple[str, str]:
    """(filename stub, effective choice) for one download."""
    choice, custom = effective_choice(settings, url, is_audio)
    if choice == "default":
        return default_template, choice
    if choice == "custom":
        return custom, choice
    return FILENAME_FORMAT_PRESETS.get(choice, default_template), choice


def describe(choice: str, custom: str = "") -> str:
    if choice == "custom":
        return custom or "(empty)"
    for label, value in RULE_CHOICES:
        if value == choice:
            return label
    return choice


# ---------------------------------------------------------------------------
# Template validation (shared by the dialog and the tests)
# ---------------------------------------------------------------------------

MAX_TEMPLATE_LENGTH = 180

ALLOWED_TEMPLATE_FIELDS = frozenset(
    {
        "title", "artist", "creator", "uploader", "uploader_id", "channel",
        "channel_id", "album", "album_artist", "track", "track_number",
        "track_id", "disc_number", "genre", "release_year", "release_date",
        "upload_date", "playlist_title", "playlist_index", "playlist_id", "id",
        "ext", "duration", "duration_string", "view_count", "like_count",
        "repost_count", "comment_count", "resolution", "height", "width", "fps",
        "vcodec", "acodec", "format_id", "extractor", "extractor_key",
        "language", "season_number", "episode_number", "autonumber", "abr",
        "vbr", "tbr", "epoch",
    }
)

# One %(field[,alt][|default])s / d / f placeholder.
_PLACEHOLDER_RE = re.compile(
    r"%\((?P<fields>[a-zA-Z_][a-zA-Z0-9_]*(?:,[a-zA-Z_][a-zA-Z0-9_]*)*)"
    r"(?:\|[^)%]*)?\)(?P<conv>[-+ #0]*\d*(?:\.\d+)?[sdf])"
)
# Illegal outside a placeholder: this is a filename stub, not a path.
_ILLEGAL_LITERAL_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_TRACK_FIELD_RE = re.compile(r"%\((?:[^)]*,)?track_number[,)|]")


def validate_template(text: str) -> Tuple[bool, str]:
    raw = str(text or "").strip()
    if not raw:
        return False, "Enter a template, e.g. %(title)s"
    if len(raw) > MAX_TEMPLATE_LENGTH:
        return False, f"Template is too long ({MAX_TEMPLATE_LENGTH} characters maximum)"
    if raw != raw.strip(" ."):
        return False, "Cannot start or end with a space or a period"

    # Mask escaped percent signs so they cannot be mistaken for a malformed
    # placeholder.
    working = raw.replace("%%", "\u0000")

    found = False
    literals: List[str] = []
    position = 0
    for match in _PLACEHOLDER_RE.finditer(working):
        found = True
        literals.append(working[position:match.start()])
        for field in match.group("fields").split(","):
            if field not in ALLOWED_TEMPLATE_FIELDS:
                return False, f"Unknown field: %({field})s"
        position = match.end()
    literals.append(working[position:])

    remainder = "".join(literals)
    if "%" in remainder:
        return False, "Malformed placeholder \u2014 use %(field)s"
    if _ILLEGAL_LITERAL_RE.search(remainder.replace("\u0000", "%")):
        return False, "Cannot contain \\ / : * ? \" < > | or control characters"
    if not found:
        return False, "Include at least one field, e.g. %(title)s"
    return True, ""


def uses_track_number(template: Optional[str]) -> bool:
    """True when a template references %(track_number)s, alone or as one of
    several alternatives."""
    return bool(template) and bool(_TRACK_FIELD_RE.search(str(template)))
