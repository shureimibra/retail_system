# Phase 3 design brief: the working screens

**Status:** approved by the owner · 22 Oct 2026 · 3a built on `phase-3a/work-queue`
**Inputs:** `PRODUCT.md`, `DESIGN.md`, the approved spec (`docs/design/retail-os-design-spec.html`, sections 8 and 9), the Phase 2 shell, and the owner's notes so far:
- keep it simple and borrow only what's needed
- no customer balance profile
- Reports gets more, kept simple

The spec's mockups are the visual reference. No new colours, fonts or components beyond the Phase 2 system.

## 1. Feature summary

Phase 2 gave every page the new look. Phase 3 rebuilds the pages around the work itself:
- Home becomes a work queue.
- Missed sales becomes **Waiting**.
- Messages becomes **Conversations**, with the deal beside the chat.
- **To order**, **Product detail** and **Floor mode** are new.
- Customers and Reports get the views the owner asked for.

All the workflow logic already exists from Phase 1 (holds, restock messages, deposits, price drops), so this phase is mostly screens over existing services.

## 2. Primary user action

**Act on the next thing that brings money back:**
- answer a waiting customer
- take a deposit
- order what people are waiting for
- log a missed sale in under 20 seconds at the till

## 3. Design direction

Unchanged from Phase 2: Restrained colour, petrol as the only accent, clay only for "a customer is waiting on you", IBM Plex, flat panels, no decoration.

- **Scene:** the owner opens the app at 8am on a phone before the shop opens, wanting to know who to call and what to buy. During the day a cashier uses a tablet at the till between customers.
- **Anchors:** Shopify Inbox (chat plus order panel), Linear's triage list (one row per action, clear next step), Loyverse's till screen (big targets, few choices).

## 4. Delivery: three slices, one PR each

Phase 3 is too large to review in one go. Each slice is its own branch and PR with tests, screenshots and your sign-off.

| Slice | Screens | Why this order |
|---|---|---|
| **3a · Work queue** | Home with widgets, Settings → Home layout, Reports additions, new navigation | Everything else links from Home |
| **3b · Stock and demand** | Waiting, To order, Product detail with photos and the option grid, Customers with grouped records | The morning routine: what to buy, who is waiting |
| **3c · Talk and capture** | Conversations (list, chat, deal panel), Floor mode | The two highest-touch screens; they deserve their own review |

## 5. Navigation (applies from 3a)

| Screen | Change |
|---|---|
| Desktop and tablet sidebar | **Customers:** Waiting, Conversations · **Stock:** To order, Products · **Shop:** Customers, Reports · Settings and Sign out at the bottom. Counts beside Waiting, Conversations (clay, unread) and To order |
| Phone tab bar | Home · Waiting · **+** · Chats · More (Products, To order, Customers, Reports, Settings, Sign out) |
| Top bar | **Floor mode** button next to **Log missed sale** (desktop and tablet) |

Old URLs (`/intents/`, `/notifications/`) redirect to the new pages, so bookmarks keep working.

## 6. Screens

### 3a · Home (work queue)

- **Key numbers** (one row): Waiting demand (money and customers, "5 need it this week"), In conversation ("2 unanswered over 1 hour"), Reserved (deposits held), Recovered (paid in full only, with change against the previous period). Each number links to the records behind it.
- **Needs you now:** one row per action, newest first, each with one button:
  - customer replied and is waiting → **Reply**
  - promises due within 2 days with nothing ordered → **To order**
  - reserved items past their pickup date → **Open**
  - messages that failed → **Send as SMS** or **Fix number**

  Empty state: "Nothing needs you right now."
- **Why people didn't buy:** share of each reason in the period (simple horizontal bars, `dataviz` rules).
- **To order today:** the top 5 items by money waiting, linking to To order.
- **Recovered per week:** the last 8 weeks, paid recoveries only.
- **Walk-in conversion:** visits logged as Bought ÷ all visits logged in the period. Hidden until there are at least 10 visits.
- **Period picker** stays at the top right and applies to the charts and Recovered. Key numbers for waiting and conversations always show "now".

### 3a · Settings → Home layout (Owner)

Choose the widgets each role sees and their order: Owner, Manager, Cashier tabs, a checklist with up/down buttons (no drag library), Save. Staff can't change their own Home.

**Defaults:**
- **Owner and Manager:** all widgets.
- **Cashier:** Needs you now and Key numbers only.

### 3a · Reports additions

Kept to three, each with the period picker and a CSV download:
1. **Recovered money by month:** paid in full only; Declined is never counted.
2. **Missed sales by reason and by product:** the item, option and count of what to stock.
3. **To-order list:** the same list as the To order page, as a CSV for the supplier.

Per-staff numbers and deposits held stay for later, as agreed.

### 3b · Waiting

The list of open demand, grouped by customer (one row per customer, their items under it).

- **Tabs:** Waiting for stock · Waiting for a lower price · All records (every status, the old Missed sales list).
- **Each item shows:** product and option, reason, status badge, needed by, days waiting.
- **Filters:** search (name, phone, product, SKU), status, reason, period.
- **Bulk action (owner, manager):** **Mark as ordered** with an expected date.
- **Phone:** each customer is a card; items stack inside it.

### 3b · To order (owner, manager)

The morning list:
- **One row per product option** with customers waiting: item and SKU, waiting customers (initials, "+3"), quantity needed, money waiting, earliest needed-by date, status (Open / On order with the expected date).
- **Sort:** money waiting, then needed by.
- **Actions:**
  - select rows → **Mark as ordered** (sets On order and the expected date)
  - **Share with supplier**: a plain-text list opened in WhatsApp (`wa.me` share link) or copied, plus the CSV from Reports

### 3b · Product detail (new page)

- **Header:** photo, name, type, price, SKU pattern; actions **Change price** and **Receive stock**.
- **Option grid:** rows for one option (for example Colour), columns for the other (Size). Each cell shows stock, plus "N waiting" in clay when customers want it. Tapping a cell opens Receive stock for that option. Products with one option show a simple list.
- **Panels:** Waiting for stock (customers, money, oldest need) and Waiting for a lower price ("Any price below KSh 12,500 messages them").
- **Photos:** one product photo plus an optional photo per option value, used in restock messages. Uploads are resized to a 800px thumbnail.

### 3b · Customers

- **List:** name, phone, number of open items, last contact.
- **Detail:** their items with statuses, payments recorded, and a link to the conversation.
- No balance profile.

### 3c · Conversations

| Screen | Layout |
|---|---|
| Desktop | Three panes: inbox list · chat · deal panel |
| Tablet | List · chat; the deal panel opens beside the chat on demand |
| Phone | List → chat, with the deal pinned on top as one line ("Adidas Ultraboost 42 / Grey · KSh 18,700 · held until Tue · **Deposit**"), opening a sheet |

- **Inbox:** customer, last message, time, status badge, unread dot. Filters: Needs reply · All.
- **Chat:**
  - messages with delivery state (sent, delivered, read, failed)
  - the item photo on restock messages
  - quick replies: *Send payment details*, *Confirm pickup*, *Offer another option*
- **WhatsApp 24-hour window:** free replies only while the window is open ("Free replies open for 23 h"). When it's closed, the box offers the approved follow-up template instead.
- **Deal panel**, for each of the customer's open items:
  - stage stepper (Notified · Talking · Reserved · Paid)
  - price, hold and expiry, who logged it and when, follow-up state
  - **Change item**
  - **Record a deposit** (amount, M-Pesa / Cash / Card, reference)
  - **Paid in full**
  - **Declined**, with a reason

### 3c · Floor mode

A focused till screen: no sidebar, big targets (50px+), and an **Exit** link.

**First step: how did this visit end?**
- **Bought** logs a visit with one tap.
- **Didn't buy** opens three steps:
  1. **What they wanted:** search or pick a product; option chips show stock ("42 · 0 left"); reason chips. Price and budget reasons say "messaged on a price drop".
  2. **Customer:** phone first, with the number keypad; a match fills the name. Email and name are optional.
  3. **Confirm:** "needed within" chips (2 days · 3–4 days · A week · No rush), consent line, summary. Then **Save** or **Save, same customer, another item**.

Cashiers can quick-add a product if the owner allows it ("Needs review").

**Layout:**
- **Phone:** one step per screen, button in thumb reach.
- **Tablet landscape:** all three steps side by side.
- **Tablet portrait:** two steps side by side.

## 7. Key states (all screens)

| State | Behaviour |
|---|---|
| Empty | One sentence plus the action that fills it ("No one is waiting. Missed sales you log appear here.") |
| Loading | Server-rendered pages; no skeletons needed. Buttons show a working state on submit |
| Errors | Inline, saying how to fix it. A failed send says why ("Not on WhatsApp") and offers the fallback |
| Permissions | Cashier: Home (their layout), Waiting, Conversations, Floor mode, Customers. No To order, price changes or Reports. Every action is checked on the server, not just hidden |
| Dark mode, 360/768/1280 | Checked for every screen before sign-off |
| No JavaScript | Everything works as plain forms; scripts only add conveniences (chips, step transitions, auto-refresh of the inbox every 30s) |

## 8. Data changes (small)

| Change | Why |
|---|---|
| `Shop.home_layout` (JSON: role → ordered widget keys, with defaults) | Settings → Home layout |
| `Shop.payment_details` (text, in Shop details) | The "Send payment details" quick reply |
| `Product.supplier` (optional text) | To order grouping and the shared list |
| `ProductOptionPhoto` (product, option value, image) | A photo per colour rather than per variation row; falls back to the product photo |
| Thumbnail on upload (Pillow, already installed) | Pages stay light on mobile data |

No changes to the lifecycle, holds or messaging rules.

## 9. Not in this phase

- Assigning conversations to staff.
- Ctrl K search.
- Offline capture.
- "Add to home screen".
- Per-staff reports and deposits held.
- Paid channels and M-Pesa confirmation (Phase 4).

## 10. Decisions (owner, 22 Oct)

1. **Delivery:** three slices, 3a → 3b → 3c, one PR each.
2. **Supplier:** an optional supplier name on each product; To order can group and share by supplier.
3. **Phone tab bar:** Home · Waiting · + · Chats · More, as in the spec.

## Done when (per slice)

- [ ] Screens match this brief at 360, 768 and 1280px, light and dark, with no sideways scroll.
- [ ] Role rules enforced on the server, with tests.
- [ ] Every number links to its records, and only paid in full counts as recovered.
- [ ] `audit` and `polish` run; tap targets ≥44px (≥50px in Floor mode).
- [ ] All tests pass on PostgreSQL and SQLite.
