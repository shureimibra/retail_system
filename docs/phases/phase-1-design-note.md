# Phase 1 design note: the workflow engine

**Status:** draft for the owner's approval · 22 Oct 2026
**Goal:** the eight-step story in the spec (walk-in → capture → to-order → order → restock → follow-up → conversation → paid) runs end to end in the built-in customer simulator, with a test for every stage.
**Not in this phase:** the new look and screens (Phases 2–3), paid providers and M-Pesa confirmation (Phase 4). The current UI keeps working throughout, and the "record a blocked purchase" flow stays available at every step.

## 1. How it's delivered

Five pull requests, one after another. Each keeps the app working and all tests green, and each gets your sign-off before it merges.

| PR | Name | What it does |
|---|---|---|
| 1a | Foundations | Settings and security fixes, removes duplicate and dead code, phone numbers in +254 format, Shop and roles |
| 1b | Catalog and stock | Product types and options, photos, prices with price-drop tracking, stock receiving with holds |
| 1c | Lifecycle | New statuses and reasons with data migration, one transition service, timeline, visits, deposits and payments, change item |
| 1d | Messaging | One gateway, free providers, conversations, inbound replies and STOP, customer simulator |
| 1e | Automation | Restock and price-drop triggers, follow-up schedule, expiry, new KPI numbers, API v1 |

A permanent regression test for "owner records a missed sale (product, size, colour, reason, phone)" goes in with 1a and must pass in every later PR.

## 2. 1a: Foundations

**Settings**
- `DEBUG` defaults to `False` (local `.env` sets `True`).
- An empty or missing `SECRET_KEY` fails loudly outside DEBUG.
- Replace the removed `STATICFILES_STORAGE` with Django 5.2's `STORAGES`, so WhiteNoise compression works again.
- Celery runs tasks inline (`CELERY_TASK_ALWAYS_EAGER`) unless `CELERY_BROKER_URL` is set, so development needs no Redis. Tasks are only queued after the database commit (`transaction.on_commit`).

**Admin:** superusers only, at a configurable path (`ADMIN_URL`, default `ops/`), with read-only views on records whose history matters.

**Remove**
- the root `services/` package
- `send_sms.py`
- `notifications/signals.py`
- the empty signals in `intents/signals.py`
- `products/signals.py` and the `save()` overrides on Product and ProductVariation that fire them
- the synchronous send path in `products.services.update_product_stock`
- `notifications/services.SMSService`

Until the gateway arrives in 1d, the Celery task `send_restock_notification_task` is the **single** send path. A stock increase made through `products.services` (the API and dashboard restock buttons) triggers it explicitly, so restock messages keep working. Tests that call the removed code move to the app services.

**Keep it simple:** borrow only what this system needs. From Reatech360 that's only deposits on reserved items and roles with per-shop data. There's no customer balance profile and no setup wizard.

**Phones:** add the `phonenumbers` library. Every customer phone is saved as E.164 (`+254712345678`) using the shop's region, so `0712 345 678`, `+254 712…` and `254712…` all become one number. A data migration normalises existing numbers and reports any that can't be parsed instead of guessing.

**Shop and roles**
- **New `Shop` model:** name, phone region (KE), currency (KES), timezone (Africa/Nairobi), and logo later.
- **New `Membership` model:** user + shop + role (owner / manager / cashier). One person can hold several roles.
- **Scoping:** every business model gets a `shop` foreign key, filled by migration with one default shop. Queries are scoped to the user's shop.

This is the small step that makes many shops (Track 2) possible later without a rewrite.

**Fixes:** the REST API create returns the saved record with its id. The HTML create form goes through the service. Status is no longer a free-edit field in forms; it changes through actions.

## 3. 1b: Catalog and stock

**Product types**
- **`ProductType`** (per shop): name plus up to three option names in order. Seeded with **Shoes** (Size, Colour), **Clothing** (Size, Colour), **Bags** (Colour, Style), **Accessories** (Colour, Size) and **Other** (options the shop defines). Each option can have a suggested value list (EU 36–46, XS–XXL), editable in Settings later.
- **`Product`** gets a `product_type` and an optional photo.
- **`ProductVariation`** gets `option1–3` values, an optional own price and an optional photo (the colour photo). Existing `size` → option 1 and `color` → option 2. Existing products are typed from their category name (footwear → Shoes, apparel → Clothing, bag → Bags, accessor → Accessories, otherwise Other).

**Prices:** `PriceChange` records every price edit. When a price goes down, the price-drop trigger (1e) runs.

**Stock**
- `StockMovement` records every change: received, sold, adjusted, held or released, with who, why and a reference (for example a delivery note).
- `receive_stock(variation, qty, ref)` is the **only** way stock goes up. It locks the row, so two staff receiving at once can't lose an update (today's browser GET-then-PATCH can).
- `StockHold` reserves one unit per waiting customer. **Available = on hand − active holds**, and the floor screen shows available, not on hand.

**Photos** go to `MEDIA_ROOT` locally (cloud storage in production later), with resized thumbnails.

## 4. 1c: Lifecycle

**Statuses.** Old → new data mapping:

| Old | New |
|---|---|
| Pending, Monitoring | `open` |
| Resolved | `back_in_stock` |
| Customer Notified | `notified` |
| Recovered | `recovered` (marked "migrated, payment not recorded") |
| Closed | `declined` (reason "closed before upgrade") |
| — | `on_order`, `in_conversation`, `reserved`, `expired` (new) |

**Reasons** become a per-shop `Reason` model, editable in Settings. Each reason has a **trigger**: `restock` (size missing, colour missing, out of stock), `price_drop` (price too high, over budget) or `manual` (something else). Old values map one to one.

**Transitions.** One function, `intents.services.transition(intent, to, actor, **data)`, with an explicit allowed-moves table that matches the spec's lifecycle diagram. Any other move raises an error. Every move writes an `IntentEvent` (who, when, what, details), which powers the timeline and the audit trail. Nothing else sets `status`.

**New fields on a missed sale**
- `needed_by` (date)
- consent (yes or no, with a timestamp)
- preferred channel (WhatsApp, SMS or email)
- `ordered_at` and `expected_at` (On order)
- `pickup_by` (Reserved)
- `closed_reason`

**Visits.** A `Visit` (shop, customer, staff, outcome bought / didn't buy) groups "same customer, another item" and gives the walk-in conversion rate. A "Bought" visit has no missed sales.

**Payments**
- `Payment` records amount, method (M-Pesa, cash, card, bank), reference, kind (deposit or balance) and who recorded it.
- A deposit, or an agreed hold with a pickup date, makes it **Reserved**.
- When payments reach the item total, it becomes **Recovered**, the only revenue figure.
- Deposits can't exceed the total.

**Change item.** It records the old item in the timeline, moves the hold to the new item if it's available, or goes back to `open` for the new item.

## 5. 1d: Messaging

**Models.** `Conversation` (one per customer per shop) and `Message`:
- direction (in or out) and channel
- to, from and body
- template key and image URL
- status: queued, sent, delivered, read, failed or skipped
- provider and provider message id
- error code and detail
- attempts and cost
- timestamps

Old `NotificationLog` and `InboundSMSLog` rows migrate into `Message`.

**The gateway (`notifications/gateway.py`)** is the only code that talks to a provider. Before every send it checks:
1. consent
2. a valid E.164 number
3. no duplicates
4. WhatsApp's 24-hour rule (outside it, only approved templates)

It then picks the provider for the channel from the shop's settings.

**Providers, all free for development**

| Provider | Use |
|---|---|
| **Simulator** (default in development) | Stores messages; the simulator page shows them |
| **Email via SMTP** | Mailpit locally (a free local inbox) |
| **WhatsApp Cloud API** | Test number, a template with the item photo |
| **Africa's Talking** | Sandbox SMS |
| **Twilio SMS** | Kept as an option. Not the WhatsApp sandbox |

**Fallback:** if WhatsApp fails permanently (for example "not on WhatsApp"), the message is offered as SMS, then email. Provider errors retry up to three times with backoff. Invalid numbers and opt-outs never retry; they go to "Send failed" with a fix action.

**Inbound replies**
- Webhooks for WhatsApp (verify token + signature check), Africa's Talking (secret URL token) and Twilio (signature check).
- Exact phone match only, so no reply attaches to the wrong customer.
- STOP / STOPALL / UNSUBSCRIBE / CANCEL / END / QUIT opt the customer out on every channel.
- Any reply moves Notified → In conversation and pauses follow-ups.
- YES and HOLD are flagged for staff.

**Customer simulator.** A development-only page (`/dev/simulator/`) where you play the customer: you see each outbound message with its photo and reply as the customer. Replies go through the same inbound code as a real webhook. Plain styling; it's a developer tool, not part of the redesign.

**Message templates** are seeded for fashion and editable per shop later:
- restock alert (with photo)
- reminders on days 2, 4 and 7
- price drop
- deposit receipt
- pickup reminder
- on-order update

## 6. 1e: Automation

**Restock.** `receive_stock` creates holds for waiting customers, oldest first, one unit each, up to the quantity received. Those requests become Back in stock, and a message is queued after commit. Customers beyond the received quantity stay Open or On order. Only `restock`-trigger reasons react.

**Price drop.** A lower price notifies `price_drop`-trigger requests for that product or option, with the old and new price.

**Schedule.** A periodic task runs every 15 minutes (Celery beat in production, and `python manage.py process_due` for development without Redis):
- sends due follow-ups (days 2, 4, 7)
- expires Notified with no reply after the last one
- expires Reserved past pickup-by, releasing holds
- expires Open after 30 days

All timings are per-shop settings.

**Numbers**
- KPI selectors move to the new definitions: waiting demand, in conversation, reserved (deposits held), recovered (paid only), and walk-in conversion.
- Expired requests are excluded by default.
- The hardcoded "recovery funnel" percentages are removed from the current dashboard.

**API v1.** `/api/v1/` endpoints for capture, transitions, receiving stock, payments and messages, with the same services as the screens. Old `/api/` routes keep working until Phase 3.

## 7. Keeping the current UI working

The current templates get the minimum edits needed for the new data, and no redesign:
- status badges read the new statuses
- the create form shows option values instead of fixed size and colour
- the restock buttons call `receive_stock`

## 8. Done when

- The full story runs in the simulator: capture → to-order → mark ordered → receive 4 of 6 → 4 messages with photo → one reply → deposit → paid → Recovered. In the same run, one customer declines, one expires after day 7, and one price-too-high request is notified on a price cut.
- There is a test for every allowed transition, and every disallowed one raises an error.
- The "record a missed sale" regression test passes.
- No code outside the gateway calls a provider.
- `manage.py check`, `makemigrations --check` and the full test suite pass in CI.

## 9. Decisions this note assumes (say if any should change)

1. **Shop and roles are added now**, with every record scoped to a shop, even though there's one shop today.
2. **Unit holds:** one unit per waiting customer, oldest first. A hold lasts until the last follow-up (day 7 plus one day) or until the pickup-by date once Reserved (default 5 days).
3. **Old "Recovered" rows stay Recovered**, marked "payment not recorded", so past reports don't change.
4. **New dependency:** `phonenumbers`. No other new libraries in Phase 1.
5. **Item photos for real WhatsApp tests** must be at a public web address. During development the simulator needs nothing. For real-phone tests we'd use a free tunnel (Cloudflare Tunnel), set up when we reach 1d.
