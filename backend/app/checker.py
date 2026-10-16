from app import link_handler, verdict_engine
from app.i18n import t
from app.schemas import VerifyResponse


def check_message(message: str, lang: str) -> VerifyResponse:
    """The full check, shared by the website and the Telegram bot: link handling, the curated
    pattern library, then Claude for anything the library doesn't recognise."""
    link = link_handler.find_link(message)
    if link is None:
        return verdict_engine.analyze(message, lang)

    platform, url = link
    label = link_handler.PLATFORM_LABELS[platform]

    if platform == "youtube":
        video_id = link_handler.extract_youtube_id(url)
        fetched_text = link_handler.fetch_youtube_text(video_id) if video_id else None
        if fetched_text:
            # Keep the user's own wrapper text (e.g. "claim your prize") alongside the fetched
            # video info -- a legitimate-looking video can still be wrapped in a fraudulent claim.
            combined = f"Message from the user sharing this link:\n{message}\n\nFetched YouTube video info:\n{fetched_text}"
            result = verdict_engine.analyze(combined, lang)
            result.source_platform = "youtube"
            return result
        return VerifyResponse(
            verdict="link_unsupported",
            confidence=0,
            headline=t(lang, "yt_failed_headline"),
            link_notice=t(lang, "yt_failed_notice"),
            source_platform="youtube",
        )

    return VerifyResponse(
        verdict="link_unsupported",
        confidence=0,
        headline=t(lang, "platform_headline", platform=label),
        link_notice=t(lang, "platform_notice", platform=label),
        source_platform=platform,
    )
