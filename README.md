# Activity Log Viewer

A very small FastAPI app that renders the latest rows from the Supabase `activity_logs` table.

The viewer reads `activity_logs` and orders newest first by `occurred_at` (then `id`).
Date filters use UTC event time; the timezone selector changes timestamp display only.
Event type filtering accepts an exact value rather than a fixed list.
Coordinates, accuracy (m), speed (m/s), and motion are shown in the table; expand
View details for receipt time, notes, session/version identifiers, and JSON payload.
Recent map shows the latest location records across all users, with separate lines
for each user/session. Filter by exact user ID and optional UTC start/end times
(start inclusive, end exclusive). It shows up to 500 location updates after filtering, using small clickable dots
and does not inherit log filters.

When updating an existing deployment, set `SUPABASE_LOGS_TABLE=activity_logs`
in its environment and restart the app. The configured Supabase key must have
read access to the new table. This change does not create tables or move old data.

Run the viewer checks without contacting external services:
`.venv/bin/python -m pytest tests/test_activity_logs.py -q`

## Setup

Project location:
`/Users/samiam/clients/kaleo/pb/test_portal`

1. Create and activate a virtual environment.
2. Install dependencies:
   `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your Supabase values.
4. Start the app:
   `uvicorn app.main:app --reload`
5. Open:
   `http://127.0.0.1:8000`

You can also run it without activating the virtual environment:
`.venv/bin/uvicorn app.main:app --reload`

## Environment variables

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY` for direct DB integration tests
- `SUPABASE_LOGS_TABLE` defaults to `activity_logs`
- `DEFAULT_LOG_LIMIT` defaults to `100`
- `APP_PASSWORD` defaults to `arsenal`
- `SESSION_SECRET` should be set to a random secret in production

## Product flow tests

This repo now has a small pure-Python integration test skeleton under `product_tests/` and `tests/`.

1. Install dependencies:
   `pip install -r requirements.txt`
2. Copy `.env.example` to `.env.test` and fill in test credentials.
3. Put the Firebase service-account JSON at `./firebase-service-account.json`, or set `FIREBASE_SERVICE_ACCOUNT_JSON` in `.env.test`.
4. Run the current skeleton test:
   `pytest -q`

The first test creates a Firebase Auth user, reads it back, confirms key values, and deletes the user in cleanup. Real secrets and service-account files are ignored by git.

## Deploying on Render

This app works well as a Render web service.

### Option 1: Use the Render blueprint

If you deploy from this repo with `render.yaml`, Render will prefill the service settings for you.

### Option 2: Create the service manually

Use these settings in Render:

- Environment: `Python 3`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Set these environment variables in Render:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_LOGS_TABLE=activity_logs`
- `DEFAULT_LOG_LIMIT=100`
- `APP_PASSWORD=arsenal`
- `SESSION_SECRET=<random-secret>`
