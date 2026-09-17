import logging
import os
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger("trustline.link_handler")

URL_RE = re.compile(r"https?://\S+")

PLATFORM_HOSTS = {
    "youtube": {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"},
    "x": {"twitter.com", "mobile.twitter.com", "x.com"},
    "facebook": {"facebook.com", "m.facebook.com", "fb.watch", "fb.com"},
    "instagram": {"instagram.com", "instagr.am"},
}

PLATFORM_LABELS = {
    "youtube": "YouTube",
    "x": "X (Twitter)",
    "facebook": "Facebook",
    "instagram": "Instagram",
}

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"

_TRAILING_PUNCTUATION = ").,!?\"'"


def _strip_trailing_punctuation(url: str) -> str:
    return url.rstrip(_TRAILING_PUNCTUATION)


def find_link(text: str) -> Optional[tuple[str, str]]:
    """Return (platform, url) for the first recognized social link in text, else None."""
    for raw_match in URL_RE.findall(text):
        url = _strip_trailing_punctuation(raw_match)
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        for platform, hosts in PLATFORM_HOSTS.items():
            if host in hosts:
                return platform, url
    return None


def extract_youtube_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")

    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
        return video_id or None

    if host in ("youtube.com", "m.youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        for prefix in ("/shorts/", "/embed/", "/live/"):
            if parsed.path.startswith(prefix):
                return parsed.path[len(prefix):].split("/")[0] or None

    return None


def fetch_youtube_text(video_id: str) -> Optional[str]:
    """Fetch a YouTube video's title/description via the free YouTube Data API v3.

    Returns None (never raises) on a missing key, network failure, or unknown video --
    callers fall back to a graceful "couldn't fetch" notice instead of breaking the demo.
    """
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.get(
            YOUTUBE_API_URL,
            params={"part": "snippet", "id": video_id, "key": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items") or []
        if not items:
            return None
        snippet = items[0]["snippet"]
        return (
            f"YouTube video by {snippet.get('channelTitle', 'unknown channel')}\n"
            f"Title: {snippet.get('title', '')}\n"
            f"Description: {snippet.get('description', '')}"
        )
    except Exception:
        logger.exception("YouTube fetch failed for video_id=%s", video_id)
        return None
