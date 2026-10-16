import hmac
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app import checker, db, limits, reports_store, telegram_api, telegram_bot, verdict_engine
from app.i18n import normalize_lang
from app.schemas import (
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
