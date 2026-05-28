# UCR Smartcity Chatbot — Project Context

## Purpose

A LINE Messaging API chatbot that crowdsources hyper-local environmental and infrastructure data from community residents. Survey responses (temperature, humidity, noise, trash, GPS location, photos) feed into the GAMA urban planning platform to assist in redesigning community maps and facility placement.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI (async) |
| Database | PostgreSQL + PostGIS (geospatial) |
| DB driver/ORM | asyncpg + SQLAlchemy async |
| Validation | Pydantic v2 |
| LINE SDK | linebot v3 (AsyncMessagingApi) |
| Auth (dashboard) | JWT via `python-jose` |
| Tunnel (dev) | ngrok → `/callback` |

---

## Architecture Overview

```
LINE Webhook POST /callback
        │
   main.py (event router)
        │
   message_handler.py  ← top-level dispatcher
   ├── info_handler.py     ("ข้อมูลโครงการ" → static text)
   ├── stat_handler.py     ("สรุปผล" → placeholder text)
   ├── report_handler.py   ("รายงานปัญหา" → LIFF redirect placeholder)
   └── chatbot_handler.py  (survey trigger + in-progress answer routing)
            │
      survey_service.py   ← state machine (start / step / complete)
            │
      survey_loader.py    ← in-memory survey JSON cache (SurveyManager)
            │
      PostgreSQL          ← users / survey_sessions / completed_reports / incomplete_reports

REST API  GET /api/dashboard/*
        │
   routes/dashboard.py   ← JWT-protected admin dashboard endpoints
        │
   utils/auth.py         ← OAuth2 Bearer / JWT decode
```

---

## Module Reference

### `app/main.py`
- FastAPI entrypoint with `lifespan` startup hook.
- Startup: enables PostGIS extension, runs `Base.metadata.create_all`, loads all survey JSONs from `app/data/surveys/`.
- `POST /callback`: validates LINE webhook signature, dispatches `MessageEvent` by type (Text / Location / Image) to `message_handler`.
- `GET /api/health`: rate-limited (1 req/5s per IP) health check.
- `GET /uploads/*`: serves static uploaded files (legacy; images now proxied on-demand).
- Swagger/ReDoc disabled when `ENV=production`.

### `app/config.py`
- Loads env vars: `CHANNEL_SECRET`, `CHANNEL_ACCESS_TOKEN`, `DATABASE_URL`, `LIFF_REPORT_URL`.
- `SURVEY_TRIGGER_MAP`: dict mapping Thai keyword → survey version key (e.g. `"เริ่มทำแบบสำรวจ" → "devtest_message_01"`). **Add new surveys here.**
- Static reply text constants: `PROJECT_INFO_TEXT`, `REPORT_DEVELOPMENT_TEXT`, `SUMMARY_PLACEHOLDER_TEXT`.

### `app/handlers/message_handler.py`
Top-level router. Matches exact text strings to dedicated handlers; falls through to `chatbot_handler` for everything else.

### `app/handlers/chatbot_handler.py`
- `handle_chatbot_chat`: checks `SURVEY_TRIGGER_MAP`; if matched, starts new session; otherwise forwards to `process_survey_answer` as an in-progress answer.
- `handle_chatbot_location` / `handle_chatbot_image`: wrap event data and call `process_survey_answer`.

### `app/handlers/info_handler.py`, `stat_handler.py`, `report_handler.py`
Simple one-shot reply handlers triggered by Rich Menu buttons. No DB access.

### `app/services/survey_service.py`
Core state machine.
- `start_survey_session`: upserts `User`, deletes any existing `SurveySession`, creates a new one at `step=0`, sends first question.
- `process_survey_answer`: loads active session → saves answer into `payload` JSONB keyed by question ID → advances `current_step` → sends next question **or** finalises into `CompletedReport` and deletes session.
- `send_question`: builds `TextMessage` with `QuickReply` buttons (MessageAction / LocationAction / CameraAction).
- Image answers: stores `image_id` + proxy URL (`/api/dashboard/image/{id}`) in payload; images are **not** saved to disk.

### `app/utils/survey_loader.py`
`SurveyManager` singleton. Scans `app/data/surveys/*.json` at startup, validates each file via Pydantic (`Survey → SurveyQuestion → SurveyOption`), stores in `_surveys` dict keyed by `version` string. `get_question_by_step(version, step_index)` is the primary access method.

### `app/models/__init__.py`
Four SQLAlchemy models (all timestamps default to Bangkok UTC+7):

| Model | Table | Key fields |
|---|---|---|
| `User` | `users` | `lineuser_id` (PK) |
| `SurveySession` | `survey_sessions` | `lineuser_id` (PK), `survey_version`, `current_step`, `payload` (JSONB) |
| `CompletedReport` | `completed_reports` | `report_id`, `lineuser_id`, `survey_version`, `payload` (JSONB), `location_data` (PostGIS POINT SRID 4326) |
| `IncompleteReport` | `incomplete_reports` | same + `drop_off_step`, `status` |

### `app/routes/dashboard.py`
JWT-protected REST API for the admin frontend (Angular, default `localhost:4200`).

| Endpoint | Description |
|---|---|
| `GET /api/dashboard/stats` | Total users / completed / incomplete counts |
| `GET /api/dashboard/available-dates` | Distinct dates with completed reports |
| `GET /api/dashboard/reports` | All completed reports (filterable by `?date=YYYY-MM-DD`), lat/lon extracted from PostGIS via `ST_X`/`ST_Y` |
| `GET /api/dashboard/reports/{id}` | Single report detail |
| `GET /api/dashboard/image/{image_id}` | On-demand proxy: fetches image from LINE CDN and streams back as `image/jpeg` |

### `app/utils/auth.py`
Decodes JWT Bearer token. Returns `{"username": ..., "role": ...}`. `get_current_admin` additionally asserts `role == "admin"`. Auth tokens are issued externally (no login endpoint in this service).

### `app/database/__init__.py`
- Normalises `DATABASE_URL` to `postgresql+asyncpg://`.
- Strips `sslmode=` param from URL; adds asyncpg-compatible SSL context for hosted platforms (Render/Heroku).

### `app/schemas.py`
Pydantic response schemas: `DashboardStats`, `CompletedReportSchema` (with flattened `latitude`/`longitude`).

---

## Survey Flow (end-to-end)

1. User taps Rich Menu button → LINE sends `"เริ่มทำแบบสำรวจ"` text event.
2. `message_handler` → `chatbot_handler` → `start_survey_session` → new `SurveySession(step=0)`.
3. Bot replies with Q1 (text + Quick Reply buttons from JSON definition).
4. User picks answer → `process_survey_answer` saves to `payload[question.id]`, increments step, sends Q(n+1).
5. On final step: `CompletedReport` created (with PostGIS point from `q1_location`), `SurveySession` deleted, thank-you message sent.

---

## Adding a New Survey

1. Create `app/data/surveys/<name>.json` with the schema `{version, questions:[{id, type, text, options:[{label, action_type, value?}]}]}`.
2. Add a trigger keyword in `config.py` → `SURVEY_TRIGGER_MAP`: `"<keyword>": "<version>"`.
3. Restart the server — the new JSON is loaded automatically at startup.

---

## Environment Variables

```env
CHANNEL_SECRET=           # LINE channel secret
CHANNEL_ACCESS_TOKEN=     # LINE channel access token
DATABASE_URL=postgresql://user:pass@host/db
LIFF_REPORT_URL=          # LIFF URL for report web app (feature in progress)
SECRET_KEY=               # JWT signing key for dashboard auth
ALGORITHM=HS256           # JWT algorithm (default HS256)
FRONTEND_URL=             # Angular dashboard origin for CORS (default http://localhost:4200)
ENV=production            # Set to 'production' to hide /docs and /redoc
```

Run: `uvicorn app.main:app --reload`

---

## Active Branch Context

- Current branch: `feature-liff` — preparing LIFF URL integration (`LIFF_REPORT_URL` env var added, report button placeholder in `report_handler.py`).

---

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `tonkitcstu/ucr-smartcity_chatbot`. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five canonical default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo — one `CONTEXT.md` + `docs/adr/` at the root. See `docs/agents/domain.md`.
