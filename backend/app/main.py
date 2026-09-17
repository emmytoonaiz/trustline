from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app import link_handler, reports_store, verdict_engine
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


@app.post("/api/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest):
    link = link_handler.find_link(req.message)
    if link is None:
        return verdict_engine.analyze(req.message)

    platform, url = link
    label = link_handler.PLATFORM_LABELS[platform]

    if platform == "youtube":
        video_id = link_handler.extract_youtube_id(url)
        fetched_text = link_handler.fetch_youtube_text(video_id) if video_id else None
        if fetched_text:
            # Keep the user's own wrapper text (e.g. "claim your prize") alongside the fetched
            # video info -- a legitimate-looking video can still be wrapped in a fraudulent claim.
            combined = f"Message from the user sharing this link:\n{req.message}\n\nFetched YouTube video info:\n{fetched_text}"
            result = verdict_engine.analyze(combined)
            result.source_platform = "youtube"
            return result
        return VerifyResponse(
            verdict="link_unsupported",
            confidence=0,
            headline="Couldn't fetch that YouTube video's details",
            link_notice="We couldn't automatically read this video right now. Paste the video's title, description, or comment text instead and we'll check that.",
            source_platform="youtube",
        )

    return VerifyResponse(
        verdict="link_unsupported",
        confidence=0,
        headline=f"We can't automatically read {label} links yet",
        link_notice=f"{label} blocks automatic reading of posts. Copy the caption or message text from the post and paste it here instead — we'll check that.",
        source_platform=platform,
    )


@app.post("/api/report", response_model=ReportResponse)
def report(req: ReportRequest):
    new_id = reports_store.add_report(req.message, req.category, req.location)
    return ReportResponse(status="ok", id=new_id)


@app.get("/api/stats", response_model=StatsResponse)
def stats():
    return reports_store.get_stats()
