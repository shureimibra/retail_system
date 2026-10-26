# UAT checklist: the whole missed-sale journey

Run these on your laptop with real WhatsApp (Twilio sandbox) and your own phone. Each scenario was first run by me, as automated tests on the same screens (`intents/test_uat.py`, scenarios S01–S18) and in the browser. All passed on 26 Oct 2026.

**Before you start**
- `runserver` and the Cloudflare tunnel are running, and `SITE_URL` in `.env` is the tunnel's address.
- Your phone has joined the Twilio WhatsApp sandbox (send the join code to +1 415 523 8886 within the last 24 hours).
- Sign in as the owner. For S16, also create a cashier in Settings → Team and roles.
- Use your own number for the customer in every scenario.

## How statuses move

Nobody sets a status by hand. Each one changes because of a real action:

| Status | Moves when | Who |
|---|---|---|
| Open | You log the missed sale in Floor mode | Staff |
| On order | To order (or Waiting) → tick → **Mark as ordered** | Owner or manager |
| Back in stock → Notified | You **Receive stock** on the product page: a unit is held and the WhatsApp goes out | **Automatic** after receiving |
| In conversation | The customer replies on WhatsApp | **Automatic** |
| Reserved | **Save deposit and reserve** in the conversation (or M-Pesa confirms it) | Staff (or M-Pesa) |
| Recovered | **Paid in full** in the conversation | Staff |
| Declined | **Close as declined** (conversation or item page) | Staff |
| Expired | No reply after the reminders, replied but no deposit before the hold ends, not collected by the pickup day, or 30 days with nothing ordered | **Automatic** (`process_due`) |

Price-too-high and over-budget customers skip ordering. They move to Notified when you **lower the price** on the product page.

Every item in **Waiting** says its **next step** and has a button for it.

## Scenarios

| # | Scenario | Do this | You should see |
|---|---|---|---|
| S01 | Size missing, all the way to paid | Floor mode → Didn't buy → Adidas Ultraboost → a size with **0 in stock** → Size missing → your number → Save. Then To order → tick it → Mark as ordered (set a date). Then Waiting → **Receive stock** → 1 → Receive. Reply "Yes" on WhatsApp. In the chat: deposit 5000, then **Paid in full**. | To order lists it. After receiving: the "back in stock" WhatsApp arrives. Your reply appears **without refreshing**. Deposit: a receipt arrives, status Reserved. Paid in full: Recovered, stock down by 1, Home shows the money recovered. |
| S02 | A size that's in stock | Floor mode → pick a size showing **"3 in stock · sell it"** → Size missing | A warning: "This one is in stock… Sell it now". Saving is refused. Choosing **Price too high** for it is allowed and does not appear on To order. |
| S03 | A colour you've never stocked | Floor mode → item → **Not in the list? Type the size and colour** → 42 / Black → Colour missing → Save | The new option appears on To order with 0 in stock. Receiving it messages you. Typing "black" again reuses it. |
| S04 | An item the shop doesn't sell | Floor mode → Item → **+ An item the shop doesn't have yet** → name, type, price, size/colour → Out of stock → Save | It appears in Products (as a cashier: "Needs review") and on To order. If the owner switched off "Cashiers can add products", a cashier is told to ask. |
| S05 | Any size will do | Floor mode → Any or not sure → Out of stock → Save. Receive any size. | You're messaged when **any** size arrives. |
| S06 | Price too high / over budget | Floor mode → an in-stock size → Over budget → Save. Product page → Change price **up**, then **down**. | Raising it sends nothing; lowering it sends the price-drop WhatsApp. Receiving stock does not message price customers. |
| S07 | Something else | Floor mode → Something else, without a note → Save; then add a note → Save | Without a note it's refused. Waiting shows "Next: Follow up with them yourself". |
| S08 | Customer said no to messages | Floor mode → untick the WhatsApp consent → Save. Receive the stock. | No message is sent; a unit is held. The item page says "didn't agree to messages. Call them." |
| S09 | Two customers, one unit | Log the same size for two numbers. Receive 1. Close the first as declined. | The first person gets the message, the second keeps waiting. After the decline, the second person is messaged automatically. |
| S10 | Customer replies STOP | After the back-in-stock message, reply **STOP** | No more reminders. The customer shows "Opted out". |
| S11 | No reply at all | Receive stock, don't reply, run `python manage.py process_due` on later days (or wait) | Reminders go out on days 2, 4 and 7. On day 8 it expires and the unit goes to the next customer. |
| S12 | Replied, then went quiet | Reply "Maybe" and pay nothing | When the 8-day hold ends it expires and the next customer is messaged. With a deposit it stays Reserved. |
| S13 | Pickup day passes | Take a deposit, then let the pickup date pass | It stays Reserved (money was paid) and shows in Home → Needs you now as "pickup is overdue". |
| S14 | They want another size | In the chat → Change item → another size | The held unit moves to the new size; the old size goes back on sale. |
| S15 | Same customer, another item | Floor mode → Save, same customer, another item | Their number is already filled in; it counts as **one** visit. |
| S16 | Cashier | Sign in as the cashier | They can use Floor mode, reply and take deposits. To order, Reports, Payments settings and Receive stock are refused. |
| S17 | Live chat | Keep a conversation open and reply from your phone; then start typing and reply again | New replies appear within about 5 seconds, with no refresh. While you type, your draft is kept. "Send the check-in message instead" is always available. |
| S18 | Waiting tells you what's next | Open Waiting → All records | Every item has "Next: …" and a button (To order, Receive stock, Reply, Open deal…), and shows the stock now. |

## If something doesn't match

Note the scenario number, what you did, and what you saw (a screenshot helps). For WhatsApp problems I can read Twilio's delivery log for you.
