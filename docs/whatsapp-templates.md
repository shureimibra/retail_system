# WhatsApp message templates

WhatsApp only lets a business start a conversation with a **template Meta has approved**. Retail OS sends seven automatic messages, so you create seven templates in Meta's WhatsApp Manager and put each approved name in `.env`.

Until a template is approved, that message goes by SMS instead, so nothing silently fails.

For each template below:
- **Category:** Utility
- **Language:** English (`en`), matching `WHATSAPP_TEMPLATE_LANGUAGE=en`
- **Name:** use the name shown; you can choose another, as long as `.env` matches
- **Body:** paste it exactly, keeping the `{{1}}`, `{{2}}`… placeholders in the same order. Retail OS fills them in that order (`notifications/compose.py`, `template_params`).

Meta asks for an example value for each placeholder when you submit. The examples below work.

---

## 1. Back in stock (with the item's photo)
- **Name:** `restock_alert` → `.env`: `WHATSAPP_TEMPLATE_RESTOCK_ALERT=restock_alert`
- **Header:** Image (example: any product photo)
- **Body:**
  > Hi {{1}}, the {{2}} you asked about on {{3}} is back at {{4}}. We're holding one for you until {{5}}. Reply YES to keep it, or STOP to opt out.
- **Examples:** Jane · Adidas Ultraboost in 42 / Grey · Tue 13 Oct · Kimathi Street Store · Fri 30 Oct

## 2. Price drop (with the item's photo)
- **Name:** `price_drop` → `WHATSAPP_TEMPLATE_PRICE_DROP=price_drop`
- **Header:** Image
- **Body:**
  > Good news {{1}}: the {{2}} is now {{3}} (was {{4}}) at {{5}}. Reply YES to reserve it, or STOP to opt out.
- **Examples:** Ali · Leather Messenger Bag · KSh 12,900 · KSh 14,900 · Kimathi Street Store

## 3. Deposit receipt
- **Name:** `deposit_receipt` → `WHATSAPP_TEMPLATE_DEPOSIT_RECEIPT=deposit_receipt`
- **Body:**
  > Thank you {{1}}. We received {{2}} for the {{3}}. Balance {{4}}. Please pick it up by {{5}}.
- **Examples:** Jane · KSh 5,000 · Adidas Ultraboost in 42 / Grey · KSh 13,700 · Tue 27 Oct

## 4. First reminder
- **Name:** `reminder_1` → `WHATSAPP_TEMPLATE_REMINDER_1=reminder_1`
- **Body:**
  > Hi {{1}}, a reminder that the {{2}} is waiting for you at {{3}}. Reply YES to keep it, or STOP to opt out.

## 5. Second reminder
- **Name:** `reminder_2` → `WHATSAPP_TEMPLATE_REMINDER_2=reminder_2`
- **Body:**
  > Hi {{1}}, we're still holding the {{2}} for you until {{3}}. Reply YES to keep it, or STOP to opt out.

## 6. Last call
- **Name:** `reminder_3` → `WHATSAPP_TEMPLATE_REMINDER_3=reminder_3`
- **Body:**
  > Last call, {{1}}: we can hold the {{2}} until tomorrow, then it goes back on sale. Reply YES to keep it.

## 7. Check-in (when the 24-hour reply window has closed)
- **Name:** `check_in` → `WHATSAPP_TEMPLATE_CHECK_IN=check_in`
- **Body:**
  > Hi {{1}}, this is {{2}} about the {{3}}. Reply to this message and we'll help you.

---

**If you change a template's wording in Meta,** change it in `notifications/compose.py` too. The text shown in Conversations comes from there; the text the customer sees comes from Meta.
