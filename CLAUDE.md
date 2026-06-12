# UCR Smartcity Chatbot — Project Context

## Purpose

A LINE Messaging API chatbot that crowdsources hyper-local environmental and infrastructure data from community residents. Survey responses (temperature, humidity, noise, trash, GPS location, photos) are collected and surfaced through a JWT-protected admin dashboard with a map view, to assist in redesigning community maps and facility placement.

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
   main.py (event router: MessageEvent / FollowEvent)
        │
   ├── follow_handler.py    (add เพื่อน → upsert User + Flex ชวนกรอก profile)
   └── message_handler.py   ← top-level dispatcher
       ├── info_handler.py     ("ข้อมูลโครงการ" → static text)
       ├── stat_handler.py     ("สรุปผล" → placeholder text)
       ├── report_handler.py   ("รายงานปัญหา" → text fallback; ปุ่มจริงเป็น URI เปิด LIFF)
       ├── manual_handler.py   ("คู่มือการใช้งาน" → Flex)
       └── chatbot_handler.py  (survey trigger + answer routing; persists photo answers)
                │
          survey_service.py   ← state machine (start / step / complete)
          ├── routing.py            ← pure route-graph engine (next/go-back/multi-select)
          ├── survey_repository.py  ← DB access
          ├── survey_messages.py    ← LINE message building
          └── survey_loader.py      ← in-memory survey JSON cache (SurveyManager)
                │
          PostgreSQL  ← users / survey_sessions / completed_reports / incomplete_reports / form_reports

LIFF pages (เสิร์ฟจาก FastAPI origin เดียวกัน, auth ด้วย LIFF access token)
   ├── routes/report.py    GET /report + POST /api/form-reports   (แจ้งปัญหา)
   └── routes/userdata.py  GET /userdata + GET/PUT /api/userdata/profile (ข้อมูลส่วนตัว)

REST API  GET /api/dashboard/*
        │
   routes/dashboard.py   ← JWT-protected admin dashboard endpoints
        │
   utils/auth.py         ← OAuth2 Bearer / JWT decode

Image store: utils/storage.py — ทุกโมดูลเซฟ/อ่านรูปผ่าน helper นี้ (local uploads/ ตาม
storage key เช่น survey/<image_id>.jpg, reports/<uuid>.jpg; จุดเสียบ S3 ในอนาคต)
```

---

## Module Reference

### `app/main.py`
- FastAPI entrypoint with `lifespan` startup hook.
- Startup: enables PostGIS extension, runs `Base.metadata.create_all`, loads all survey JSONs from `app/data/surveys/`.
- `POST /callback`: validates LINE webhook signature, dispatches `MessageEvent` by type (Text / Location / Image) to `message_handler` and `FollowEvent` to `follow_handler`.
- Startup also runs an idempotent `ALTER TABLE users ADD COLUMN IF NOT EXISTS ...` for the profile columns (create_all never alters existing tables).
- `GET /api/health`: rate-limited (1 req/5s per IP) health check.
- `GET /uploads/*`: serves static uploaded files (legacy; images now proxied on-demand).
- Swagger/ReDoc disabled when `ENV=production`.

### `app/config.py`
- Loads env vars: `CHANNEL_SECRET`, `CHANNEL_ACCESS_TOKEN`, `DATABASE_URL`, `LIFF_REPORT_ID`/`LIFF_REPORT_URL`, `EDIT_PROFILE_ID`/`EDIT_PROFILE_URL`.
- `SURVEY_TRIGGER_MAP`: dict mapping Thai keyword → survey version key (e.g. `"เริ่มทำแบบสำรวจ" → "socratic_community_report_v3"`). **Add new surveys here.**
- Static reply text constants: `PROJECT_INFO_TEXT`, `REPORT_DEVELOPMENT_TEXT`, `SUMMARY_PLACEHOLDER_TEXT`, `MANUAL_TEXT`, `WELCOME_TEXT`, `WELCOME_BACK_TEXT`.

### `app/handlers/message_handler.py`
Top-level router. Matches exact text strings to dedicated handlers; falls through to `chatbot_handler` for everything else.

### `app/handlers/chatbot_handler.py`
- `handle_chatbot_chat`: checks `SURVEY_TRIGGER_MAP`; if matched, starts new session; otherwise forwards to `process_survey_answer` as an in-progress answer.
- `handle_chatbot_location` / `handle_chatbot_image`: wrap event data and call `process_survey_answer`.
- Image answers: fetches bytes from LINE CDN immediately and saves via `utils/storage` (key `survey/<image_id>.jpg`); on failure degrades to `image_id` only (CDN proxy still works until expiry).

### `app/handlers/follow_handler.py`
`FollowEvent` (add เพื่อน / unblock): upserts the `User` row, then greets — users without a profile get a Flex invite that opens the Userdata LIFF; profiled re-followers get a plain welcome-back.

### `app/routes/userdata.py` + `app/static/userdata_form.html`
Userdata LIFF (แก้ไขข้อมูลส่วนตัว). Profile = `nickname`, `age_range`, `gender`, `community` — canonical columns on `users`, edited **only** here (surveys no longer ask). `GET/PUT /api/userdata/profile` require a verified LIFF access token (no anonymous mode, unlike the report form). Saving sets `has_completed_profile=1`.

### `app/utils/storage.py`
Central image store. `save_image(key, bytes)` / `local_file(key)`; keys like `survey/<image_id>.jpg`, `reports/<uuid>.<ext>` under `uploads/`. The single seam where an S3 backend will plug in later — no module writes image files on its own.

### `app/handlers/info_handler.py`, `stat_handler.py`, `report_handler.py`
Simple one-shot reply handlers triggered by Rich Menu buttons. No DB access.

### `app/services/survey_service.py`
Core state machine.
- `start_survey_session`: upserts `User`, deletes any existing `SurveySession`, creates a new one at `step=0`, sends first question.
- `process_survey_answer`: loads active session → saves answer into `payload` JSONB keyed by question ID → advances `current_step` → sends next question **or** finalises into `CompletedReport` and deletes session.
- `send_question`: builds `TextMessage` with `QuickReply` buttons (MessageAction / LocationAction / CameraAction).
- Image answers arrive as `{image_id, storage_key?}` (persisted upstream by `chatbot_handler`); the proxy URL `/api/dashboard/image/{id}` is added into the payload.
- On completion: thank-you reply, plus a Flex invite to fill the profile when `has_completed_profile` is still 0 (`services/profile_messages.py`).

### `app/utils/survey_loader.py`
`SurveyManager` singleton. Scans `app/data/surveys/*.json` at startup, validates each file via Pydantic (`Survey → SurveyQuestion → SurveyOption`), stores in `_surveys` dict keyed by `version` string. `get_question_by_step(version, step_index)` is the primary access method.

### `app/models/__init__.py`
Four SQLAlchemy models (all timestamps default to Bangkok UTC+7):

| Model | Table | Key fields |
|---|---|---|
| `User` | `users` | `lineuser_id` (PK), `has_completed_profile`, profile: `nickname` / `age_range` / `gender` / `community` |
| `SurveySession` | `survey_sessions` | `lineuser_id` (PK), `survey_version`, `current_route_id`, `current_step`, `route_history`, `payload` (JSONB) |
| `CompletedReport` | `completed_reports` | `report_id`, `lineuser_id`, `survey_version`, `payload` (JSONB), `location_data` (PostGIS POINT SRID 4326) |
| `IncompleteReport` | `incomplete_reports` | same + `drop_off_route_id`, `drop_off_step`, `status` |
| `FormReport` | `form_reports` | แจ้งปัญหาจาก LIFF form: `description`, `category`, `location_data`, `image_path` (storage key), nullable `lineuser_id` |

### `app/routes/dashboard.py`
JWT-protected REST API for the admin frontend (Angular, default `localhost:4200`).

| Endpoint | Description |
|---|---|
| `GET /api/dashboard/stats` | Total users / completed / incomplete counts |
| `GET /api/dashboard/available-dates` | Distinct dates with completed reports |
| `GET /api/dashboard/reports` | All completed reports (filterable by `?date=YYYY-MM-DD`), lat/lon extracted from PostGIS via `ST_X`/`ST_Y` |
| `GET /api/dashboard/reports/{id}` | Single report detail |
| `GET /api/dashboard/image/{image_id}` | Store-first: serves `uploads/survey/<image_id>.jpg` if persisted; otherwise falls back to proxying LINE CDN (old reports, until expiry) |

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
5. On final step: `CompletedReport` created (with PostGIS point from the first location answer), `SurveySession` deleted, thank-you message sent (+ Flex invite to fill profile when the user has none).

Profile is **not** part of any survey — it is filled/edited only in the Userdata LIFF, and users without a profile can still complete surveys (their demographic fields are simply empty until they fill the LIFF).

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
LIFF_REPORT_ID=           # LIFF app id ของหน้าแจ้งปัญหา (/report) — LINE Login channel, provider เดียวกับบอท
LIFF_REPORT_URL=          # https://liff.line.me/<LIFF_REPORT_ID> — ใช้ในปุ่ม rich menu
EDIT_PROFILE_ID=          # LIFF app id ของหน้าข้อมูลส่วนตัว (/userdata) — channel เดียวกัน คนละ app
EDIT_PROFILE_URL=         # https://liff.line.me/<EDIT_PROFILE_ID> — ใช้ในปุ่ม rich menu
SECRET_KEY=               # JWT signing key for dashboard auth (required — app refuses to start without it)
ALGORITHM=HS256           # optional — JWT algorithm (default HS256)
FRONTEND_URL=             # optional — Angular dashboard origin for CORS (default http://localhost:4200)
ENV=production            # optional — set to 'production' to hide /docs and /redoc
```

Run: `uvicorn app.main:app --reload`

---

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `tonkitcstu/ucr-smartcity_chatbot`. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five canonical default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo — one `CONTEXT.md` + `docs/adr/` at the root. See `docs/agents/domain.md`.
