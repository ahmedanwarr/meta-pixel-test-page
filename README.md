# meta-pixel-test-page

Test landing page for validating Meta Pixel + CAPI (Conversions API) dual-tracking before connecting to the live client ad account.

## Structure

```
├── index.html          # Landing page — collects lead, fires pixel + calls CAPI
├── thank-you.html      # Confirmation page shown after form submission
├── api/
│   ├── main.py         # FastAPI CAPI relay — forwards events server-side to Meta
│   └── requirements.txt
├── .env.example        # Environment variable template
└── .gitignore
```

## Quick Start

### 1. Fill in your Pixel ID

Replace `PIXEL_ID_HERE` in both `index.html` and `thank-you.html` with your actual Meta Pixel ID.

Replace `API_BASE_URL_HERE` in `index.html` with your CAPI relay URL (local: `http://localhost:8001`).

### 2. Set up the CAPI relay

```bash
cd api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # then fill in values
uvicorn main:app --port 8001 --reload
```

Required env vars:
| Variable | Where to get it |
|---|---|
| `META_PIXEL_ID` | Events Manager → your dataset ID |
| `META_CAPI_ACCESS_TOKEN` | Events Manager → Settings → Conversions API → Generate access token |
| `META_TEST_EVENT_CODE` | Events Manager → Test Events tab (remove in production) |

### 3. Test the full flow

1. Open `index.html` in a browser (or serve with `npx serve .`)
2. Fill in and submit the form
3. Check **Events Manager → Test Events** — you should see two `Lead` events with the same `event_id` (Meta deduplicates them into one conversion)

## How deduplication works

- The browser fires `fbq('track', 'Lead', ..., { eventID: eventId })` with a generated `event_id`
- The form also sends that same `event_id` to `/capi/lead`
- The relay forwards it to Meta with the same `event_id`
- Meta matches them and counts it as **one conversion**, not two

## Deploying

| Layer | Recommended host |
|---|---|
| HTML pages | Netlify (drag-and-drop deploy) |
| CAPI relay API | Fly.io, Render, or Railway (free tier) |

Once deployed, update `API_BASE_URL_HERE` in `index.html` to your live API URL, and set `ALLOWED_ORIGINS` to your landing page domain.
