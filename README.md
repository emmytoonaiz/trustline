# TrustLine — Verify before you trust

Built for the **OSF × Andela "Build for Africa" Hackathon** (theme: *Information You Can Trust*).

## The problem

Scam messages — fake bank alerts, "guaranteed" loans, OTP-harvesting texts, romance scams,
crypto pyramid schemes — spread fastest exactly where verification is hardest: low-bandwidth
connections, unfamiliar formats, and victims under time pressure ("act within 24 hours").
Most people have no fast, private way to check "is this real?" before they act.

## Who it's for

Everyday phone users in Nigeria/Kenya (and beyond) who receive a suspicious SMS, WhatsApp
message, or call script and want a quick, judgment-free second opinion before they click a
link, share an OTP, or send money.

## How it works

1. **Paste the message.** The user pastes the suspicious text into a lightweight chat UI
   (works on low bandwidth — plain text, no heavy assets).
2. **Match against a curated scam-pattern library** (`backend/app/data/scam_patterns.json`, 20
   patterns) — OTP/PIN requests, fake account-suspension links, loan upfront fees, romance
   scams, "guaranteed" investment returns, lottery/prize scams, SIM-swap data requests,
   courier/customs fee scams, fake job offers, compromised-account transfer requests, mobile
   money reversal fraud, celebrity/crypto giveaway scams, fake rental listings, fake customer
   care callbacks, impersonated support accounts, tax refund phishing, scholarship fee scams,
   the "Hi Mum, new number" family emergency scam, marketplace pay-before-delivery fraud, and
   tampered QR-code payments — each with real-world reasoning ("why"), concrete advice, and a
   source citation.
3. **Get a verdict**: *Likely a scam*, *Be careful*, or *No known pattern detected* — with a
   confidence score, plain-language reasoning, and a next step, not just a label.
4. **Report new scams**: users can flag a message as a new scam, feeding a community stats
   panel (`GET /api/stats`) — the beginning of a crowd + curated trust layer rather than a
   static list.
5. **Paste a link instead of text.** TrustLine detects YouTube, X/Twitter, Facebook, and
   Instagram links (`backend/app/link_handler.py`). YouTube links are fetched automatically
   (title + description, via the free YouTube Data API v3) and run through the same verdict
   pipeline. X, Facebook, and Instagram block automated reading of posts, so those get an
   honest "paste the caption/text instead" prompt rather than a best-effort scrape that could
   silently fail or break live during a demo.

## Why it's worth developing further

- **Rule-based matching + an LLM reasoning layer, combined.** Exact matches against the curated
  pattern library return instantly with a real citation and no API cost. Anything the keyword
  matcher doesn't confidently recognize is handed to Claude (`backend/app/verdict_engine.py::_llm_analyze`),
  which reasons about the specific message and returns a structured verdict — so TrustLine isn't
  limited to scams it has seen before. If no `ANTHROPIC_API_KEY` is configured, it falls back to
  the rule-based heuristics automatically, so the app never breaks in a demo with a flaky key/network.
- The **pattern library is a seed**, meant to grow from real community reports and partnerships
  with consumer-protection bodies (CBN, EFCC, NCC-style advisories) rather than stay static.
- Designed from day one for **real-world constraints** the hackathon brief calls out:
  - *Low bandwidth*: plain-text chat UI, no heavy images/frameworks.
  - *Accessibility*: large tap targets, plain language, mobile-first layout.
  - *Multilingual access*: English, **French**, **Swahili** (Kenya), **Yoruba** and **Hausa**
    (Nigeria), plus a Nigerian Pidgin interface. The four translated languages are supported
    end to end — the interface, all 21 curated scam explanations
    (`backend/app/data/scam_patterns_<lang>.json`), Claude's live answers (it is told to reply
    in the user's language), the link notices, and the community stats. French and Swahili also
    carry local trigger phrases so a scam text in that language is caught instantly by the free
    library; Yoruba and Hausa messages go to Claude instead, since tone marks and special letters
    are typed inconsistently. Pidgin covers the interface only. The Yoruba and Hausa
    translations are machine-drafted and should be reviewed by native speakers before real
    deployment. Adding another language means one new copy block, one strings block in
    `backend/app/i18n.py`, and one translated pattern file.
  - *Privacy*: no login, no phone number collection — you paste text, you get an answer.
  - *Trust & verification*: every scam verdict cites a specific reason and source instead of
    a black-box "trust me."
- **Next steps if we keep building**: real WhatsApp/SMS channel (Twilio/Africa's Talking) so it
  reaches people who never open a browser; a moderation queue so community-reported scams get
  reviewed before joining the pattern library; and extending link support to X/Facebook/Instagram
  if/when those platforms offer a reliable free read path (as of 2026, X's official API dropped
  its free tier entirely — pay-per-use, no billing-free option — and Facebook/Instagram require
  login for most post access, so we chose an honest fallback over a fragile scraper for the demo).

## Track fit

- **Transparency & Accountability** — helps people scrutinize the legitimacy of offers,
  institutional-looking messages, and alerts before acting on them.
- **Safety, Reporting & Protection** — gives people a private way to check for financial threats
  and a path to report new ones.
- **Stability & Social Cohesion** (secondary) — reduces panic/urgency-driven bad decisions caused
  by convincing but fake "urgent" messages.

## Running it locally

### Backend (FastAPI)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # optional: add ANTHROPIC_API_KEY and/or YOUTUBE_API_KEY
uvicorn app.main:app --reload --port 8000
```

Both keys are optional and independent:
- Without `ANTHROPIC_API_KEY`, `/api/verify` still works end-to-end using the rule-based matcher only.
- Without `YOUTUBE_API_KEY` (free, no billing — see `.env.example` for setup), YouTube links get
  a graceful "couldn't fetch, paste the text instead" notice rather than a fetched verdict.

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Then open the printed Vite URL (default `http://localhost:5173`). The frontend proxies
`/api/*` calls to the backend on port 8000.

## Deploying (Railway)

The `Dockerfile` at the repo root builds the React frontend and serves it from the FastAPI
backend, so one service hosts the whole app (the browser calls `/api` on its own address).
Railway builds it straight from this repo (`railway.json` points at the Dockerfile and uses
`/health` as the health check).

Set these as service variables in Railway (never commit them):

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables Claude reasoning for messages the curated library doesn't match. Without it the app still works on the curated patterns alone. |
| `YOUTUBE_API_KEY` | Enables reading YouTube links. Without it, YouTube links get a "paste the text instead" notice. |
| `DATABASE_URL` | Postgres connection string (on Railway: add a Postgres service and set `DATABASE_URL=${{Postgres.DATABASE_URL}}`). Without it the app uses a local SQLite file — fine for development, but it is lost on every redeploy. |
| `TELEGRAM_BOT_TOKEN` | Optional. Turns on the Telegram bot (see below). |
| `LLM_DAILY_CAP` | Optional. Most AI calls allowed per day (default `1000`) — a cost ceiling for a public site. |
| `ACCOUNT_WARN_THRESHOLD` | Optional. How many different people must report a Telegram account before the bot warns about it (default `3`). |
| `PRIVACY_SALT` | Optional. Secret used to hash Telegram ids. Defaults to a value derived from the bot token; set it explicitly to keep hashes stable if the token is ever rotated. |
| `DEMO_SEED_STATS` | Optional. Set to `1` to show made-up demo numbers in the community stats panel. Off by default so the panel only shows real reports. |
| `BUSINESS_CONTACT` | Optional. An email address or link (e.g. a TikTok profile) for the "Join the pilot" button on the site. The button stays hidden until it is set. |
| `ADMIN_KEY` | Optional. Secret that unlocks the owner-only `GET /api/visits` (visit counts per `?ref=` label) and `GET /api/feedback` (everything people wrote in the feedback form), sent as the `X-Admin-Key` header. These endpoints do not exist until it is set. |
| `FEEDBACK_NOTIFY_CHAT_ID` | Optional. Your Telegram chat id (send `/myid` to the bot to find it). Each new piece of feedback is then forwarded to you there as it arrives. |
| `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_VERIFY_TOKEN`, `INSTAGRAM_PAIRING_CODE` | Optional. Turn on Instagram comment monitoring for one account (see [docs/INSTAGRAM-SETUP.md](docs/INSTAGRAM-SETUP.md)). |
| `MONITOR_MIN_CONFIDENCE`, `MONITOR_CHECKS_PER_HOUR`, `MONITOR_INCLUDE_OWNER` | Optional. Group-monitoring tuning (see the Telegram section). |

Because the site is public and calls a paid API, `/api/verify` is limited to 20 requests per
minute per visitor, `/api/report` to 10, and messages to 4,000 characters.
Visits are counted per link label (`/?ref=tiktok`), with no IP address, cookie or other identifier.
The community stats shows the last 7 days of real reports and stays hidden until there are some.

## Telegram bot

`POST /telegram/webhook` powers the bot. In a private chat, users paste or **forward** a
suspicious message, or send a **screenshot**, and get the same verdict as on the website, in
their language (picked from their Telegram settings, changeable with `/language`). Buttons let
them report the scam and, for forwarded messages, the sender's account.

- **Screenshots:** Claude transcribes the image, then the text goes through the normal check
  (curated library first), and the bot shows what it read so the user can see it understood.
- **Groups:** by default the bot never reads a group's conversation. Someone replies to a message
  with `/check` and the bot answers under that message.
- **Group monitoring (opt-in, for businesses):** when an owner makes the bot an **administrator**
  of their group, it starts watching that group for scams. Nothing is posted in the group:
  a suspicious message goes to the owner as a private alert with **Delete** / **Keep** buttons,
  and only the owner can press them (deleting needs the "delete messages" admin right; without
  it the alert is informational). Cheap pre-filtering (links, phone/account numbers, money,
  risk words, curated patterns) decides which messages get a full check, and only confident
  "likely scam" verdicts (`MONITOR_MIN_CONFIDENCE`, default 70) reach the owner. A per-group cap
  (`MONITOR_CHECKS_PER_HOUR`, default 60) bounds AI cost. Set `MONITOR_INCLUDE_OWNER=true` to also check the owner's own messages (for testing alone; leave it off in production). Removing the bot, or demoting it,
  stops monitoring. Telegram admin bots see all messages in the group, so this is what the
  owner is consenting to when they promote the bot.
- **Website link:** the site shows a "chat with the bot" link once the bot is running (the
  username comes from Telegram itself; set `TELEGRAM_BOT_USERNAME` to override).

Setup: message `@BotFather` on Telegram, create a bot, and add its token as
`TELEGRAM_BOT_TOKEN`. On start-up the server registers its own webhook (it reads Railway's
public domain automatically; set `PUBLIC_BASE_URL` to override) — the token is never logged.
Telegram's requests are verified with a secret header derived from the token.

Privacy and abuse design:
- **Reporter identities are hashed.** A reporter's Telegram id is stored only as a salted
  one-way hash, used to stop one person from reporting the same account twice.
- **No message history.** A checked message is held for 24 hours so the Report buttons work,
  then deleted; it is only kept if the user taps Report.
- **Account warnings need several reporters.** The bot only warns about an account once
  `ACCOUNT_WARN_THRESHOLD` different people reported it, and words it as "reported by N users".
  The "Report the sender" button is only offered for messages judged scam or uncertain, and
  each person can file at most 20 account reports a day.
- **Monitoring keeps the minimum.** Only the group's and the owner's Telegram ids (needed to send
  alerts), plus a 500-character excerpt of each flagged message, which is purged after 14 days.
  Messages that are not flagged are never stored.
- The bot never receives IP addresses, phone numbers or locations from Telegram, and doesn't ask.

## Instagram comment monitoring (prototype)

The same idea as group monitoring, for the comments on an Instagram professional account: a comment that
looks like a scam produces a private Telegram alert with **Hide / Delete / Keep** buttons, and only the owner's
tap changes anything on Instagram. Comments arrive through Meta's webhook (`/instagram/webhook`, verified with
the app secret) and through a light polling fallback that works in Meta's development mode. One account is
supported for now; letting other businesses connect needs Meta App Review. Setup: [docs/INSTAGRAM-SETUP.md](docs/INSTAGRAM-SETUP.md).

Run the tests (fake Telegram, throwaway database): `cd backend && python -m pytest tests`.
Set `TEST_DATABASE_URL` to run them against Postgres.

## Project structure

```
trustline/
  backend/
    app/
      main.py            # FastAPI routes: /api/verify, /api/report, /api/stats
      verdict_engine.py  # rule-based matcher + Claude reasoning layer
      link_handler.py    # detects YouTube/X/Facebook/Instagram links, fetches YouTube content
      checker.py         # the full check (links, pattern library, Claude), shared by web and bot
      i18n.py            # translated headlines/fallbacks/link notices
      limits.py          # per-visitor rate limits and the daily AI-call ceiling
      db.py              # database tables (Postgres in production, SQLite locally)
      reports_store.py   # community reports + stats
      telegram_bot.py    # Telegram bot: private chats, groups (/check), buttons, reports, webhook
      image_reader.py    # reads the text out of screenshots with Claude
      telegram_api.py    # thin client for Telegram's Bot API
      monitor.py         # opt-in group monitoring: private alerts to the owner, delete/keep buttons
      monitor_store.py   # watched groups and alerts
      instagram.py       # Instagram comments: webhook, polling, pairing, Hide/Delete/Keep buttons
      instagram_api.py   # thin client for Instagram's Graph API
      instagram_store.py # linked account and alerts
      triage.py          # cheap risk-signal filter that decides which group messages get an AI check
      telegram_store.py  # language choices, pending checks, account reports (hashed reporters)
      bot_i18n.py        # the bot's text in five languages
      schemas.py          # request/response models
      data/scam_patterns.json     # curated scam pattern library (English)
      data/scam_patterns_fr.json  # French translations + French trigger phrases
  frontend/
    src/
      App.jsx             # chat UI shell
      components/VerdictCard.jsx
      components/StatsPanel.jsx
      copy.js              # EN / FR / Pidgin UI strings + language list
      api.js
```
