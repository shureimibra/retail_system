# Phase 4 design note: real channels, still free

**Status:** draft for the owner's approval · 23 Oct 2026
**Owner's rule (23 Oct):** nothing paid for now. Everything in this phase runs on free test accounts, sandboxes or trial credit. Going live later is a change of `.env` values and account approvals, not new code.

## 1. What this phase delivers

Until now, every message stayed on this computer (the simulator). After Phase 4:
- **WhatsApp:** the restock message, with the item's photo, reaches **your own phone**, and your reply comes back into Conversations.
- **SMS:** the fallback reaches real phones on the Twilio trial.
- **M-Pesa:** from the deal panel, staff tap **Ask for M-Pesa payment**. The customer's phone shows the M-Pesa PIN prompt, and when they pay, the deposit or full payment **records itself** with the M-Pesa code. This runs on Safaricom's free sandbox, which uses test numbers and test money.

Free test accounts limit who can receive messages: only a few phones you register yourself. That's fine for testing; it isn't for real customers yet.

## 2. The free accounts

| Channel | Free route | Its limit | What you do (all free, no card) |
|---|---|---|---|
| WhatsApp | **Meta WhatsApp Cloud API test number** | Sends only to up to 5 phone numbers you add; message templates still need Meta's review | Create a Meta developer account and app, add WhatsApp, add your phone as a recipient, copy the token and number ID into `.env` |
| SMS | **Twilio trial** (your new account) | Trial credit only; sends only to numbers verified in Twilio; each SMS starts "Sent from your Twilio trial account" | Verify your phone in the Twilio console. Already in `.env` |
| SMS (option) | Africa's Talking sandbox | Messages appear only in their web simulator, not on phones | Already built; stays available |
| Email | Mailpit on this computer | Never leaves the computer | Optional: run Mailpit |
| M-Pesa | **Safaricom Daraja sandbox** | Test business number and test phones; no real money moves | Create a Daraja account and a sandbox app, and copy the consumer key and secret into `.env` |
| Webhooks | **Cloudflare quick tunnel** (`cloudflared`) | The web address changes each time it restarts | Install `cloudflared` once; I'll give the exact command |

**Why a tunnel:** replies, delivery receipts and M-Pesa confirmations come from Meta, Twilio and Safaricom over the internet. A tunnel gives your laptop a temporary public `https` address while it runs. Real hosting is a later step, chosen when you're ready to pay for it.

## 3. What gets built

**3.1 WhatsApp templates done properly**
- Today, only the restock message has a template, and it squeezes the whole text into one variable, which Meta usually rejects.
- Each automatic message (restock with photo, price drop, receipt, three reminders, check-in) gets its own template with named parts: name, item, shop, date.
- `docs/whatsapp-templates.md` holds the exact wording to paste into Meta for review.
- Until a template is approved, that message falls back to SMS, so nothing silently fails.

**3.2 Twilio for SMS and replies**
- Send through the trial.
- Receive SMS replies and delivery receipts on the existing webhook, with Twilio's signature check.

**3.3 M-Pesa payment prompt (Daraja STK push)**
- **Deal panel:** **Ask for M-Pesa payment** takes an amount (the deposit, or the balance) and the phone, prefilled from the customer.
- **While waiting:** the panel shows "Waiting for Jane to enter her PIN…" and checks again every few seconds.
- **When paid:** the payment is recorded through the same service as a typed-in deposit. The item becomes Reserved, or Recovered when it's paid in full, the receipt message goes out, and the M-Pesa code is saved.
- **If cancelled, timed out or failed:** the panel says so plainly and offers to try again. Nothing is recorded.
- **Safety:**
  - The callback address carries a secret.
  - A callback only counts if it matches a request we started, for the same amount.
  - Each confirmation is recorded once, even if Safaricom sends it twice.
  - The amount can never exceed the balance.
- **Typing a payment by hand** stays available (cash, card, or M-Pesa sent another way).

**3.4 Settings, so you can see it's connected**
- **Settings → Messaging:** each channel shows "Simulator", "Test account" or "Not set up", and has a **Send a test message to my phone** button. You see it arrive, or get the provider's error in plain words.
- **Settings → Payments (new, owner):** M-Pesa shows Sandbox, Live or Off, plus "How customers pay you".
- **Unchanged:** keys still live in `.env`, never on a page.

**3.5 Set-up guide**
`docs/setup-free-channels.md`: step by step for each free account, the tunnel, and which `.env` keys to fill in. `.env.example` lists every key.

## 4. What stays the same
- Consent, STOP, duplicate checks, the 24-hour WhatsApp rule and fallbacks all still go through the one gateway.
- Tests never contact a real provider: they replace every key and connection with fakes.
- No Redis or worker is needed. Retries and follow-ups keep running through `process_due`.

## 5. Not in this phase
- Paid or live accounts, and real hosting. These come when you decide to pay; the note on them will list exactly what changes.
- Matching payments customers send straight to your Till or Paybill. That needs a live Till.
- Per-shop keys stored in the database. Still one shop per installation.

## 6. Open questions
1. **WhatsApp test route:** the Meta test number (recommended, and the same API as production later), or the Twilio WhatsApp sandbox (customers must first send a join code, and it lapses after 72 hours)?
2. **SMS:** the Twilio trial to real phones (recommended), or the Africa's Talking sandbox (web simulator only)?
3. **M-Pesa sandbox payment prompt:** build it in this phase (recommended), or leave M-Pesa for later?

## Done when
- [ ] A restock message with the photo arrives on your phone over the Meta test number; your reply shows in Conversations.
- [ ] An SMS fallback arrives on your phone over the Twilio trial.
- [ ] An M-Pesa sandbox payment from the deal panel records the deposit by itself, with the receipt sent.
- [ ] Settings shows each connection's state, and the test-message buttons work.
- [ ] All tests pass on PostgreSQL and SQLite, with no test touching a real provider.
