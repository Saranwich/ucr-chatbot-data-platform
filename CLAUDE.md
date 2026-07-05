# UCR Smartcity Chatbot — Project Context

## Purpose

A LINE Messaging API chatbot that crowdsources hyper-local environmental and infrastructure problems from community residents. Instead of a fixed survey, an **AI assistant ("น้องเมือง")** chats naturally in Thai, gathers the details of a problem, and extracts a structured report. Reports are surfaced through a JWT-protected admin dashboard with a map view, to assist in redesigning community maps and facility placement.

> **V2 (AI) rebuild.** The old rule-based survey engine has been removed; the bot is now LLM-driven (Gemini) with conversation memory. Historical survey data is still readable by the dashboard (kept dormant — see *Dormant V1 read-side*).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI (async) |
| LLM | Google **Gemini** (`gemini-3.1-flash-lite`) via `google-genai`, function calling |
| Conversation memory | **Redis** (per-user transcript, TTL) |
| Database | PostgreSQL + PostGIS (geospatial) |
| DB driver/ORM | asyncpg + SQLAlchemy async |
| Validation | Pydantic v2 |
| LINE SDK | linebot v3 (AsyncMessagingApi) |
| Auth (dashboard) | JWT via `python-jose` |
| Deploy adapter | Mangum (AWS Lambda ASGI) |
| Tunnel (dev) | ngrok → `/callback` |

---

## Architecture — `main → routes → handlers → services → models`

`main.py` only **binds** (lifespan + CORS + routers + exception handler + Mangum). All logic lives below it.

```
LINE Webhook POST /callback
        │
   routes/line.py         ← parse + signature check + per-event rescue
        │
   ├── handlers/follow_handler.py     (add เพื่อน → upsert User + welcome)
   ├── handlers/broadcast_flow_handler.py  (Pim: weather-alert reply flow → BroadcastReport)
   └── handlers/message_handler.py    ← text dispatcher
         ├── rich-menu buttons → static text / คู่มือ Flex (services/line.py)
         ├── broadcast confirm/decline (YES_MAP / NO_MAP)
         └── free text → AI CORE ↓
                 │
           services/ai_tool.build_question(user_id, text)
             ├── services/session.py   ← Redis transcript (load last ~10 / append; 30-min TTL)
             ├── services/llm.py        ← Gemini seam (chat + record_complaint tool). ONLY file importing the SDK
             └── services/report.py     ← save extracted report (CSV stand-in → Postgres later)

LIFF pages (same FastAPI origin, LIFF access-token auth)
   ├── routes/report.py    GET /report + POST /api/form-reports (+ image)  → services/form_report.py
   └── routes/userdata.py  GET /userdata + GET/PUT /api/userdata/profile   → services/user.py

Admin REST API
   routes/dashboard.py  GET /api/dashboard/*  (JWT)  → services/dashboard.py
   routes/system.py     GET /api/health (DB reachability)
   routes/viewer.py     GET /viewer (dev-only data viewer)

Image store: utils/storage.py — every module saves/reads images through this helper
(local uploads/ by key, e.g. reports/<uuid>.jpg, broadcast/<id>.jpg; S3 seam later).
```

---

## The AI conversation (end-to-end)

1. User sends free text on LINE → `/callback` (`routes/line.py`) → `message_handler` → `services/ai_tool.build_question(user_id, text)`.
2. `ai_tool` appends the user turn to the **Redis** session, loads the last ~10 messages, and calls `llm.chat(history, system=NONG_MUEANG_SYSTEM_PROMPT, tools=[RECORD_COMPLAINT])`.
3. Gemini either replies with a follow-up question **or** calls the `record_complaint` tool when it has enough. On a tool call, `ai_tool` extracts the report and `services/report.save()` persists it; the session **stays alive** so one chat can hold several reports, and the model thanks the user naturally.
4. The bot reply is appended to the session. Sessions auto-expire after 30 min (Redis TTL).

**MVP report schema (the AI's extraction target):** `category` + `notes` **required**; `location` + `severity` optional/skippable.

**Persistence is a CSV stand-in for now** (`reports.csv`, gitignored). `services/report.save()` is the single seam that swaps to a Postgres insert (via `database_manager`) once the report table schema is agreed.

---

## Module Reference

### `app/main.py`
Binds only: `lifespan` (PostGIS + `Base.metadata.create_all` + idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for profile/broadcast columns; also loads V1 survey JSON for the dashboard read-side), CORS, `include_router(...)`, global exception handler, `handler = Mangum(app)`. Swagger/ReDoc off when `ENV=production`.

### `app/config.py`
Env vars (`CHANNEL_SECRET`, `CHANNEL_ACCESS_TOKEN`, `DATABASE_URL`, `LIFF_REPORT_ID/URL`, `EDIT_PROFILE_ID/URL`) + static reply text (`PROJECT_INFO_TEXT`, `SUMMARY_PLACEHOLDER_TEXT`, `REPORT_DEVELOPMENT_TEXT`, `MANUAL_TEXT`, `WELCOME_TEXT`, `WELCOME_BACK_TEXT`, `SYSTEM_ERROR_TEXT`). `config_loader.py` loads `.env` and (in Lambda) AWS Secrets Manager.

### `app/routes/` (thin endpoints, no logic)
| File | Endpoints |
|---|---|
| `line.py` | `POST /callback` — webhook parse + `handle_event_safely` dispatch to handlers |
| `dashboard.py` | `GET /api/dashboard/*` (JWT) — delegates to `services/dashboard.py` |
| `report.py` | `GET /report`, `POST /api/form-reports`, `GET /api/form-reports/{id}/image` |
| `userdata.py` | `GET /userdata`, `GET/PUT /api/userdata/profile` (owns `ProfileIn`, `_require_lineuser_id`) |
| `viewer.py` | `GET /viewer` (dev-only page) |
| `system.py` | `GET /api/health` — verifies DB reachability (`SELECT 1`), 503 when down |

### `app/handlers/` (per-surface dispatch)
- **`message_handler.py`** — routes text: `RICH_MENU_REPLIES` map (info/summary/report-fallback) + คู่มือ Flex, broadcast `YES_MAP`/`NO_MAP`, else `ai_tool.build_question`. Non-broadcast location/image are currently ignored (AI image/location handling is future work).
- **`follow_handler.py`** — `FollowEvent`: upsert `User`, reply `WELCOME_TEXT` / `WELCOME_BACK_TEXT` (no profile-invite in V2).
- **`broadcast_flow_handler.py`** — **Pim's** weather-alert reply flow (`awaiting_note → awaiting_location → awaiting_photo → done`), persists `BroadcastReport`. Owns its own message builders + `YES_MAP`/`NO_MAP`.

### `app/services/` (one file per domain)
- **`ai_tool.py`** — AI conversation core. `NONG_MUEANG_SYSTEM_PROMPT` (persona + report goal), `RECORD_COMPLAINT` tool spec (4 fields), `build_question(user_id, text)` = Redis memory + `llm.chat` + `report.save`.
- **`llm.py`** — the **only** file importing the Gemini SDK. `chat(messages, system, tools, tool_handler)` runs a turn with function-calling (one tool-result round-trip). `MODEL = "gemini-3.1-flash-lite"`; lazy client. Swap providers/models here alone.
- **`session.py`** — Redis transcript store. `load(user_id)` / `append(user_id, role, content)`; key `chat:<user_id>`, `SESSION_TTL = 1800`s.
- **`report.py`** — `save(lineuser_id, report)` appends a row to `reports.csv`. **Swap seam** for Postgres.
- **`dashboard.py`** — all dashboard queries + serialization (moved out of the route).
- **`form_report.py`** — `FormReport` insert + image lookup (`point_wkt` lives here).
- **`user.py`** — `get_or_create_user`, `get_profile`, `save_profile`.
- **`line.py`** — reusable LINE builders: `reply_text`, `reply_messages`, `build_manual_messages` (คู่มือ Flex).
- **`weather.py`** — stub; Pim's broadcast push/trigger home.

### `app/database/`
- `__init__.py` — normalises `DATABASE_URL` to `postgresql+asyncpg://`, strips `sslmode`, adds SSL for hosted platforms; exposes `engine`, `SessionLocal`, `get_db`, `Base`.
- `database_manager.py` — thin gateway: `get_session()` for service code outside a request (routes still use the `get_db` dependency).

### `app/models/` (per file, re-exported from `__init__`; timestamps default Bangkok UTC+7)
| Model | Table | Note |
|---|---|---|
| `User` | `users` | `lineuser_id` (PK), `has_completed_profile`, profile `nickname`/`age_range`/`gender`/`community` |
| `FormReport` | `form_reports` | LIFF แจ้งปัญหา: `description`, `category`, `location_data` (PostGIS), `image_path` |
| `BroadcastReport` | `broadcast_reports` | Pim: `alert_type` (flood/heat/both), `confirmed`, `status`, `note`, geo, image |
| `CompletedReport` / `IncompleteReport` | `completed_reports` / `incomplete_reports` | **Dormant V1 survey data** — dashboard read-side only; no new rows under V2 |

### `app/utils/`
`auth.py` (JWT decode; `get_current_user` / `get_current_admin`), `liff_auth.py` (LIFF access-token verify → `lineuser_id`), `storage.py` (image save/read seam). `survey_loader.py` = **dormant** V1 survey JSON cache, still imported by the dashboard to label old incomplete-report drop-offs.

### `app/routes/dashboard.py` → `services/dashboard.py`
| Endpoint | Description |
|---|---|
| `GET /stats` | user / completed / incomplete counts + breakdowns |
| `GET /available-dates` | distinct dates with completed reports |
| `GET /reports`, `/reports/{id}` | completed survey reports (dormant data), lat/lon via `ST_X`/`ST_Y` |
| `GET /incomplete-reports` | dormant survey drop-offs |
| `GET /form-reports` | LIFF แจ้งปัญหา reports |
| `GET /broadcast-reports` | weather-broadcast reports (both = 2 map pins) |
| `GET /image/{id}`, `/broadcast-image/{id}` | store-first image serving (fallback to LINE CDN proxy) |

---

## Dormant V1 read-side (kept on purpose)

`survey_loader.py`, `app/data/surveys/*.json`, `CompletedReport`/`IncompleteReport`, and the dashboard `/reports` + `/incomplete-reports` endpoints remain so the dashboard can still display **historical** survey data. No new rows are written under V2. Deleting them is deferred pending the dashboard team + the V2 dashboard contract (issue #81).

---

## Changing the AI behaviour

- **Persona / report goal:** edit `NONG_MUEANG_SYSTEM_PROMPT` in `app/services/ai_tool.py`.
- **Extraction fields:** edit the `RECORD_COMPLAINT` tool spec in `ai_tool.py` (keep `category`/`notes` required).
- **Model / provider:** change `MODEL` (or the client) in `app/services/llm.py` — nothing else imports the SDK.
- **Session TTL / windowing:** `SESSION_TTL` in `session.py`, `HISTORY_WINDOW` in `ai_tool.py`.

---

## Environment Variables

```env
CHANNEL_SECRET=            # LINE channel secret
CHANNEL_ACCESS_TOKEN=      # LINE channel access token
DATABASE_URL=postgresql://user:pass@host/db
GEMINI_API_KEY=            # Gemini (google-genai) — required for AI replies
REDIS_URL=                 # conversation memory (default redis://localhost:6379/0)
LIFF_REPORT_ID=            # LIFF app id ของหน้าแจ้งปัญหา (/report)
LIFF_REPORT_URL=           # https://liff.line.me/<LIFF_REPORT_ID>
EDIT_PROFILE_ID=           # LIFF app id ของหน้าข้อมูลส่วนตัว (/userdata)
EDIT_PROFILE_URL=          # https://liff.line.me/<EDIT_PROFILE_ID>
SECRET_KEY=                # JWT signing key for dashboard auth (required)
ALGORITHM=HS256            # optional — JWT algorithm (default HS256)
FRONTEND_URL= / FRONTEND_URLS=   # optional — dashboard CORS origin(s)
ENV=production             # optional — hide /docs and /redoc
# AWS (Lambda deploy only): AWS_SECRET_NAME, AWS_REGION
```

Run (needs a running Redis + Postgres): `uvicorn app.main:app --reload`
Tests: `pytest` (deps in `requirements.txt`).

---

## Agent skills

- **Issue tracker** — GitHub Issues for `tonkitcstu/ucr-smartcity_chatbot`. See `docs/agents/issue-tracker.md`.
- **Triage labels** — five canonical labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.
- **Domain docs** — one `CONTEXT.md` + `docs/adr/` at the root. See `docs/agents/domain.md`.
