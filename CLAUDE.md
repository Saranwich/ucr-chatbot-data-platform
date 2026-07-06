# UCR Smartcity Chatbot — Project Context

## Purpose

A LINE Messaging API chatbot that crowdsources hyper-local environmental and infrastructure problems from community residents. Instead of a fixed survey, an **AI assistant ("น้องเมือง")** chats naturally in Thai, gathers the details of a problem, and extracts a structured report. The bot also **broadcasts weather alerts** (heat/flood) per community and lets the AI collect the on-the-ground impact. Reports are surfaced through a JWT-protected admin dashboard with a map view, to assist in redesigning community maps and facility placement.

> **V2 (AI).** The old rule-based survey engine is gone; the bot is LLM-driven (Gemini) with Redis conversation memory. All report channels write one central **`reports`** table (legacy V1 tables were dropped after backfilling — see *Data model*).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI (async) |
| LLM | Google **Gemini** (`gemini-3.1-flash-lite`) via `google-genai`, function calling |
| Conversation memory | **Redis** (per-user transcript + broadcast-mode flag + pending attachments, TTL 30 min) |
| Database | PostgreSQL + PostGIS (geospatial) |
| DB driver/ORM | asyncpg + SQLAlchemy async |
| Schema | **Alembic** owns the schema (`alembic upgrade head` as a deploy step — no create_all at boot) |
| Validation | Pydantic v2 |
| LINE SDK | linebot v3 (AsyncMessagingApi) |
| Forecast source | data-team S3 bucket (`FORECAST_BASE_URL/<date>.json`, uploaded nightly) |
| Auth (dashboard) | JWT via `python-jose` |
| Deploy adapter | Mangum (AWS Lambda ASGI) |
| Tunnel (dev) | ngrok → `/callback` |

---

## Architecture — `main → routes → handlers → services → models`

`main.py` only **binds** (lifespan = hourly broadcast-scheduler task, CORS, routers, exception handler, Mangum). All logic lives below it. Services do **one thing each**; orchestrators only connect them.

```
เส้น 1 — Reactive: LINE Webhook POST /callback
        │
   routes/line.py         ← parse + signature check + per-event rescue
        │
   ├── handlers/follow_handler.py     (add เพื่อน → upsert User + welcome)
   └── handlers/message_handler.py    ← dispatcher (text / image / location)
         ├── rich-menu buttons → static text / คู่มือ Flex (services/line.py)
         ├── broadcast "ใช่" → set broadcast_mode (Redis) + AI คุยต่อ / "ไม่" → decline
         ├── image → services/line.persist_message_image (LINE CDN → uploads/reports/)
         │            + Redis pending_images + "[ระบบ: ...]" marker เข้า AI
         ├── location → Redis pending_location + marker เข้า AI
         └── free text → AI CORE ↓
                 │
           services/ai_tool  (build_question / build_broadcast_reply)
             ├── services/session.py   ← Redis: transcript (last ~10, TTL 30 min),
             │       broadcast_mode:<user>, pending_images/<location>:<user>
             ├── services/llm.py       ← Gemini seam (chat + record_complaint tool).
             │                            ONLY file importing the SDK
             ├── services/conversation.py ← conversation anchor (ensure_active, archive_key)
             └── services/report.py    ← INSERT reports (+ report_images, PostGIS point)

เส้น 2 — Proactive: weather broadcast
   ⏰ hourly scheduler in main.py lifespan (only_due=True)  |  POST /api/broadcast/run (JWT)
        │
   services/weather.run_broadcast   ← orchestrator, connects only:
     forecast.get_daily (S3 JSON) → weather_broadcast (classify >35°C=heat /
     rain label=flood, strongest per community, filter_due, build flex) →
     user.get_users_by_community → guards (7-day cap in outreach, unfinished
     broadcast) → broadcast.push_to_users (per-user failure isolation) → log_outreach
        │
   user กด "ใช่" บนการ์ด → กลับเข้าเส้น 1 → AI คุยเก็บผลกระทบ → reports source='broadcast'

LIFF pages (same FastAPI origin, LIFF access-token auth)
   ├── routes/report.py    GET /report + POST /api/form-reports (+ image)  → services/form_report.py
   └── routes/userdata.py  GET /userdata + GET/PUT /api/userdata/profile   → services/user.py

Admin REST API
   routes/dashboard.py  GET /api/dashboard/*  (JWT)  → services/dashboard.py
   routes/broadcast.py  POST /api/broadcast/run (JWT) — manual trigger, {date?, force?}
   routes/system.py     GET /api/health (DB reachability)
   routes/viewer.py     GET /viewer (dev-only data viewer)

Image/blob store: utils/storage.py — every module saves/reads through this helper
(local uploads/ by key: reports/<id>.jpg, broadcast/<id>.jpg, conversations/<user>.json;
S3 seam later).
```

---

## The AI conversation (end-to-end)

1. Free text on LINE → `message_handler` → `ai_tool.build_question(user_id, text)` — or, if the Redis `broadcast_mode` flag is set (user pressed "ใช่" on a weather alert), `ai_tool.build_broadcast_reply(...)` with an alert-specific prompt.
2. `ai_tool._run_turn` appends the user turn to the **Redis** session, loads the last ~10 messages, and calls `llm.chat(history, system, tools=[RECORD_COMPLAINT])`.
3. Gemini either asks a follow-up **or** calls `record_complaint` when it has enough. On a tool call the record hook: opens a `conversations` anchor (first record of the chat), **pops pending attachments** (images/location the user sent mid-chat), and `report.save()` inserts into `reports` (+ `report_images` rows, lat/lon → PostGIS `location_data`). The session stays alive — one chat can hold several reports.
4. After a record, the full transcript is dumped via the storage seam (`conversations/<user>.json`) and linked on the anchor (`archive_key`). Sessions auto-expire after 30 min.

**Images & location:** the model stays text-only. Files/coordinates never enter Gemini — the handler stashes them in Redis (`pending_images:` / `pending_location:`) and injects a `[ระบบ: ...]` text marker so the AI acknowledges and moves on. Attachments stick to the first report recorded after they arrive.

**Extraction target:** `category` + `notes` required; `severity`/`title`/`location` optional (see `RECORD_COMPLAINT` in `ai_tool.py`). Known drift: tool emits severity `med`, DBML says `medium` (no DB CHECK — reconcile at the tool spec).

---

## The broadcast pipeline (เส้น 2)

- **Decide:** `weather_broadcast.classify_alert` — temp > 35.0 °C = heat, `condition_label` in rain labels = flood; strongest event per community per day; community names matched **exactly** against `communities` (typos in forecast data land in `unmatched`).
- **Recipients:** `user.get_users_by_community` (FK first, legacy varchar fallback; users without a community are skipped by policy).
- **Guards:** 7-day anti-spam cap per user (`outreach` log; `force=true` skips it — demo lever) and *never-skipped* unfinished-broadcast guard (`report.has_unfinished_broadcast`).
- **Send:** `broadcast.push_to_users` — per-user isolation, one blocked user never kills the round. Every push logged to `outreach`.
- **Triggers:** hourly lifespan task fires events whose forecast `time` falls in the current hour (dev/uvicorn only — dies on Lambda; EventBridge = next sprint, #82), or `POST /api/broadcast/run` with `{"date": "...", "force": true}`.
- **Dev mock:** `scripts/make_mock_forecast.py` writes real-shaped forecast JSON; serve with `python -m http.server 9000 -d mock_forecast` + `FORECAST_BASE_URL=http://localhost:9000/forecast`.

---

## Data model (`app/models/`, timestamps Bangkok UTC+7)

| Model | Table | Note |
|---|---|---|
| `Report` | `reports` | **central table, all channels**: `source` 'ai' \| 'broadcast' \| 'form_report' \| 'survey', `source_ref`, `category_id` FK, `notes`, `severity`, `title`, `status`, `location_text`, `location_data` (PostGIS point), `payload` JSONB |
| `ReportImage` | `report_images` | image storage keys per report (all sources) |
| `Conversation` | `conversations` | chat anchor: `trigger`, `archive_key` → transcript blob |
| `Outreach` | `outreach` | broadcast push log (1 push = 1 row) — anti-spam cap + response tracking |
| `Community` | `communities` | 14 seeded communities (+ lat/lon) — seed data in `services/lookups.py` |
| `Category` | `categories` | report categories, seeded; AI tool enum locked to these values |
| `User` | `users` | `lineuser_id` PK, profile fields, `community_id` FK (+ legacy `community` varchar) |

Legacy V1 survey tables were **dropped** (migration `0002_drop_legacy`) after `app/scripts/backfill_surveys.py` folded them into `reports` (source='survey', `_backfill` marker in payload).

---

## Module Reference

### `app/main.py`
Binds only: lifespan (starts/cancels the hourly broadcast scheduler — schema is Alembic's job), CORS, routers, global exception handler, `handler = Mangum(app)`. Swagger/ReDoc off when `ENV=production`.

### `app/config.py`
Env vars (`CHANNEL_SECRET`, `CHANNEL_ACCESS_TOKEN`, `DATABASE_URL`, `LIFF_REPORT_ID/URL`, `EDIT_PROFILE_ID/URL`, `FORECAST_BASE_URL`) + static reply texts. `config_loader.py` loads `.env` and (in Lambda) AWS Secrets Manager.

### `app/routes/` (thin endpoints, no logic)
| File | Endpoints |
|---|---|
| `line.py` | `POST /callback` — webhook parse + signature + `handle_event_safely` per-event rescue |
| `broadcast.py` | `POST /api/broadcast/run` (JWT) — manual broadcast trigger |
| `dashboard.py` | `GET /api/dashboard/*` (JWT) — stats, available-dates, reports(+id), incomplete-reports, form-reports, broadcast-reports, image/{image_id} |
| `report.py` | `GET /report`, `POST /api/form-reports`, `GET /api/form-reports/{id}/image` |
| `userdata.py` | `GET /userdata`, `GET/PUT /api/userdata/profile` |
| `system.py` | `GET /api/health` — DB reachability (503 when down) |
| `viewer.py` | `GET /viewer` (dev-only page) |

### `app/handlers/` (per-surface dispatch)
- **`message_handler.py`** — routes text/image/location: rich-menu replies, broadcast confirm (`YES_MAP` → broadcast_mode + AI) / decline (`NO_MAP`), attachments → pending stash + marker, free text → AI core.
- **`follow_handler.py`** — `FollowEvent`: upsert `User`, welcome text.
- **`broadcast_flow_handler.py`** — **legacy** state-machine reply flow (`awaiting_*`), kept only as a guard for old unfinished rows; new broadcast replies go through the AI. Owns `YES_MAP`/`NO_MAP` (the button-text contract with `weather_broadcast._MESSAGE_CONFIG`).

### `app/services/` (one file per domain; orchestrators connect, never own domain logic)
- **`ai_tool.py`** — AI core: `NONG_MUEANG_SYSTEM_PROMPT` + `NONG_MUEANG_BROADCAST_PROMPT`, `RECORD_COMPLAINT` tool spec, `_run_turn` (memory + llm.chat + record hook), `build_question`, `build_broadcast_reply`.
- **`llm.py`** — the **only** Gemini import. `chat()` with tool-call rounds (cap 5). Swap providers here alone.
- **`session.py`** — Redis: transcript (`chat:`), `broadcast_mode:`, `pending_images:`, `pending_location:`, `dump_transcript` → storage. `SESSION_TTL = 1800`.
- **`conversation.py`** — conversations anchor (`ensure_active`, `attach_archive`).
- **`report.py`** — `save()` → `reports` (+ `report_images`, PostGIS point); `category_id_for`, `community_id_*`, `has_unfinished_broadcast`.
- **`weather.py`** — broadcast **orchestrator** `run_broadcast(date, force, only_due)` + outreach log/cap (`log_outreach`, `recently_contacted`, CAP_DAYS=7).
- **`weather_broadcast.py`** — decision + message: `classify_alert`, `parse_forecast`, `pick_strongest_per_location`, `filter_due`, `build_message`, `to_sdk_messages`.
- **`forecast.py`** — fetch daily forecast JSON from S3 (`get_daily`; 404/403 → None; else `ForecastUnavailable`).
- **`broadcast.py`** — `push_to_users(user_ids, messages)` with per-user failure isolation.
- **`user.py`** — `get_or_create_user`, `get_profile`, `save_profile`, `get_users_by_community`.
- **`dashboard.py`** — all dashboard queries + serialization (reads the central `reports` + `report_images`).
- **`form_report.py`** — LIFF form insert + image lookup.
- **`line.py`** — LINE builders (`reply_text`, `reply_messages`, คู่มือ Flex) + `persist_message_image` (CDN → storage).
- **`lookups.py`** — seed data: `COMMUNITIES`, `CATEGORIES` (source of truth for the seeded tables).

### `app/database/`
`__init__.py` — URL normalisation (`postgresql+asyncpg://`, SSL for hosted), `engine`, `SessionLocal`, `get_db`, `Base`. `database_manager.py` — `get_session()` for service code outside a request.

### `app/utils/`
`auth.py` (JWT decode; `get_current_user`/`get_current_admin`), `liff_auth.py` (LIFF access-token verify), `storage.py` (blob/image save-read seam — the S3 swap point).

### `alembic/`
`0001_v2_reports_schema` (central tables + GiST index), `0002_drop_legacy` (V1 tables dropped). Run `alembic upgrade head` before starting the app on a fresh DB.

---

## Changing the AI behaviour

- **Persona / report goal:** `NONG_MUEANG_SYSTEM_PROMPT` (normal chat) / `NONG_MUEANG_BROADCAST_PROMPT` (post-alert) in `app/services/ai_tool.py`.
- **Extraction fields:** `RECORD_COMPLAINT` tool spec in `ai_tool.py` (keep `category`/`notes` required; category enum comes from `lookups.CATEGORIES`).
- **Model / provider:** `MODEL` (or client) in `app/services/llm.py` — nothing else imports the SDK.
- **Session TTL / windowing:** `SESSION_TTL` in `session.py`, `HISTORY_WINDOW` in `ai_tool.py`.
- **Broadcast thresholds / messages:** `HEAT_THRESHOLD`, `RAIN_LABELS`, `_MESSAGE_CONFIG` in `weather_broadcast.py` (button texts must stay in sync with `YES_MAP`/`NO_MAP`).

---

## Environment Variables

```env
CHANNEL_SECRET=            # LINE channel secret
CHANNEL_ACCESS_TOKEN=      # LINE channel access token
DATABASE_URL=postgresql://user:pass@host/db
GEMINI_API_KEY=            # Gemini (google-genai) — required for AI replies
REDIS_URL=                 # conversation memory (default redis://localhost:6379/0)
FORECAST_BASE_URL=         # forecast JSON base (default: data-team S3; point at a local
                           # http.server dir to demo with scripts/make_mock_forecast.py)
LIFF_REPORT_ID=            # LIFF app id ของหน้าแจ้งปัญหา (/report)
LIFF_REPORT_URL=           # https://liff.line.me/<LIFF_REPORT_ID>
EDIT_PROFILE_ID=           # LIFF app id ของหน้าข้อมูลส่วนตัว (/userdata)
EDIT_PROFILE_URL=          # https://liff.line.me/<EDIT_PROFILE_ID>
SECRET_KEY=                # JWT signing key for dashboard/broadcast auth (required)
ALGORITHM=HS256            # optional — JWT algorithm (default HS256)
FRONTEND_URL= / FRONTEND_URLS=   # optional — dashboard CORS origin(s)
ENV=production             # optional — hide /docs and /redoc
# AWS (Lambda deploy only): AWS_SECRET_NAME, AWS_REGION
```

Run (needs Redis + Postgres): `alembic upgrade head` once, then `uvicorn app.main:app --reload`
Tests: `pytest` (deps in `requirements.txt`). Note: the hourly broadcast scheduler only lives in a long-running process (uvicorn) — not on Lambda.

---

## Agent skills

- **Issue tracker** — GitHub Issues for `tonkitcstu/ucr-smartcity_chatbot`. See `docs/agents/issue-tracker.md`.
- **Triage labels** — five canonical labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.
- **Domain docs** — one `CONTEXT.md` + `docs/adr/` at the root. See `docs/agents/domain.md`.
