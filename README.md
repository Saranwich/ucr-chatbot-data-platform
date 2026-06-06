# UCR Smart City — Community Survey Chatbot

A LINE chatbot that crowdsources situational and environmental data from local community residents. Survey responses are stored in a PostgreSQL database with geospatial support. This chatbot is one data-collection component within the larger UCR Smart City platform.

## Concept & Purpose

This project is a LINE chatbot that conducts surveys with local residents in community areas. Users interact through LINE's familiar chat interface — answering questions, sharing their GPS location, and sending photos. Every completed response is saved to the database along with the respondent's location, so the data can be traced back to which community it came from.

The exact survey questions depend on the situation being measured and are managed through JSON configuration files. The survey engine currently uses static JSON files to define the question flow. Dynamic branching — where follow-up questions change based on earlier answers — is under active development.

## Tech Stack

- **Platform:** LINE Messaging API
- **Backend:** FastAPI
- **Database:** PostgreSQL (asyncpg)
- **Geospatial:** PostGIS

## Core Features

- **User Onboarding:** Registers LINE users upon first interaction.
- **Survey Engine:** Loads survey sequences from JSON files at startup — no database migrations needed to add new surveys.
- **Data Collection:** Processes text responses, LINE Location events, and Image messages.
- **State Management:** Tracks each user's survey progress using temporary database sessions and JSONB payloads.
- **Structure:** Separates routing (`main.py`), controllers (`handlers/`), and business logic (`services/`).

## Project Structure

```text
ucr-smartcity_chatbot/
├── app/
│   ├── data/             # Survey JSON files and static assets
│   ├── database/         # Database connection and session management
│   ├── handlers/         # LINE message processing logic
│   ├── models/           # SQLAlchemy models
│   ├── routes/           # REST API routes (dashboard)
│   ├── services/         # Core business logic & State Machine
│   ├── utils/            # Utilities (survey_loader, auth)
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
SECRET_KEY=your_jwt_secret_key
# RICHMENU_ID=richmenu-....
```
*(Note: The application automatically replaces `postgresql://` with `postgresql+asyncpg://`)*

### 6. Run the application
```bash
uvicorn app.main:app --reload
```
*(Note: The application automatically creates the database tables upon startup.)*

## Webhook Configuration (Local Development)

LINE requires an HTTPS URL for webhooks. For local testing, use a tunneling service like [ngrok](https://ngrok.com/):
```bash
ngrok http 8000
```
Copy the HTTPS URL provided by ngrok and set your LINE Webhook URL to:
`https://<your-ngrok-url>/callback`
