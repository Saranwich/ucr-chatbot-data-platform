# UCR Chatbot Data Platform

A data collection platform built on the LINE Messaging API, designed for daily community data surveys. This chatbot engages with local residents to gather hyper-local environmental and infrastructure data to assist in the redesign and mapping of community areas via the GAMA platform.

## Concept & Purpose

This project is a LINE Chatbot built to conduct daily surveys with local people. The primary goal is to collect valuable, localized data to help in redesigning community maps and planning the locations of new facilities.

The bot collects various types of data from users, including:
- Temperature & Humidity
- Sunlight levels
- Sound/Noise levels
- Trash and waste reporting (via Image IDs)
- Location data (Coordinates) for mapping facilities and issues

By crowdsourcing this data directly from the community via a familiar chat interface, we can build a comprehensive and dynamic map of the area's current state and needs.

## Tech Stack

- **Platform:** LINE Messaging API
- **Backend:** FastAPI
- **Database:** PostgreSQL (asyncpg)
- **Geospatial:** PostGIS

## Core Features

- **User Onboarding:** Registers LINE users upon first interaction.
- **Survey Engine:** Loads survey sequences from JSON files (e.g., `devtest_message_01.json`) without database migrations.
- **Data Collection:** Processes text responses, LINE Location events, and Image messages.
- **State Management:** Tracks survey progress using temporary database sessions and JSONB payloads.
- **Structure:** Separates routing (`main.py`), controllers (`handlers/`), and business logic (`services/`).

## Project Structure

```text
ucr-chatbot-data-platform/
├── app/
│   ├── data/             # Survey JSON files and static assets
│   ├── database/         # Database connection and session management
│   ├── handlers/         # LINE message processing logic
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Core business logic & State Machine
│   ├── utils/            # Utilities (survey_loader, config)
│   └── main.py           # FastAPI entry point & Webhook callback
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
git clone <repository-url>
cd ucr-chatbot-data-platform
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
# RICHMENU_ID=richmenu-....
```
*(Note: The application automatically replaces `postgresql://` with `postgresql+asyncpg://`)*

### 6. Run the application
```bash
uvicorn app.main:app --reload
```
*(Note: The application automatically creates the `users`, `survey_sessions`, and `completed_reports` tables upon startup.)*

## Webhook Configuration (Local Development)

LINE requires an HTTPS URL for webhooks. For local testing, use a tunneling service like [ngrok](https://ngrok.com/):
```bash
ngrok http 8000
```
Copy the HTTPS URL provided by ngrok and set your LINE Webhook URL to:
`https://<your-ngrok-url>/callback`