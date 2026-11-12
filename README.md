# Activity Log Viewer

A very small FastAPI app that renders the latest rows from the Supabase `activity_logs` table.

The viewer reads `activity_logs` and orders newest first by `occurred_at` (then `id`).
Date filters use UTC event time; the timezone selector changes timestamp display only.
Event type filtering accepts an exact value rather than a fixed list.
Coordinates, accuracy (m), speed (m/s), and motion are shown in the table; expand
View details for receipt time, notes, session/version identifiers, and JSON payload.
The map defaults to the past hour ending now, displayed in browser-local time.
Time fields can be edited or cleared; Reset to last hour restores the default.

Recent map shows the latest location records across all users, with separate lines
for each user/session. Filter by exact user ID and optional browser-local start/end times (converted to UTC for querying)
(start inclusive, end exclusive). It shows up to 5,000 location updates after filtering, using small clickable dots
and does not inherit log filters.

When updating an existing deployment, set `SUPABASE_LOGS_TABLE=activity_logs`
in its environment and restart the app. The configured Supabase key must have
read access to the new table. This change does not create tables or move old data.

Run the viewer checks without contacting external services:
`.venv/bin/python -m pytest tests/test_activity_logs.py -q`

## Data Quality page

`/data-quality` (PB-624) shows data quality checks on `locations` and
`jurisdictions`. Each section calls a read-only `dq_*` database function that
must exist in the Supabase project the panel points to (dev):

- `dq_locations_by_data_source()` - total locations, by data source
- `dq_duplicate_place_ids()` - place_ids used by more than one location (PB-653)
- `dq_jurisdictions_without_topics()` - jurisdictions with no jurisdiction_topics (PB-654)
- `dq_locations_with_parent_not_child()` - locations with a parent_id that aren't `place_child`
- `dq_locations_by_status()` - location counts by status and data source
- `dq_jurisdictions_missing_geofence()` - non-federal jurisdictions with no buffered geofence

Apply new or changed functions in the Supabase dashboard SQL editor. Each
check loads independently, so a missing function only errors its own section.

Run its checks without contacting external services:
`.venv/bin/python -m pytest tests/test_data_quality.py -q`

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

## Deploying on Firebase

Deploy updates to the debug panel:

```sh
./scripts/deploy.sh
```

This updates Cloud Run and only the `pb-debug-panel` Hosting site, preserving the
existing server configuration. See [FIREBASE_DEPLOY.md](FIREBASE_DEPLOY.md) for
CLI authentication and initial setup.

## Local production run viewer

Choose **Local run** in the panel navigation (`/local-run`), then select or drop a
TransistorSoft diagnostic `.log` or `.txt` exported from Field Diagnostics → Email
TS Diagnostic Log. Parsing stays in browser memory; no log data is sent to the
server or saved. Select a day to inspect its trail, queued points, motion changes,
HTTP results, and approximate distance (excluding gaps longer than five minutes).
Timestamps are shown as logged; intermediate single-location samples are excluded.
Queued points indicate database inserts, not proof of successful upload.

The basemap starts disabled. Enabling it requests OpenStreetMap tiles for the
viewed area; the Leaflet library and stylesheet load from a CDN even with the
basemap disabled. This parser supports the iOS diagnostic text format shown in
the supplied viewer, not arbitrary JSON exports or other diagnostic formats.

Checks: `node --test tests/local_run_parser.test.cjs` and
`.venv/bin/python -m pytest tests/test_local_run.py -q`.
