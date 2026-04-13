# UCR Chatbot Data Platform

A data collection platform built on the LINE Messaging API, designed for daily community data surveys. This chatbot engages with local residents to gather hyper-local environmental and infrastructure data to assist in the redesign and mapping of community areas.

## Concept & Purpose

This project is a LINE Chatbot built to conduct daily surveys with local people. The primary goal is to collect valuable, localized data to help in redesigning community maps and planning the locations of new facilities.

The bot collects various types of data from users, including:
- Temperature & Humidity
- Sunlight levels
- Sound/Noise levels
- Trash and waste reporting
- Location data (Coordinates) for mapping facilities and issues

By crowdsourcing this data directly from the community via a familiar chat interface, we can build a comprehensive and dynamic map of the area's current state and needs.

## Tech Stack

- Platform: LINE Messaging API (Chatbot Interface)
- Backend / API: FastAPI
- Database: PostgreSQL (via SQLAlchemy ORM)

## Core Features

- Automated User Onboarding: Registers new community members (LINE users) automatically upon their first interaction.
- Dynamic Survey Engine: Delivers questions sequentially based on active entries in the database.
- Rich Data Collection: Designed to handle and store various data types, specifically emphasizing text responses and Location data.
- State Management: Tracks where a user is in the survey, allowing them to resume seamlessly if they stop halfway.
- Clean Architecture: Well-structured FastAPI application separating routing, database models, and message handling logic.

## Project Structure

```text
ucr-chatbot-data-platform/
├── app/
│   ├── database/         # Database connection and session management
│   ├── handlers/         # LINE message processing logic (handling text, location, etc.)
│   ├── models/           # SQLAlchemy models (User, Question, AskLog, Response)
│   ├── config.py         # Environment variables configuration
│   └── main.py           # FastAPI entry point & LINE Webhook callback
├── requirements.txt      # Python dependencies
└── .env                  # Environment variables (not tracked)
```

## Setup & Installation

### 1. Prerequisites
Before running the application, you must have the following set up:

**LINE Official Account:**
- Create a Provider and a Messaging API Channel on the [LINE Developers Console](https://developers.line.biz/en/).
- Obtain your `Channel Secret` and `Channel Access Token` from the channel settings.

**PostgreSQL Database:**
- Install and run a PostgreSQL server locally or use a cloud provider.
- Create a new database for this project.
- Have your database connection credentials ready (username, password, host, port, database name).

### 2. Clone the repository
```bash
git clone <repository-url>
cd ucr-chatbot-data-platform
```

### 3. Create and activate a virtual environment

**On Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```cmd
python -m venv venv
venv\Scripts\activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Create a `.env` file in the root directory and add your credentials:
```env
CHANNEL_SECRET=your_line_channel_secret
CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
DATABASE_URL=postgresql://user:password@localhost/dbname
```

### 6. Run the application
```bash
uvicorn app.main:app --reload
```
*Note: The application will automatically create the required database tables (`users`, `questions`, `ask_logs`, `responses`) upon startup.*

## Database Schema Overview

- Users: Stores LINE User IDs to identify community members.
- Questions: A configurable library of survey questions.
- AskLog: Tracks the state of the survey for each user (which question was asked, is it answered).
- Responses: Stores the actual data provided by users, including a dedicated field for location data.

## Webhook Configuration

To connect the bot to LINE, ensure your LINE Developer Console Webhook URL is set to your server's endpoint (must be HTTPS):
`https://<your-domain>/callback`
