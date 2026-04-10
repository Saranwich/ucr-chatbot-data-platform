# UCR Chatbot Data Platform

A data collection platform built on the LINE Messaging API using FastAPI and PostgreSQL. This system allows for dynamic questioning and response tracking for LINE users.

## Features

- **Automated User Onboarding:** Automatically registers new LINE users in the database upon their first interaction.
- **Dynamic Survey Engine:** Delivers questions to users one by one based on active entries in the `questions` table.
- **Response Management:** Tracks and stores user responses, ensuring users resume where they left off if they stop mid-survey.
- **Webhook Integration:** Seamlessly handles LINE Webhooks using the `line-bot-sdk-python` v3.
- **Clean Architecture:** Separated concerns between handlers, models, and configuration.

## Tech Stack

- **Framework:** [FastAPI](https://fastapi.tiangolo.com/)
- **Database ORM:** [SQLAlchemy](https://www.sqlalchemy.org/)
- **Database:** PostgreSQL (via `psycopg2-binary`)
- **LINE Integration:** [line-bot-sdk-python (v3)](https://github.com/line/line-bot-sdk-python)
- **Configuration:** `python-dotenv`
- **Server:** `uvicorn`

## Project Structure

```text
ucr-chatbot-data-platform/
├── app/
│   ├── database/         # DB engine and session management
│   ├── handlers/         # Message processing logic
│   ├── models/           # SQLAlchemy models (User, Question, Response, etc.)
│   ├── config.py         # Environment configuration
│   └── main.py           # FastAPI entry point & Webhook callback
├── requirements.txt      # Python dependencies
└── .env                  # Environment variables (not tracked)
```

## Setup & Installation

### 1. Clone the repository
```bash
git clone <repository-url>
cd ucr-chatbot-data-platform
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory:
```env
CHANNEL_SECRET=your_line_channel_secret
CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
DATABASE_URL=postgresql://user:password@localhost/dbname
```

### 5. Run the application
```bash
uvicorn app.main:app --reload
```

## 📊 Database Schema

- **Users:** Stores LINE User IDs and metadata.
- **Questions:** A library of questions to be asked to users.
- **AskLog:** Tracks which questions have been sent to which user and their status.
- **Responses:** Stores the actual answers provided by users (supports text and placeholders for location).

## 🔗 Webhook Configuration
Ensure your LINE Developer Console points to:
`https://<your-domain>/callback`
