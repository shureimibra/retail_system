# Retail OS

Missed-sale recovery for local fashion shops. When a customer can't buy what they came for (wrong size, colour, out of stock, price), staff record it in seconds. When the item is back, the customer is messaged, and the sale counts as recovered only when it's paid.

> **Status:** being rebuilt in phases from the earlier "Retail Purchase Constraint Management System". See `docs/design/retail-os-design-spec.html` for the approved design and build plan. The current UI is the old one until Phase 2.

## Stack

- Python 3.11, Django 5.2, Django REST Framework
- Celery + Redis for background messaging
- SQLite locally, PostgreSQL in production (`DATABASE_URL`)
- Server-rendered templates, Chart.js, ReportLab (PDF exports)

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows (use: source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Generate a `SECRET_KEY` for `.env` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Leave the Twilio values blank to run messaging in simulation mode.

## Messaging (free setup)

Out of the box every message goes to the built-in **customer simulator**, and nothing leaves your computer. Sign in and open `/notifications/simulator/` to see what customers would receive and to reply as them.

To use real channels for free, set these in `.env`:

| Channel | Free option | Settings |
|---|---|---|
| WhatsApp | Meta WhatsApp Cloud API test number (developers.facebook.com) | `WHATSAPP_PROVIDER=whatsapp_cloud`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`. Webhook URL: `/notifications/webhooks/whatsapp/` |
| SMS | Africa's Talking sandbox (username `sandbox`) | `SMS_PROVIDER=africastalking`, `AFRICASTALKING_API_KEY`, `AFRICASTALKING_WEBHOOK_TOKEN`. Callback URL: `/notifications/webhooks/africastalking/<token>/` |
| Email | Mailpit locally (`docker run -p 8025:8025 -p 1025:1025 axllent/mailpit`) | `EMAIL_PROVIDER=email`, `EMAIL_HOST=localhost`, `EMAIL_PORT=1025` |

Follow-ups (days 2, 4 and 7), expiry and message retries run every 15 minutes through Celery beat. Without Redis, run them by hand with `python manage.py process_due`.

Webhooks need a public address. For local testing, run a free tunnel (for example `cloudflared tunnel --url http://localhost:8000`) and set `SITE_URL` to it, so photo links in WhatsApp messages work too.

## Tests

```bash
python manage.py test
```

CI runs the same checks on every push and pull request (`.github/workflows/tests.yml`).

## Docs

| File | What it is |
|---|---|
| `PRODUCT.md` | Users, purpose, brand personality, principles |
| `DESIGN.md` | Colours, type, components, do's and don'ts |
| `CLAUDE.md` | How work is done in this repo, and which design skills are used |
| `docs/design/retail-os-design-spec.html` | Approved design spec with screen mockups |
| `docs/CLAUDE_AI_SYSTEM_HANDOVER.md` | Handover from the previous build (partly outdated; see the spec) |
