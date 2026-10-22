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
