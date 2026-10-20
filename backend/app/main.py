import hmac
import html
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

load_dotenv()

from app import checker, db, feedback_store, instagram, limits, ops_alerts, reports_store, telegram_api, telegram_bot, verdict_engine, visits_store
from app.spa import SinglePageStaticFiles
from app.i18n import normalize_lang
from app.schemas import (
    FeedbackRequest,
    VisitRequest,
    ReportRequest,
    ReportResponse,
    StatsResponse,
    VerifyRequest,
    VerifyResponse,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    threading.Thread(target=telegram_bot.register_webhook, daemon=True).start()
    instagram.start_poller()
    ops_alerts.start_key_watch()
    yield


app = FastAPI(title="TrustLine API", lifespan=lifespan)

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
    return checker.check_message(req.message, normalize_lang(req.language))


def _business_contact() -> str | None:
    """Where business owners can reach you: an email address or a link (TikTok, Telegram, ...)."""
    value = os.getenv("BUSINESS_CONTACT", "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return f"mailto:{value}" if "@" in value else None


@app.get("/api/config")
def config():
    return {"telegram_url": telegram_bot.bot_url(), "business_contact": _business_contact()}


@app.post("/api/visit", dependencies=[Depends(limits.limit_report)])
def visit(req: VisitRequest):
    visits_store.record(req.ref)
    return {"ok": True}


def _require_admin(request: Request, response: Response) -> None:
    """Owner-only endpoints need the ADMIN_KEY in the X-Admin-Key header (and do not exist until it is set).
    Repeated wrong keys are locked out, and answers are never cached by the browser or a proxy."""
    key = os.getenv("ADMIN_KEY", "")
    if not key:
        raise HTTPException(status_code=404)
    limits.admin_locked(request)
    if not hmac.compare_digest(request.headers.get("x-admin-key", "").encode(), key.encode()):
        limits.admin_key_failed(request)
        raise HTTPException(status_code=403)
    response.headers["Cache-Control"] = "no-store"


@app.get("/api/visits")
def visits(request: Request, response: Response, days: int = 30):
    _require_admin(request, response)
    return visits_store.counts(max(1, min(days, 90)))


def _notify_feedback(req: FeedbackRequest, ref: str) -> None:
    """Tells the owner on Telegram as soon as someone leaves feedback (set FEEDBACK_NOTIFY_CHAT_ID)."""
    chat_id = os.getenv("FEEDBACK_NOTIFY_CHAT_ID", "").strip()
    if not chat_id.lstrip("-").isdigit():
        return
    esc = html.escape
    stars = f"{'★' * req.rating}{'☆' * (5 - req.rating)}" if req.rating else "no rating"
    lines = [f"<b>New TrustLine feedback</b> · {stars} · via {esc(ref)}", "", esc(req.message[:1500])]
    if req.contact:
        lines += ["", f"Contact: {esc(req.contact[:200])}"]
    if req.wants_pilot:
        lines += ["", "🙋 Wants to join the business pilot"]
    telegram_api.send_message(int(chat_id), "\n".join(lines))


@app.post("/api/feedback", dependencies=[Depends(limits.limit_feedback)])
def feedback(req: FeedbackRequest, background: BackgroundTasks):
    if req.website:  # the hidden field was filled in: a bot, not a person. Pretend it worked.
        return {"ok": True}
    feedback_store.add(req.message, req.rating, req.contact, req.wants_pilot, req.ref, req.language)
    background.add_task(_notify_feedback, req, visits_store.clean_ref(req.ref))
    return {"ok": True}


@app.get("/api/feedback")
def feedback_list(request: Request, response: Response, limit: int = 50):
    _require_admin(request, response)
    return feedback_store.latest(max(1, min(limit, 200)))


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, background: BackgroundTasks):
    bot_token = telegram_api.token()
    if not bot_token:
        raise HTTPException(status_code=404)
    supplied = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(supplied, telegram_api.webhook_secret(bot_token)):
        raise HTTPException(status_code=403)
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400)
    # Answer Telegram immediately; the check (which can take seconds) runs in the background.
    background.add_task(telegram_bot.process_update, update)
    return {"ok": True}


@app.get("/instagram/webhook")
def instagram_webhook_verify(request: Request):
    """Meta's one-time handshake when the webhook is saved in the app dashboard."""
    q = request.query_params
    wanted = instagram.verify_token()
    if wanted and q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), wanted):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(status_code=403)


@app.post("/instagram/webhook")
async def instagram_webhook(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not instagram.verify_signature(body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=403)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400)
    background.add_task(instagram.handle_webhook, payload)  # answer Meta at once; the check runs afterwards
    return {"ok": True}


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
    app.mount("/", SinglePageStaticFiles(directory=STATIC_DIR, html=True), name="frontend")
