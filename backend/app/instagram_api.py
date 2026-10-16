import logging
import os

import requests

logger = logging.getLogger("trustline.instagram_api")

BASE = "https://graph.instagram.com"


def token() -> str | None:
    return os.getenv("INSTAGRAM_ACCESS_TOKEN") or None


def _version() -> str:
    return os.getenv("INSTAGRAM_API_VERSION", "v25.0")


def _call(method: str, path: str, params: dict | None = None) -> dict | None:
    """One Graph API call. The token travels in a header and the URL is never logged."""
    access_token = token()
    if not access_token:
        return None
    try:
        resp = requests.request(
            method,
            f"{BASE}/{_version()}/{path}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        data = resp.json()
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            logger.warning("Instagram %s %s failed: %s (code %s)", method, path.split("/")[-1][:8], err.get("message"), err.get("code"))
            return None
        return data
    except Exception as exc:
        logger.warning("Instagram request failed: %s", type(exc).__name__)
        return None


def me() -> dict | None:
    """The account the token belongs to: {"user_id": ..., "username": ...}."""
    data = _call("GET", "me", {"fields": "user_id,username"})
    if not data:
        return None
    user_id = data.get("user_id") or data.get("id")
    return {"user_id": str(user_id), "username": data.get("username") or ""} if user_id else None


def recent_media(limit: int = 3) -> list[dict]:
    data = _call("GET", "me/media", {"fields": "id,timestamp", "limit": limit})
    return (data or {}).get("data", [])


def media_comments(media_id: str, limit: int = 50) -> list[dict]:
    data = _call("GET", f"{media_id}/comments", {"fields": "id,text,timestamp,username", "limit": limit})
    return (data or {}).get("data", [])


def hide_comment(comment_id: str) -> bool:
    data = _call("POST", comment_id, {"hide": "true"})
    return bool(data and data.get("success", True))


def delete_comment(comment_id: str) -> bool:
    data = _call("DELETE", comment_id)
    return bool(data and data.get("success", True))
