# UCR Smart City — Community Survey Chatbot

A LINE chatbot that crowdsources situational and environmental data from local community residents. Survey responses are stored in a PostgreSQL database with geospatial support. This chatbot is one data-collection component within the larger UCR Smart City platform.

## Concept & Purpose

This project is a LINE chatbot that conducts surveys with local residents in community areas. Users interact through LINE's familiar chat interface — answering questions, sharing their GPS location, and sending photos. Every completed response is saved to the database along with the respondent's location, so the data can be traced back to which community it came from.

Survey questions are defined in JSON configuration files. The engine is a **route-graph state machine**: a survey is a set of *routes* (groups of questions), and each route declares where to go next. An *orchestrator* can branch to different routes based on earlier answers — so follow-up questions adapt to what the user said (e.g. heat-related questions vs. flood-related questions). Adding or reshaping a survey means editing JSON, not the code.

## Tech Stack

- **Platform:** LINE Messaging API (`line-bot-sdk` v3, async)
- **Backend:** FastAPI (async)
- **Database:** PostgreSQL (asyncpg + SQLAlchemy async)
- **Geospatial:** PostGIS (`Geometry(POINT, 4326)`)
- **Validation:** Pydantic v2
- **Dashboard auth:** JWT (`python-jose`)

## Core Features

- **User Onboarding:** Registers LINE users upon first interaction.
- **Route-Graph Survey Engine:** Loads survey definitions from JSON at startup. Supports dynamic branching between routes based on prior answers — no database migrations needed to add or change a survey.
- **Data Collection:** Processes text responses, LINE Location events, and Image messages. Images are proxied on demand from the LINE CDN (not written to disk).
- **State Management:** Tracks each user's survey progress with a per-user database session and a JSONB payload.
- **Data API:** JWT-protected read endpoints (`/api/dashboard/*`) that expose completed reports, stats, and report images. A **separate project** consumes this API (server-to-server) to retrieve the collected data — this service does not ship a dashboard UI.
- **Structure:** Separates webhook routing (`main.py`), message handlers (`handlers/`), and survey business logic (`services/`).

## Project Structure

```text
ucr-smartcity_chatbot/
├── app/
│   ├── data/surveys/     # Survey JSON definitions (route-graph schema)
│   ├── database/         # Async engine, session, URL normalisation
│   ├── handlers/         # LINE message dispatch (message/info/stat/report/chatbot)
│   ├── models/           # SQLAlchemy models (users, sessions, reports)
│   ├── routes/           # JWT-protected dashboard REST API
│   ├── services/         # Survey state machine, routing engine, repository
│   ├── utils/            # survey_loader, auth
│   └── main.py           # FastAPI entry point & /callback webhook
├── tests/                # pytest suite
├── requirements.txt      # Python dependencies
└── .env.example          # Environment variables template
```

## Setup & Installation

### 1. Prerequisites

**LINE Official Account:**
- Create a Provider and a Messaging API Channel on the [LINE Developers Console](https://developers.line.biz/en/).
- Obtain your `Channel Secret` and `Channel Access Token`.
- Configure and upload a Rich Menu to trigger the survey.

**PostgreSQL Database:**
- Install a PostgreSQL server and create a new database.
- **Mandatory:** You must enable the PostGIS extension in your database **BEFORE** running the application for the first time.
  ```sql
  CREATE EXTENSION postgis;
  ```

### 2. Clone the repository
```bash
git clone https://github.com/tonkitcstu/ucr-smartcity_chatbot.git
cd ucr-smartcity_chatbot
```

### 3. Virtual Environment
**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```
**Windows:**
```cmd
python -m venv venv
venv\Scripts\activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Environment Variables
Copy the template file and add your credentials:
```bash
cp .env.example .env
```
Edit `.env`:
```env
CHANNEL_SECRET=your_line_channel_secret
CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
DATABASE_URL=postgresql://user:password@localhost/dbname
LIFF_REPORT_URL=your_liff_url
SECRET_KEY=your_jwt_secret_key        # signs/verifies dashboard JWTs
ALGORITHM=HS256                       # JWT algorithm (default HS256)
FRONTEND_URL=http://localhost:4200    # browser client origin allowed by CORS
ENV=development                       # set to 'production' to hide /docs & /redoc
# RICHMENU_ID=richmenu-....
```
*(Note: The application automatically replaces `postgresql://` with `postgresql+asyncpg://`.)*

### 6. Run the application
**Linux/macOS:**
```bash
uvicorn --reload app.main:app
```
**Windows:**
```cmd
python -m uvicorn app.main:app --reload
```
*(Note: The application automatically creates the database tables upon startup.)*

### 7. Upload the Rich Menu

The Rich Menu is what users tap to trigger the survey and other actions. A script creates it, uploads its image, and sets it as the default menu for everyone who adds the bot.

1. Place the menu image at `app/data/images/rich_menu_v2.jpg` (size **2500 × 843** px).
2. Make sure `CHANNEL_ACCESS_TOKEN` and `LIFF_REPORT_URL` are set in `.env`.
3. Run:
   ```bash
   python scripts/setup_richmenu.py
   ```

The script prints the new menu's id (`✅ ... ได้ ID: richmenu-xxxx`) and sets it as the default for everyone — so you don't need to copy the id anywhere for normal use. (The `RICHMENU_ID` line in `.env` is optional and not read by the app; it's just a handy place to note the id.) To list menus later, call LINE's API: `GET https://api.line.me/v2/bot/richmenu/list` with your channel token.

The four buttons map to: `เริ่มทำแบบสำรวจ` (start survey), `รายงานปัญหา` (report — opens `LIFF_REPORT_URL`), `ข้อมูลโครงการ` (project info), `สรุปผล` (summary). To change the layout or button actions, edit `scripts/setup_richmenu.py`.

## Data API (`/api/dashboard`)

A read-only API that a **separate project** consumes (server-to-server) to retrieve the collected data. This service does not ship a UI of its own. All endpoints require a JWT Bearer token; tokens are issued externally — this service only verifies them with `SECRET_KEY`.

| Endpoint | Description |
|---|---|
| `GET /stats` | Total users / completed / incomplete counts |
| `GET /available-dates` | Distinct dates that have completed reports |
| `GET /reports?date=YYYY-MM-DD` | Completed reports (optionally filtered by date), with `latitude`/`longitude` and an `images` list |
| `GET /reports/{id}` | Single completed report detail |
| `GET /image/{image_id}` | Streams a report image (proxied from the LINE CDN as `image/jpeg`) |

**Report images.** A report's photos live inside its `payload`; the API surfaces them as a flat `images` list so a consumer reads them at one stable place regardless of survey shape. A report may carry zero, one, or several images:

```json
"images": [
  { "question_id": "q_photo", "image_id": "617445...", "image_url": "/api/dashboard/image/617445..." }
]
```

Fetch the bytes from `image_url` (it requires the same JWT). Images are proxied live from the LINE CDN and can expire — a consumer that needs them long-term should cache its own copy. (Durable storage on S3 is planned — see `docs/adr/0005`.)

## Running Tests

```bash
pytest
```

## Webhook Configuration (Local Development)

LINE requires an HTTPS URL for webhooks. For local testing, use a tunneling service like [ngrok](https://ngrok.com/):
```bash
ngrok http 8000
```
Copy the HTTPS URL provided by ngrok and set your LINE Webhook URL to:
`https://<your-ngrok-url>/callback`
