from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app import limits, link_handler, reports_store, verdict_engine
from app.i18n import normalize_lang, t
from app.schemas import (
    ReportRequest,
    ReportResponse,
    StatsResponse,
    VerifyRequest,
    VerifyResponse,
)

app = FastAPI(title="TrustLine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/verify", response_model=VerifyResponse, dependencies=[Depends(limits.limit_verify)])
def verify(req: VerifyRequest):
    lang = normalize_lang(req.language)
    link = link_handler.find_link(req.message)
    if link is None:
        return verdict_engine.analyze(req.message, lang)

    platform, url = link
    label = link_handler.PLATFORM_LABELS[platform]

    if platform == "youtube":
        video_id = link_handler.extract_youtube_id(url)
        fetched_text = link_handler.fetch_youtube_text(video_id) if video_id else None
        if fetched_text:
            # Keep the user's own wrapper text (e.g. "claim your prize") alongside the fetched
            # video info -- a legitimate-looking video can still be wrapped in a fraudulent claim.
            combined = f"Message from the user sharing this link:\n{req.message}\n\nFetched YouTube video info:\n{fetched_text}"
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


@app.post("/api/report", response_model=ReportResponse, dependencies=[Depends(limits.limit_report)])
def report(req: ReportRequest):
    new_id = reports_store.add_report(req.message, req.category, req.location)
    return ReportResponse(status="ok", id=new_id)


@app.get("/api/stats", response_model=StatsResponse)
def stats(language: str = "en"):
    result = reports_store.get_stats()
    labels = verdict_engine.category_labels(normalize_lang(language))
    result["top_categories"] = [
        {**c, "category": labels.get(c["category"], c["category"])} for c in result["top_categories"]
    ]
    return result


# In production the built frontend is copied next to the backend and served from the same
# address, so the browser calls /api on its own origin. Absent locally (Vite serves it there).
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
