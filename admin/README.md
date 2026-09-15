# Admin, dashboard, and report media

## Run

Use the existing `.env` settings for PostgreSQL, Redis, LINE, and Typhoon, then start:

```sh
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/admin/**. Plain HTML, CSS, and JavaScript live in the top-level `admin/` directory, outside `app/`. FastAPI serves the page and APIs on the same origin. No authentication or CORS middleware is included in this version.

Startup creates every table in `app.clients.psql.init_db` with `CREATE TABLE IF NOT EXISTS`; existing report, image, and location rows remain intact. No frontend build or Node dependency installation is needed.

## Pages

- **Map & reports:** map spots for linked coordinates; click a spot or report to see its fields, locations, and images. Reports without coordinates remain in the list. Filter by problem type. The page loads 100 reports at a time; “Load more” adds older reports and their spots. Listing defaults to all dates.
- **Dashboard:** report count, daily report graph, category totals and leading category, and counts with images, locations, both, or neither. Select 7, 30, 90, or 365 calendar days. Dates use `Asia/Bangkok`; image/location cards count report records, not individual attachments. Counts with images and with locations each include records with both. Other entity totals and session statuses are all-time.
- **Broadcasts:** select multiple users or all known users, enter text, then confirm. Sending starts immediately and cannot be recalled; the confirmation dialog is the only review step. Recipients are captured when the message is created. Everyone receives the same text. History shows per-recipient request outcomes.

The map uses [Leaflet](https://leafletjs.com/examples/quick-start/) and OpenStreetMap tiles. Map assets and tiles need an internet connection; reports remain accessible in the list if the map library cannot load.

## API

Two prefixes. `/api/dashboard` is read-only work the whole team does; `/api/admin` is what only an
administrator does.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/dashboard/reports?limit=50&offset=0&type=flood&days=30` | Report page with nested images and locations. `type` and `days` are optional; omitted `days` includes all history. |
| GET | `/api/dashboard/reports/{id}` | One report with its session ID and media. |
| GET | `/api/dashboard/images/{id}` | Local image file, or 404 if unavailable. |
| GET | `/api/dashboard/statistics?days=30` | Period report totals, media coverage, categories, daily series, and all-time entity counts. |
| GET | `/api/dashboard/users?limit=50&offset=0` | Users available for recipient selection. |
| POST | `/api/admin/broadcasts?force_send=false` | Capture the recipients and start sending; returns 202 immediately with the record to poll. `force_send=true` pushes to recipients who are mid-conversation instead of skipping them. |
| GET | `/api/admin/broadcasts?limit=50&offset=0` | Paginated broadcast history. |
| GET | `/api/admin/broadcasts/{id}` | Broadcast content, aggregate counts, and individual recipient statuses. |
| GET | `/api/admin/system-config` | Running system configuration, including the automatic-broadcast flag. |

Pagination accepts `limit` from 1 to 200 and nonnegative `offset`; report periods accept 1 to 365 days.

Example send request:

```json
{
  "text": "Community notice",
  "audience": "selected",
  "user_ids": ["00000000-0000-0000-0000-000000000001"]
}
```

Use real internal user UUIDs returned by `/users`. For all known users, send `"audience": "all"` and omit `user_ids`. Invalid selected IDs reject the whole message; nothing is sent. Text must be nonblank and no longer than 5,000 UTF-16 units.

## Report attachments

- Successful image downloads appear in the transcript as `[got image from user: image_id=...]`. Failed downloads use `[image download failed]`, without a usable attachment reference.
- Analyzer output includes `image_ids` and `location_ids`; the model sees references, not image pixels or coordinate values.
- `report_images` is a many-to-many join table. One photo can support separate reports without merging those reports.
- Every attachment must belong to the same session. Images must have a saved storage key; locations must have complete coordinates.
- Saving a report and its attachment links happens in one transaction. The entire multi-report analysis batch is not one transaction.
- Existing location-linked report IDs can be reused on analysis retry. Image-only retries have no general deduplication; image equality does not establish report identity.
- Old generic image markers are not automatically backfilled into report associations. The new association flow applies to identifiable images in new conversations.

## Broadcasting behavior

`app.services.broadcast.send(text, audience, user_ids, force_send)` is the whole interface. It validates the payload, writes durable `broadcasts` and `broadcast_deliveries` rows, starts dispatch in the background, and returns the record right away so an HTTP caller does not wait for hundreds of pushes. LINE text goes out through `app.clients.line.push`; each recipient has a stable retry key, following [LINE's retry-key guidance](https://developers.line.biz/en/docs/messaging-api/retrying-api-request/).

There is no draft state. Reviewing before sending is the front end's job, not a row in the database.

`system_config.broadcast_auto_enabled` defaults to `false` and lives on the same active row as the session timeouts. Nothing reads it yet: it is there for whatever component later decides on its own whether to call `send`, because "send a message" and "is the system allowed to send one right now" are separate questions.

- `pending`: not attempted.
- `sending`: claimed by the dispatcher.
- `sent`: LINE accepted the HTTP request; this is not a read receipt.
- `failed`: LINE returned a non-200 response.
- `unknown`: transport failure or timeout leaves acceptance uncertain. The application does not resend it automatically.
- `skipped`: the recipient had already spoken in an open conversation when the dispatcher reached them, so nothing was pushed. They do not receive this broadcast at all; there is no deferred retry. An open session in which the villager has not said anything yet does not count as a conversation and is pushed to normally.

`force_send=true` overrides the skip and pushes anyway. A forced message that LINE accepts is appended to that live conversation, so the bot can see what it said when the villager replies. Only the administrator route can set it; the internal automatic hook never does. The append rewrites the whole session blob, so a message arriving at the same moment can be lost — an accepted trade-off for forcing a send into a live chat.

Sending runs in the FastAPI process. Process shutdown or a database outage can interrupt a broadcast; automatic recovery and retry of interrupted work are outside this version. No startup or scheduled job sends broadcasts.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -t .
node --check admin/admin.js
git diff --check
```

The unit suite mocks external services. An additional isolated PostgreSQL check exercised schema initialization twice, report/media persistence, dashboard aggregates, admin HTTP responses and image serving, draft transactions, audience selection, send-once behavior, and failed/unknown request outcomes. LINE calls were mocked in that check too.
