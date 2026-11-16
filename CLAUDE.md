# CLAUDE.md: TrustLine

Guidance for Claude Code (and humans) picking this project up on a new machine. Read this first, then `README.md`
for the long version. **Never put secrets in this file or anywhere in git.**

## What this is

TrustLine is a scam-verification assistant for Nigeria and Kenya (built for the OSF x Andela "Build for Africa"
hackathon, now being piloted publicly). A user pastes a suspicious message, link or screenshot and gets a verdict
(likely scam / be careful / no known pattern), plain-language reasons and advice, in English, Yorùbá, Hausa,
Français or Kiswahili.

Surfaces: a website, a Telegram bot (private chats, `/check` in groups), opt-in **Telegram group monitoring** for
businesses (private alerts with Delete/Keep buttons), and an **Instagram comment monitoring prototype**.

Live: <https://trustline-production.up.railway.app> (Railway), bot `@TrustLineScamBot`, owner dashboard at `/admin`.

## Status (as of 2026-11-16)

Working and live: web app, 21 curated scam patterns (5 languages), Claude reasoning layer, Postgres, Telegram bot
(text, forwarded messages, screenshots, groups, account-level reports), Telegram group monitoring, feedback form
and `/admin` dashboard, `?ref=` visit counter, Telegram operations alerts (AI key rejected / credit low / daily cap).

**Built but never verified against the real service:**
- Instagram monitoring (`instagram*.py`). Tested only against a fake Instagram; Meta payload shapes and the hide
  call come from Meta's docs. Needs a Meta developer app, an Instagram tester account and an access token (see
  `docs/INSTAGRAM-SETUP.md`). Meta says comment webhooks need a Live app with Advanced Access, so there is also a
  polling fallback for development mode.
- Yorùbá and Hausa translations are unreviewed drafts. Have native speakers check them.

**Planned, not started:** a Facebook Page comment adapter (same Meta app and the same flow as Instagram: webhook +
polling, private Telegram alert, Hide/Delete/Keep). TikTok: no confirmed official API for moderating other people's
comments on organic videos, so the plan is link/screenshot checks plus a scam keyword list for TikTok's own comment
filter, and applying for developer access. Also needed before onboarding other businesses: a "Connect your account"
flow, encrypted per-business tokens and token refresh, Meta App Review and business verification.

## Run it locally

Backend (production runs Python 3.12; 3.14 also worked locally. The requirements are deliberately unpinned because
pinned versions failed to build on 3.14):

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/python
cp .env.example .env                                            # add ANTHROPIC_API_KEY (optional, see below)
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

Use `python -m uvicorn`, not the `uvicorn` executable (the managed Windows laptop blocked `uvicorn.exe`).
Frontend: `cd frontend && npm install && npm run dev` (Vite on 5173, proxies `/api` to `localhost:8000`).
Without `ANTHROPIC_API_KEY` the app still works on the pattern library alone. The local database is a SQLite file
(`backend/app/data/trustline.db`); production uses Postgres via `DATABASE_URL`.

Tests (no network, no paid services; `tests/conftest.py` blanks the keys and fakes Telegram):

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests -q        # 119 tests at last count
```

Set `TEST_DATABASE_URL` to run them against Postgres. Always run the suite before pushing.

## Architecture map (`backend/app/`)

| File | Role |
|---|---|
| `main.py` | FastAPI app, lifespan (DB init, Telegram webhook registration, pollers), all routes, serves the built frontend |
| `checker.py` | The full check: link handling, pattern library, Claude. Shared by web, bot, monitors |
| `verdict_engine.py` | Pattern matcher (`data/scam_patterns*.json`) and Claude layer (`messages.parse`, effort low, `max_tokens=900`) |
| `triage.py` | Cheap risk-signal filter deciding which monitored messages get a paid AI check |
| `monitor.py` / `monitor_store.py` | Telegram group monitoring; `assess()` and `alert_body()` are shared with Instagram |
| `instagram.py` / `instagram_api.py` / `instagram_store.py` | Instagram webhook, polling fallback, pairing, Hide/Delete/Keep |
| `telegram_bot.py` / `telegram_api.py` / `telegram_store.py` / `bot_i18n.py` | The bot, its Bot API client, hashed-id storage, strings |
| `ops_alerts.py` | Telegram alerts to the owner when the AI stops working, plus a 6-hourly key check |
| `limits.py` | Per-visitor rate limiters, daily AI cap, admin-key lock-out |
| `db.py` | SQLAlchemy models. `create_all` at start-up, **no migrations** (see gotchas) |
| `spa.py` | Static file serving that shows the app for unknown page addresses (not for `/api`, files, etc.) |
| `reports_store.py`, `feedback_store.py`, `visits_store.py` | Community reports, feedback form, visit counter |
| `i18n.py`, `data/scam_patterns_{fr,sw,yo,ha}.json` | Translations of verdict text and patterns |

Frontend (`frontend/src/`): `App.jsx` (chat UI), `AdminPage.jsx` (`/admin`), `components/`, `copy.js` (UI text; only
English has the newest business/feedback strings, others fall back to it).

## Rules that keep this safe (don't break these)

- **Privacy:** Telegram reporter ids are stored only as salted HMAC hashes. A checked message is held 24 h for the
  Report buttons, then deleted. Monitoring stores the chat and owner ids it must have to send alerts, plus a
  500-character excerpt of flagged messages, purged after 14 days. Unflagged messages are never stored.
- **Owner decides:** nothing is hidden or deleted on any platform until the owner taps a button, and only the owner
  can press it.
- **Cost controls:** keep `triage` in front of the AI, the per-place hourly cap, the confidence floor
  (`MONITOR_MIN_CONFIDENCE`), `LLM_DAILY_CAP`, and message size limits.
- **Telegram messages use HTML parse mode:** `html.escape` every piece of user-supplied text. `callback_data` must
  stay under 64 bytes.
- **Never log tokens or URLs containing tokens.** Instagram calls send the token in a header for this reason.
- Tests must never call paid or external services. Add a test for every behaviour you add.

## Conventions and gotchas

- **Five languages stay in step.** `bot_i18n.STRINGS` has the same keys for `en/fr/sw/yo/ha`; `s()` raises
  `KeyError` for a missing key. Add keys to all five (generate the edit with a script using `json.dumps` rather than
  hand-pasting; accents and curly quotes got mangled once). New scam patterns go in `scam_patterns.json` and all four
  translation files; `tests/test_patterns.py` checks this.
- **No database migrations.** `create_all` only creates *new* tables. Adding a column to an existing table needs a
  manual `ALTER TABLE` on Railway's Postgres.
- **Anthropic API keys expire** (30 days by default in the Console) and **must be created in the Default workspace**,
  or the API returns 400 "not scoped to a workspace". When the key fails, visitors silently get weaker answers; the
  ops alerts and 6-hourly key check exist so the owner finds out. Keep a calendar reminder for the expiry date.
- Pattern matching is keyword-substring scoring: 2+ keyword hits give "likely scam"; 1 hit gives "be careful".
  Real messages rarely match long exact phrases, so prefer short keywords and test with realistic messages.
- Windows quirks: heredoc-based Python string patches have silently failed on `\n` escapes; prefer editing files
  with the editor tools and assert that replacements matched. Docker Desktop must be started manually and takes
  minutes to come up.

## Deploy (Railway)

One service built from the root `Dockerfile` (Node builds the React app, FastAPI serves it), plus a Postgres service.
**Pushing to GitHub does not deploy.** After pushing, redeploy from source:

```bash
railway redeploy --service trustline --from-source -y
```

On the previous Windows laptop the Railway CLI ran inside Docker because the native exe was blocked
(`docker run --rm -v railway-config:/root/.railway -v <workdir>:/work -w /work railway-cli <command>`). On a normal
machine install the CLI (`npm i -g @railway/cli`), run `railway login`, then `railway link` and pick the `trustline`
project. Useful commands: `railway status`, `railway logs --service trustline`,
`railway variable list --service trustline`, `railway variable delete KEY --service trustline`.
If deploys are refused with "paused temporarily", check <https://status.railway.com>.

Configuration is Railway service variables (names and purposes are in the README table): `ANTHROPIC_API_KEY`,
`DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `YOUTUBE_API_KEY`, `ADMIN_KEY`, `FEEDBACK_NOTIFY_CHAT_ID`,
`BUSINESS_CONTACT`, `LLM_DAILY_CAP`, the `INSTAGRAM_*` set, and tuning knobs. The server registers its own Telegram
webhook at start-up. Get secrets from the owner or Railway; do not invent or commit them.

## Git

- Remote: `https://github.com/emmytoonaiz/trustline` (public), branch `main`.
- **Set a repo-local identity on every new machine**; do not use a work email on this public repo:
  `git config user.name "<name>"` and `git config user.email "<personal email>"`.
- Commit messages: short imperative subject, a body explaining why, then the co-author trailer if Claude helped.

## Not in git (carry these over from the old laptop by hand)

| Item | Why it matters |
|---|---|
| `backend/.env` | Local API keys. Recreate from `.env.example`. Do not copy keys that may have expired |
| `marketing/` | TikTok kit (PDF), the LinkedIn clip generator and video. Deliberately git-ignored |
| `submission/` | Hackathon pitch deck PDF and demo videos. Git-ignored |
| Railway login | Re-authenticate; the old laptop's login does not move |
| Claude memory | Notes from the old laptop do not transfer; this file replaces them |

## Next steps, in order

1. Create the Meta developer app and run the Instagram prototype on a test account (`docs/INSTAGRAM-SETUP.md`);
   fix whatever the real payloads reveal.
2. Build the Facebook Page adapter on the same pattern, then the TikTok alternatives.
3. Collect pilot feedback from `/admin`; have Yorùbá and Hausa reviewed; start Meta business verification.
4. Before onboarding other businesses: connect flow, encrypted token storage, token refresh, Meta App Review.
