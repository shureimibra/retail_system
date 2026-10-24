# Set up real channels on free accounts

This connects Retail OS to real WhatsApp, SMS, email and M-Pesa **without paying**. Each free account has limits (listed below), which is fine for testing with yourself and a few staff, but not for real customers.

When you're ready to pay, you change values in `.env`. No code changes.

You only need the channels you want; any channel you skip stays on the simulator. After each step, open **Settings → Messaging** (or **Payments**) and use **Send a test message**.

> Never commit `.env`. It holds secrets, and git already ignores it.

---

## 0. A public address for your laptop (needed for replies, photos and M-Pesa)

Meta, Twilio and Safaricom send replies and confirmations over the internet, so they need to reach your laptop. A free Cloudflare quick tunnel gives it a temporary `https` address. It needs no account.

1. Install `cloudflared`: on Windows, `winget install --id Cloudflare.cloudflared`.
2. Start the app as usual: `python manage.py runserver 8000`.
3. In another terminal, run `cloudflared tunnel --url http://localhost:8000`. It prints an address like `https://random-words.trycloudflare.com`.
4. In `.env`, set:
   ```
   SITE_URL=https://random-words.trycloudflare.com
   ALLOWED_HOSTS=localhost,127.0.0.1,.trycloudflare.com
   ```
   Then restart `runserver`.

**The address changes every time the tunnel restarts.** When it does, update `SITE_URL`, plus the webhook addresses in Meta and Twilio.

---

## 1. WhatsApp: Meta's free test number

**Limits:**
- Sends only to the few phone numbers you add as recipients (Meta allows up to 5).
- The temporary access token lasts 24 hours.
- Each automatic message needs an approved template.

1. Go to developers.facebook.com, log in with Facebook, and choose **My Apps → Create app**, type **Business**.
2. In the app, add the **WhatsApp** product. Meta creates a free **test phone number**.
3. Under **WhatsApp → API Setup**:
   - Add **your own phone** under "To", and confirm the code WhatsApp sends you.
   - Copy the **Temporary access token** and the **Phone number ID**.
4. Under **App settings → Basic**, copy the **App secret**.
5. In `.env`:
   ```
   WHATSAPP_PROVIDER=whatsapp_cloud
   WHATSAPP_TOKEN=<temporary access token>
   WHATSAPP_PHONE_NUMBER_ID=<phone number ID>
   WHATSAPP_APP_SECRET=<app secret>
   WHATSAPP_VERIFY_TOKEN=<any long random text you choose>
   ```
6. **Replies:** in **WhatsApp → Configuration → Webhook**:
   - **Callback URL:** `https://<your tunnel>/notifications/webhooks/whatsapp/`
   - **Verify token:** the same text as `WHATSAPP_VERIFY_TOKEN`
   - Then subscribe to the **messages** field.
7. **Templates:** create the seven templates in `docs/whatsapp-templates.md`. When each is approved, add its name to `.env` (for example `WHATSAPP_TEMPLATE_RESTOCK_ALERT=restock_alert`).
8. **Test it:** use Settings → Messaging → **Send a test message** → WhatsApp. It uses Meta's ready-made "hello world" template, so it works before your own templates are approved.

**The token lasts 24 hours.** When it expires, sending fails with an authentication error: copy a fresh token into `.env`. For a token that doesn't expire, create a System User in Meta Business settings (also free).

## 2. SMS: Twilio trial

**Limits:**
- Your trial includes a set number of free SMS (about 100).
- Up to 5 verified numbers, at most 50 messages a day.
- Each SMS starts "Sent from a Twilio Trial account".
- **The trial ends 30 days after sign-up.**

1. Your Twilio values are already in `.env`. Check they're there and set:
   ```
   SMS_PROVIDER=twilio
   ```
2. In the Twilio console, go to **Phone Numbers → Verified Caller IDs** and add each phone that should receive test SMS.
3. **Replies and delivery receipts:** in **Phone Numbers → Manage → your number → Messaging**, set "A message comes in" to `https://<your tunnel>/notifications/webhook/` (HTTP POST). Retail OS asks for delivery receipts automatically when `SITE_URL` is https.

**Instead, Africa's Talking sandbox** (messages appear only in their web simulator): `SMS_PROVIDER=africastalking`, `AFRICASTALKING_USERNAME=sandbox`, `AFRICASTALKING_API_KEY=<sandbox key>`.

## 3. Email: Brevo free plan

**Limits:** 300 emails a day. Emails carry Brevo's name in the footer.

1. Sign up at brevo.com (free plan). Under **Senders**, add and verify the email address you'll send from.
2. Open **SMTP & API → SMTP**. Copy the **SMTP login** and create an **SMTP key**.
3. In `.env`:
   ```
   EMAIL_PROVIDER=email
   EMAIL_HOST=smtp-relay.brevo.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=<SMTP login>
   EMAIL_HOST_PASSWORD=<SMTP key>
   DEFAULT_FROM_EMAIL=Kimathi Street Store <the address you verified>
   ```

**Instead, Resend** (100 a day, 3,000 a month): host `smtp.resend.com`, port 587, user `resend`, password your API key.

## 4. M-Pesa: Daraja sandbox

**Limits:** test money only. It uses Safaricom's test business number (174379) and test phones. **No real payments.** Live payments later need your own Till or Paybill approved by Safaricom.

1. Sign up at developer.safaricom.co.ke and create an app with **Lipa na M-Pesa Sandbox** (M-Pesa Express) enabled.
2. Copy the app's **Consumer Key** and **Consumer Secret**.
3. In `.env`:
   ```
   MPESA_ENV=sandbox
   MPESA_CONSUMER_KEY=<consumer key>
   MPESA_CONSUMER_SECRET=<consumer secret>
   MPESA_CALLBACK_TOKEN=<any long random text you choose>
   ```
   Leave `MPESA_SHORTCODE` and `MPESA_PASSKEY` unset: the sandbox defaults are built in.
4. With the tunnel running and `SITE_URL` set, open a conversation. The deal panel shows **Ask for M-Pesa payment**.
5. **The sandbox prompt goes to the phone number you enter.** Safaricom's simulator in the Daraja portal shows what happens. If the confirmation doesn't arrive (for example the tunnel was down), Retail OS asks M-Pesa directly after 30 seconds.

---

## When you decide to go live (costs money)

| Channel | What changes |
|---|---|
| WhatsApp | Verify your business with Meta, add your real number, use a permanent token. Meta charges per message. |
| SMS | Upgrade Twilio, or top up Africa's Talking and set `AFRICASTALKING_SANDBOX=False`. Register a sender ID. |
| Email | Upgrade Brevo, or keep the free plan if 300 a day is enough. |
| M-Pesa | Get your Till or Paybill approved for Daraja; set `MPESA_ENV=production`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`. |
| Hosting | A permanent server and address replaces the tunnel. |
