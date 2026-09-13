# File: ytget_gui/sites.py
"""The watcher's site list.

yt-dlp supports well over a thousand extractors, so this is deliberately a
curation rather than an attempt at completeness: the watcher only needs a
user-facing allowlist for "other" links, and a thousand checkboxes would be
unusable. Anything missing is still handled by the Unlisted sites policy,
so a site absent from here can still be captured.
"""

from __future__ import annotations

from typing import Dict, Sequence, Tuple
from urllib.parse import urlsplit

# (key, label, domains). `key` is what is persisted, so labels can be
# reworded and the list can grow without invalidating a saved
# configuration.
SITES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("youtube", "YouTube", ("youtube.com", "youtu.be", "youtube-nocookie.com")),
    ("ytmusic", "YouTube Music", ("music.youtube.com",)),
    ("spotify", "Spotify", ("spotify.com",)),
    ("soundcloud", "SoundCloud", ("soundcloud.com", "snd.sc")),
    ("bandcamp", "Bandcamp", ("bandcamp.com",)),
    ("mixcloud", "Mixcloud", ("mixcloud.com",)),
    ("audiomack", "Audiomack", ("audiomack.com",)),
    ("vimeo", "Vimeo", ("vimeo.com",)),
    ("dailymotion", "Dailymotion", ("dailymotion.com", "dai.ly")),
    ("twitch", "Twitch", ("twitch.tv", "clips.twitch.tv")),
    ("tiktok", "TikTok", ("tiktok.com", "vm.tiktok.com")),
    ("instagram", "Instagram", ("instagram.com", "instagr.am")),
    ("facebook", "Facebook", ("facebook.com", "fb.watch", "fb.com")),
    ("twitter", "X / Twitter", ("twitter.com", "x.com", "t.co")),
    ("reddit", "Reddit", ("reddit.com", "redd.it")),
    ("bilibili", "Bilibili", ("bilibili.com", "b23.tv")),
    ("niconico", "Niconico", ("nicovideo.jp", "nico.ms")),
    ("odysee", "Odysee", ("odysee.com", "lbry.tv")),
    ("rumble", "Rumble", ("rumble.com",)),
    ("kick", "Kick", ("kick.com",)),
    ("vk", "VK", ("vk.com", "vkvideo.ru")),
    ("ok", "OK.ru", ("ok.ru", "odnoklassniki.ru")),
    ("streamable", "Streamable", ("streamable.com",)),
    ("imgur", "Imgur", ("imgur.com",)),
    ("tumblr", "Tumblr", ("tumblr.com",)),
    ("pinterest", "Pinterest", ("pinterest.com", "pin.it")),
    ("linkedin", "LinkedIn", ("linkedin.com",)),
    ("ted", "TED", ("ted.com",)),
    ("bbc", "BBC iPlayer", ("bbc.co.uk", "bbc.com")),
    ("arte", "ARTE", ("arte.tv",)),
    ("pbs", "PBS", ("pbs.org",)),
    ("nytimes", "NY Times", ("nytimes.com",)),
    ("coub", "Coub", ("coub.com",)),
    ("newgrounds", "Newgrounds", ("newgrounds.com",)),
    ("loom", "Loom", ("loom.com",)),
    ("douyin", "Douyin", ("douyin.com", "iesdouyin.com")),
    ("weibo", "Weibo", ("weibo.com", "weibo.cn")),
    ("rutube", "Rutube", ("rutube.ru",)),
    ("archive", "Internet Archive", ("archive.org",)),
    ("crunchyroll", "Crunchyroll", ("crunchyroll.com",)),
    ("steam", "Steam", ("steampowered.com", "steamcommunity.com")),
    ("patreon", "Patreon", ("patreon.com",)),
    ("vevo", "Vevo", ("vevo.com",)),
    ("nebula", "Nebula", ("nebula.tv",)),
    ("bitchute", "BitChute", ("bitchute.com",)),
    ("threads", "Threads", ("threads.net", "threads.com")),
    ("snapchat", "Snapchat", ("snapchat.com",)),
    ("telegram", "Telegram", ("t.me", "telegram.me")),
    ("twitcasting", "TwitCasting", ("twitcasting.tv",)),
    ("9gag", "9GAG", ("9gag.com",)),
    ("googledrive", "Google Drive", ("drive.google.com",)),
    ("dropbox", "Dropbox", ("dropbox.com",)),
    ("applepodcasts", "Apple Podcasts", ("podcasts.apple.com",)),
    ("aparat", "Aparat", ("aparat.com",)),
    ("telewebion", "Telewebion", ("telewebion.com",)),
    ("naver", "Naver TV", ("naver.com", "naver.me")),
    ("kakao", "Kakao TV", ("kakao.com",)),
    ("soop", "SOOP / AfreecaTV", ("sooplive.co.kr", "afreecatv.com")),
    ("youku", "Youku", ("youku.com",)),
    ("iqiyi", "iQIYI", ("iqiyi.com", "iq.com")),
    ("zingmp3", "Zing MP3", ("zingmp3.vn",)),
    ("aljazeera", "Al Jazeera", ("aljazeera.com", "aljazeera.net")),
    ("cnn", "CNN", ("cnn.com",)),
    ("espn", "ESPN", ("espn.com",)),
    ("cbc", "CBC", ("cbc.ca",)),
    ("dw", "DW", ("dw.com",)),
    ("nrk", "NRK", ("nrk.no",)),
    ("svt", "SVT Play", ("svtplay.se", "svt.se")),
    ("ard", "ARD Mediathek", ("ardmediathek.de", "ard.de")),
    ("zdf", "ZDF", ("zdf.de",)),
    ("rai", "RaiPlay", ("raiplay.it", "rai.it")),
    ("rtve", "RTVE", ("rtve.es",)),
    ("pornhub", "Pornhub", ("pornhub.com", "pornhub.org")),
    ("xvideos", "XVideos", ("xvideos.com",)),
    ("xhamster", "xHamster", ("xhamster.com",)),
    ("redtube", "RedTube", ("redtube.com",)),
)

# Kept as an alias: older configurations and any external code may still
# refer to the previous name.
POPULAR_SITES = SITES

# Sites that are always accepted regardless of the allowlist, because they have
# their own dedicated watcher category and format preference.
ALWAYS_ALLOWED_KEYS = frozenset({"youtube", "ytmusic", "spotify"})

DEFAULT_ENABLED_SITE_KEYS: Tuple[str, ...] = (
    "youtube",
    "ytmusic",
    "spotify",
    "soundcloud",
    "bandcamp",
    "vimeo",
    "dailymotion",
    "twitch",
    "tiktok",
    "instagram",
    "facebook",
    "twitter",
    "reddit",
)

SITE_LABELS: Dict[str, str] = {key: label for key, label, _ in SITES}

# domain -> site key. Built once; lookups are per clipboard change.
_DOMAIN_INDEX: Dict[str, str] = {
    domain.lower(): key for key, _label, domains in SITES for domain in domains
}


def host_of(url: str) -> str:
    try:
        netloc = urlsplit((url or "").strip()).netloc
    except ValueError:
        return ""
    return netloc.split("@")[-1].split(":")[0].lower().removeprefix("www.")


def site_key_for(url: str) -> str:
    """Site key for a URL, or "" when it is not one of the curated sites.

    Matching walks the host upwards (`clips.twitch.tv` -> `twitch.tv`) so
    regional and subdomain variants resolve without listing each one, while
    still being a suffix match on label boundaries rather than a substring
    check that `evil.example/?x=youtube.com` would satisfy.
    """
    host = host_of(url)
    if not host:
        return ""
    parts = host.split(".")
    for index in range(len(parts) - 1):
        candidate = ".".join(parts[index:])
        key = _DOMAIN_INDEX.get(candidate)
        if key:
            return key
    return ""


def is_site_enabled(url: str, enabled_keys: Sequence[str]) -> bool:
    key = site_key_for(url)
    if not key:
        return False
    if key in ALWAYS_ALLOWED_KEYS:
        return True
    # Membership test runs directly against the sequence. Building a temporary
    # set here allocated on every clipboard change; for the handful of enabled
    # keys a linear scan is cheaper than hashing them all.
    return key in (enabled_keys or ())
