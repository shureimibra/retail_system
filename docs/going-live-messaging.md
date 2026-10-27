# Going live: WhatsApp, SMS, email and M-Pesa

For the owner, when moving from free test accounts to real customers. Everything here is **a plan**. Each channel already works in Retail OS on a free test account (see `docs/setup-free-channels.md`). Going live is mostly **accounts, approvals and `.env` values**, not new code. The one real design decision is in section 6.

**Prices change.** No prices are written here on purpose. Check each provider's pricing page on the day you decide, and keep a note of what you agreed to.

## 1. The order to do it in

Approvals take days to weeks, so start them early, in parallel:
1. **Business documents ready:** registration certificate, KRA PIN, a business email on your own domain, and a website. The landing page counts.
2. **WhatsApp (Meta) business verification:** the slowest.
3. **SMS sender ID registration:** also slow.
4. **M-Pesa go-live with Safaricom.**
5. **Email domain set-up:** quick.

## 2. WhatsApp: the main channel

**What changes from the test number:**
- **Meta Business verification** of your business (documents from step 1).
- **A real phone number** for WhatsApp Business. It must not be in use on the WhatsApp app at the same time.
- **Display name approval:** the name customers see.
- **Message templates approved.** Every message the shop starts (restock, price drop, receipt, reminders, check-in) needs an approved template. The wording to submit is in `docs/whatsapp-templates.md`. Replies inside 24 hours of a customer's message don't need templates.
- **Costs:** Meta charges per template message sent, by country and message type. Replies inside the 24-hour window are cheaper or free. Check Meta's current WhatsApp pricing.

**Two ways to connect, both already built:**

| Route | `.env` | When to choose it |
|---|---|---|
| **Meta Cloud API directly** | `WHATSAPP_PROVIDER=whatsapp_cloud`, `WHATSAPP_TOKEN` (a permanent system-user token, not the 24-hour test one), `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, the `WHATSAPP_TEMPLATE_*` names | Cheapest: only Meta's charges. Recommended |
| **Through Twilio** | `WHATSAPP_PROVIDER=twilio_whatsapp`, `TWILIO_WHATSAPP_FROM=<your approved number>` | Simpler set-up through Twilio's console, but Twilio adds its own fee per message on top of Meta's |

In Meta's app settings, set the webhook to `https://<your domain>/notifications/webhooks/whatsapp/` with your verify token.

## 3. SMS: the fallback

SMS is used when WhatsApp can't reach someone.

**Lesson from testing:** Twilio's US numbers are **refused by Kenyan networks** (error 21612). For Kenya, use **Africa's Talking**, which is already built in:
- Open a live account and top it up. It's prepaid, per message.
- Apply for an **alphanumeric sender ID** (the shop or brand name, e.g. "KIMATHI") through Africa's Talking. It's approved by the mobile networks and can take a while. Until then, messages come from a shared number.
- `.env`:
  - `SMS_PROVIDER=africastalking`
  - `AFRICASTALKING_USERNAME=<your live app username>`
  - `AFRICASTALKING_API_KEY`
  - `AFRICASTALKING_SANDBOX=False`
  - `AFRICASTALKING_SENDER_ID=<approved ID>`
  - `AFRICASTALKING_WEBHOOK_TOKEN` (long, random)

Twilio SMS stays available for other countries later.

## 4. Email: receipts and back-up messages

- **Provider:**
  - Brevo (has a free plan with a daily limit, enough to start);
  - or Amazon SES (pay per email, very cheap at volume, more set-up).
  
  Both work through the existing SMTP settings (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS=True`), with `EMAIL_PROVIDER=email`.
- **Your own domain:** send from `no-reply@yourbrand.co.ke`, never a Gmail address. Add the **SPF, DKIM and DMARC** DNS records the provider gives you, or emails land in spam.
- `DEFAULT_FROM_EMAIL=Your Brand <no-reply@yourbrand.co.ke>`

## 5. M-Pesa: deposits and payments

**What's needed:**
- **A Till (Buy Goods) or Paybill number**, in the business's name.
- **Daraja "Go Live":** in the Safaricom developer portal, request go-live for your app against that Till or Paybill. The business's M-Pesa administrator approves it. Safaricom then gives you the **production passkey**.
- `.env`:
  - `MPESA_ENV=production`
  - `MPESA_CONSUMER_KEY` and `MPESA_CONSUMER_SECRET` (production app)
  - `MPESA_SHORTCODE=<Till or Paybill>`
  - `MPESA_PASSKEY`
  - `MPESA_TRANSACTION_TYPE=CustomerBuyGoodsOnline` for a Till, or `CustomerPayBillOnline` for a Paybill
  - `MPESA_CALLBACK_TOKEN` (long, random)
- **Costs:** Safaricom's normal M-Pesa transaction charges for your Till or Paybill tariff. There's no extra charge from Retail OS.
- **First test with real money:** a small amount (KSh 1–10) to your own phone. Check it records itself as a deposit with the M-Pesa code.

## 6. The decision to make first: whose accounts?

Today **one set of keys** (in `.env`) serves the whole system. That's right for **one shop**. When Retail OS serves many shops, each shop will want:
- **its own M-Pesa Till**, so money goes straight to the shop, never through you;
- **its own WhatsApp number and name**, so customers see "Kimathi Street Store", not your brand.

That means moving these keys from `.env` into each shop's **Settings → Messaging / Payments**, stored encrypted. It's a contained piece of work: a design note, then the build.

**Recommendation:**
- Launch with the first shop on the `.env` set-up.
- Build per-shop accounts before the second shop joins.
- SMS and email can stay on your platform accounts, with the shop's name as the sender, and the cost passed on in your subscription price.

## 7. Checklist on go-live day

- [ ] All providers' webhooks point to the real domain (no tunnel).
- [ ] `SIMULATOR_ENABLED=False`, `DEBUG=False`.
- [ ] Send one of each message to your own phone: restock (with photo), price drop, deposit receipt, a reminder. Each arrives, and each reply comes back into Conversations.
- [ ] One real M-Pesa deposit of a small amount records itself.
- [ ] Top-up alerts are set on Africa's Talking and Twilio, so balances never run out silently.
