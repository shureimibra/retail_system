# Phase 7 design note: getting a shop started

**Status:** approved by the owner 27 Oct 2026, with this scope · built on `phase-7/onboarding`
**Owner's scope decision (27 Oct, later the same day):**
- **Build now:** invitation links (§3), the demo shop (§4), and the setup guide invited owners land in (§5).
- **Documented, built later** when the landing page and pricing are decided: self sign-up with its spam protection (§2), and the free trial and billing (§6). Until then, every shop comes in by invitation, and the team sets "paid until" by hand outside the app.
**Owner's decisions (27 Oct 2026):**
- Shops can come in **both ways now**: invited by the Retail OS team, or signing up themselves.
- **Spam protection, a free-trial policy and billing** are needed from the start.
- **A guided demo shop** to explore first: yes.

**Still free to run:** everything here uses free tools. Billing collects money **from** shops through M-Pesa; Safaricom's normal transaction charges apply to each payment received.

## 1. What this phase delivers

1. **Two ways in:**
   - **Self sign-up** from the landing page;
   - an **invitation link** that the Retail OS team sends a shop owner.
2. **Explore the demo shop:** a ready-made sample fashion shop to click around in before setting up their own. It's safe: nothing is sent to real customers.
3. **"Set up your shop":** a six-step guide, from empty to ready, covering shop details, products (Excel import), team, payments and messaging. A practice run ends it.
4. **Free trial, then a monthly plan paid by M-Pesa,** with clear reminders and no surprises.
5. **Spam and abuse protection** that costs nothing.

## 2. Signing up (self sign-up)

**The form:** your name, shop name, email, phone, password. One screen.

**Protection, all free:**
- **Cloudflare Turnstile:** an invisible "are you human" check, free.
- A **hidden trap field** for bots, as on the shop link.
- **Limits:** a few sign-ups per connection per hour.
- **Email verification:** a link by email, through the free email plan. The account works straight away, but **real customer messages stay off** until the email is verified.
- **Phone:** stored, but not checked by SMS for now, since SMS codes cost money. A WhatsApp check can come later.

**Why messages stay off until verified:** WhatsApp and SMS are paid on the platform's accounts. A fake sign-up must not be able to send messages at your cost. Until then, the shop uses the simulator, which is the practice run in step 6.

## 3. Invitation

- **In the operators' admin** (`/ops/`), the Retail OS team creates a shop with the owner's name, email or phone, and chosen plan. That gives a **one-time link**, valid 7 days.
- The team sends the link by WhatsApp or email, by hand for now.
- **The owner opens it, sets a password** and goes straight to "Set up your shop". The email counts as verified.
- **The team can choose the trial length** (or "no trial, already paid") per invitation, for deals agreed in person.
- **Shop owners invite their own staff** the same way, from Settings → Team. That page already exists; it gains the invitation link.

## 4. The demo shop

- From the sign-in page (and later the landing page), **"Try the demo"** at `/demo/` gives the visitor their own copy of the sample fashion shop, with a temporary account. No sign-up is needed:
  - products and waiting customers;
  - a reply waiting, a reservation, recovered sales, reports.

  It's built from the existing `seed_demo` data.
- **A bar at the top:** "Demo shop. Nothing here is real, and no messages leave Retail OS. **Set up my real shop →**"
- **Everything works**, but all messages go to the simulator, so they can play the customer.
- **"Start over"** gives a fresh copy. Demo shops are deleted automatically after 2 days. A connection can open a few demos an hour, so bots can't fill the database.
- **Safety:**
  - a demo shop only ever uses the simulator, never real WhatsApp, SMS, email or M-Pesa;
  - it never receives real customers' replies;
  - its shop link is closed.
- **Sales demos:** you can open the same demo in front of a client.

## 5. "Set up your shop": six steps

On its own page, `/setup/`, with a progress bar. Every step can be skipped and finished later. Everything stays editable in Settings afterwards: the guide only fills in the same settings.

| Step | What they do | Uses |
|---|---|---|
| 1. Your shop | Name, logo, country (phone format), currency | Settings → Shop details |
| 2. What you sell | Tick types (Shoes, Clothing, Bags, Accessories, Other); common sizes and colours are filled in, to edit | Product types |
| 3. Your products | **Download the Excel template → fill in → upload**, with the preview from Phase 5. Or add a few by hand, or skip | Import stock |
| 4. Your team | Invite cashiers and managers; choose who may add products | Team and roles |
| 5. Payments and messages | M-Pesa till or paybill and the payment details sent to customers; how long items are held; reminder days (good defaults shown) | Payments, Follow-ups |
| 6. Try it | Log a practice missed sale, receive stock, and **see the customer's WhatsApp in the simulator**. Then copy the shop link and print the QR code | Log missed sale, Shop link |

**On Home** (staying uncluttered): one slim line until setup is done, "Finish setting up your shop · 3 of 6 →". There is no checklist on Home.

**After step 6:** "Your shop is ready". It explains what happens next: going live with WhatsApp needs the business's own number and verification (`docs/going-live-messaging.md`), and the Retail OS team helps with that.

## 6. Free trial and billing

**Proposed policy (please confirm or change the numbers):**

| | Proposal |
|---|---|
| **Free trial** | **14 days**, everything included, no payment details needed to start |
| **Messages in the trial** | Simulator always. Real WhatsApp and SMS only after email verification, **capped at 50 messages** in the trial, so trial costs stay small |
| **Plan** | One monthly plan per shop to start. **Price: you decide** (e.g. KSh ____ a month), with a lower price for paying 12 months up front |
| **How shops pay** | **M-Pesa:** a "Pay now" button sends an M-Pesa prompt to the owner's phone, using the Daraja STK push that's already built, into **your** Till or Paybill. A receipt by email and in Settings → Plan and billing |
| **Reminders** | 3 days before the trial or month ends, then on the day (email, and a line on Home) |
| **If not paid** | **7-day grace period** (everything works, with a reminder). Then **read-only**: they can see everything and pay, but nothing new is logged or sent. **Nothing is ever deleted** for non-payment; the data stays 90 days, then the owner is warned before deletion |
| **Invited shops** | The team can set "paid until" by hand, for cash or bank deals |

**Settings → Plan and billing** (owner only) shows the plan, trial or paid-until date, a **Pay now** button, and past receipts.

Later, not in this phase: several plans (for example a cheaper one without WhatsApp), card payments, and automatic monthly M-Pesa payments.

## 6b. Found while designing this (separate fix, later)

Replies from customers are matched to a shop by phone number. If two **real** shops have the same customer, that customer's replies aren't filed under either shop today. To fix before many shops share customers: match the reply to the shop that last messaged that number.

## 7. Not in this phase

- Card payments.
- Several plans.
- Phone verification by SMS or WhatsApp.
- Per-shop WhatsApp numbers and M-Pesa tills for customer payments: planned in `docs/going-live-messaging.md` §6, before the second real shop.
- The landing pages: Phase 8. Its "Start free trial" button opens the sign-up built here.

## 8. Data changes

- `Shop`:
  - `status`: demo, trial, active, grace or read-only;
  - `trial_ends`, `paid_until`, `setup_steps_done`;
  - `email_verified`, `messages_used_in_trial`.
- `Invitation`: shop, email or phone, role, one-time token (stored hashed), expiry, used at.
- `PlanPayment`: shop, amount, M-Pesa code, period covered. Recorded from the M-Pesa confirmation, like deposits.

## 9. Tests and UAT

- **Automated tests:**
  - sign-up with the bot trap and limits;
  - verification turns real messages on;
  - an invitation link works once and expires;
  - a demo shop never sends real messages;
  - setup steps tick off;
  - the trial ends, then grace, then read-only;
  - paying by M-Pesa (simulated) extends the plan;
  - read-only blocks new records but allows payment.
- **New UAT rows:**
  - sign up as a new shop;
  - explore the demo;
  - complete setup with the Excel template;
  - accept an invitation;
  - pay for a month in the M-Pesa sandbox;
  - let a trial lapse (with a test clock).

## 10. Order of work

1. Shop status, plan dates and the read-only rule.
2. Invitations, for owners and staff.
3. The setup guide (six steps) and the line on Home.
4. Self sign-up, with Turnstile, limits and email verification.
5. The demo shop.
6. Plan and billing with M-Pesa.
7. Tests, your UAT, sign-off, merge.
