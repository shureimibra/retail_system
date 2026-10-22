# Retail OS — working agreement

Django 5.2 + DRF app for local fashion shops: capture missed sales, re-engage customers (WhatsApp first), count recovered revenue. See `PRODUCT.md` (who and why), `DESIGN.md` (how it looks), and the approved spec `docs/design/retail-os-design-spec.html`.

## How we work
- Design first. No UI or workflow code without an approved spec or brief.
- One phase at a time, on its own branch (`phase-N/...`): a short design note, then build, tests, the owner's sign-off, then merge.
- Never commit secrets. `.env` is local only; `.env.example` lists the keys.
- No force-pushes or history rewrites without explicit approval.

## Precedence when instructions conflict
1. The owner's words in the conversation
2. The approved spec, `PRODUCT.md` and `DESIGN.md`
3. The `impeccable` skill suite
4. Any other skill

## Skills
**Use:** `impeccable` (umbrella), `shape`, `critique`, `audit`, `polish`, `typeset`, `layout`, `clarify`, `adapt`, `harden`, `animate` (in-app motion only), `optimize`, `distill`, `quieter`, `emil-design-eng` (principles only, no React code), `dataviz` (charts), `code-review`, `simplify`, `security-review`, `run`, and `reverse-engineer-anything` (research on public pages and open-source software only; borrow patterns, never branding or code).

`delight` and `overdrive` are only for the later landing/marketing phase.

**Do not use in this project:** `cosmic-glass-dashboard`, `design-taste-frontend`, `gpt-taste`, `high-end-visual-design`, `stitch-design-taste`, `redesign-existing-projects`, `minimalist-ui`, `industrial-brutalist-ui`, `ui-ux-pro-max`, `colorize`, `bolder`, `image-to-code`, `imagegen-frontend-web`, `imagegen-frontend-mobile`, `brandkit`, `website`. They impose conflicting aesthetics or stacks (React, Tailwind, GSAP).

## Product rules that code must respect
- Lifecycle: Open → On order → Back in stock → Notified → In conversation → Reserved → Recovered. The exits are Declined and Expired. Only **Recovered** (paid in full) counts as recovered revenue. Declined is never revenue.
- Price-too-high and over-budget requests are triggered by a price drop, not a restock.
- Launch scope is fashion: Shoes, Clothing, Bags, Accessories, Other. Product types and options are configurable, not hardcoded to size and colour.
- Messaging is free and sandbox first (simulator, Mailpit, WhatsApp Cloud test number, Africa's Talking sandbox), all behind one gateway.
- Web app only, phone-first and responsive (360 / 768 / 1280px).
- Customisation lives in Settings, never on the dashboard. The Django admin is for platform operators (superusers) only.

## Commands
```bash
python -m venv venv && venv/Scripts/activate    # Windows; use venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                              # then fill in values
python manage.py migrate
python manage.py test
python manage.py seed_demo                        # sample fashion shop in an EMPTY database (amina / demo-pass-123)
python manage.py process_due                      # follow-ups, expiry, retries (Celery beat does this every 15 min)
python manage.py runserver
```

## Code conventions
- Services (`<app>/services.py`) do writes; selectors (`<app>/selectors.py`) do reads. Views stay thin.
- The root `services/` package is legacy and duplicated; it is being removed in Phase 1. Don't add to it.
