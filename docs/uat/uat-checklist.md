# UAT checklist: the whole missed-sale journey

Run these on your laptop with real WhatsApp (Twilio sandbox) and your own phone. Each scenario was first run by me, as automated tests on the same screens (`intents/test_uat.py`, scenarios S01–S18) and in the browser. All passed on 26 Oct 2026.

**Before you start**
- `runserver` and the Cloudflare tunnel are running, and `SITE_URL` in `.env` is the tunnel's address.
- Your phone has joined the Twilio WhatsApp sandbox (send the join code to +1 415 523 8886 within the last 24 hours).
- Sign in as the owner. For S16, also create a cashier in Settings → Team and roles.
- Use your own number for the customer in every scenario.
- The sample shop already has some customers. One of them, **Jane Smith**, has a deposit on Adidas Ultraboost 42 / Grey, so Home shows **Reserved 1** and one unit of that size is held for her. That's sample data, not your test.
- **Save** takes you back to the page you started from (Home, Waiting, a conversation…). **Save, same customer, another item** keeps you on the form.
- In a third terminal, run `python manage.py process_due --every 15`. On a laptop nothing else sends reminders, retries failed messages or expires old requests (in production a background worker does it). For S11–S13 you can also run `python manage.py process_due` once whenever you like.

## How statuses move

Nobody sets a status by hand. Each one changes because of a real action:

| Status | Moves when | Who |
|---|---|---|
| Open | You log the missed sale (Log missed sale) | Staff |
| On order | To order (or Waiting) → tick → **Mark as ordered** | Owner or manager |
| Back in stock → Notified | You **Receive stock** on the product page: a unit is held and the WhatsApp goes out | **Automatic** after receiving |
| In conversation | The customer replies on WhatsApp | **Automatic** |
| Reserved | **Save deposit and reserve** in the conversation (or M-Pesa confirms it) | Staff (or M-Pesa) |
| Recovered | **Paid in full** in the conversation | Staff |
| Declined | **Close as declined** (conversation or item page) | Staff |
| Expired | No reply after the reminders, replied but no deposit before the hold ends, not collected by the pickup day, or 30 days with nothing ordered | **Automatic** (`process_due`) |

**Price too high / over budget** (one reason) customers skip ordering. They move to Notified when you **lower the price** on the product page.

Every item in **Waiting** says its **next step** and has a button for it.

## Scenarios

| # | Scenario | Do this | You should see |
|---|---|---|---|
| S01 | Size missing, all the way to paid | Log missed sale → Didn't buy → Adidas Ultraboost → a size with **0 in stock** → Size missing → your number → Save. Then To order → tick it → Mark as ordered (set a date). Then Waiting → **Receive stock** → 1 → Receive. Reply "Yes" on WhatsApp. In the chat: deposit 5000, then **Paid in full**. | To order lists it. After receiving: the "back in stock" WhatsApp arrives. Your reply appears **without refreshing**. Deposit: a receipt arrives, status Reserved. Paid in full: Recovered, stock down by 1, Home shows the money recovered. |
| S02 | A size that's in stock | Log missed sale → pick a size showing **"3 in stock · sell it"** → Size missing | A warning: "This one is in stock… Sell it now". Saving is refused. Choosing **Price too high** for it is allowed and does not appear on To order. |
| S03 | A colour you've never stocked | Log missed sale → item → **Not in the list? Type the size and colour** → 42 / Black → Colour missing → Save | The new option appears on To order with 0 in stock. Receiving it messages you. Typing "black" again reuses it. |
| S04 | An item the shop doesn't sell | Log missed sale → Item → **+ An item the shop doesn't have yet** → name, type, price, size/colour → Out of stock → Save | It appears in Products (as a cashier: "Needs review") and on To order. If the owner switched off "Cashiers can add products", a cashier is told to ask. |
| S05 | Any size will do | Log missed sale → Any or not sure → Out of stock → Save. Receive any size. | You're messaged when **any** size arrives. |
| S06 | Price too high / over budget | Log missed sale → an in-stock size → **Price too high / over budget** → Save. Product page → Change price **up**, then **down**. | Raising it sends nothing; lowering it sends the price-drop WhatsApp. Receiving stock does not message price customers. |
| S07 | Something else | Log missed sale → choose the item (or **+ An item the shop doesn't have yet**, e.g. Handbag) → Something else, without a note → Save; then add a note → Save | An item is always needed (it gives the price for recovered money). Without a note it's refused. Waiting shows "Next: Follow up with them yourself". |
| S08 | Customer doesn't want WhatsApp | Log missed sale → in step 3, **untick** "The customer agreed to a WhatsApp when it's back" → Save. Then Receive the stock. | No WhatsApp is sent; one unit is put aside for them. Waiting and the item page say they didn't agree to messages: call them. (A customer who **replies** No to a message is different: open the chat → **Close as declined**.) |
| S09 | Two customers, one unit | Log the same size for two numbers. Receive 1. Close the first as declined. | The first person gets the message, the second keeps waiting. After the decline, the second person is messaged automatically. |
| S10 | Customer replies STOP | After the back-in-stock message, reply **STOP** | No more reminders. The customer shows "Opted out". |
| S11 | No reply at all | Receive stock, don't reply, run `python manage.py process_due` on later days (or wait) | Reminders go out on days 2, 4 and 7. On day 8 it expires and the unit goes to the next customer. |
| S12 | Replied, then went quiet | Reply "Maybe" and pay nothing | When the 8-day hold ends it expires and the next customer is messaged. With a deposit it stays Reserved. |
| S13 | Pickup day passes | Take a deposit, then let the pickup date pass | It stays Reserved (money was paid) and shows in Home → Needs you now as "pickup is overdue". |
| S14 | They want another size | In the chat → Change item → another size | The held unit moves to the new size; the old size goes back on sale. |
| S15 | Same customer, another item | Log missed sale → Save, same customer, another item | Their number is already filled in; it counts as **one** visit. On the same screen, **They bought after all** counts a sale instead. |
| S16 | Cashier | Sign in as the cashier | They can use Log missed sale, reply and take deposits. To order, Reports, Payments settings and Receive stock are refused. |
| S17 | Live chat | Keep a conversation open and reply from your phone; then start typing and reply again | New replies appear within about 5 seconds, with no refresh. While you type, your draft is kept. "Send the check-in message instead" is always available. |
| S18 | Waiting tells you what's next | Open Waiting → All records | Every item has "Next: …" and a button (To order, Receive stock, Reply, Open deal…), and shows the stock now. |
| S19 | Needs you now | Reply from your phone, open the chat but don't answer; check Home. Then answer it. | The customer stays in **Needs you now** ("waiting for your answer") until you reply, even after reading it. Replies come first, then overdue pickups, promises due, failed messages. Only 5 show; the rest are under **Show all**. **Dismiss** hides a failed-message alert only: the customer stays in Waiting. |
| S20 | Conversations order | Get replies from two numbers at different times | The newest message is at the top, like WhatsApp, read or not. |
| S21 | Product categories | Add product → Type Shoes, then Clothing, then Other | Only that type's categories are offered; "Or a new category" adds one; **Other** asks what it is (e.g. Watches). Missing fields are listed at the top. |
| S22 | Many sizes and colours | A product page → Add sizes and colours → tick 45 and 46, type "Black, White" → Add | 4 new options with 0 in stock appear in the grid; adding one that exists is skipped. |
| S23 | Photo and logo | Edit a product: choose a new photo; then tick Remove. Settings → Shop details: upload a wide logo | The new photo replaces the old (no "clear and change" error); Remove clears it. The logo becomes a square and shows in the sidebar, the top bar, Log missed sale and the sign-in page. |
| S24 | Dates | Mark as ordered with a year like 275760, or more than a year ahead | The date box snaps back into range, and the server refuses it with a clear message. |
| S25 | Import stock from Excel | Products → **Import stock** → Download Excel. Change a few "In stock" numbers (raise one that a customer is waiting for), add a row for a new size, and one for a new item with no type. Upload | A preview lists every change and "Row N can't be used" for the item with no type. Nothing changes until **Save these changes**. After saving: the counts match, the new size appears, and the waiting customer gets the WhatsApp. |
| S26 | Customer asks through the shop link | Settings → **Shop link** → Open (or scan the QR code with your phone through the tunnel). Pick an item, a size with 0 in stock, your number → Send | "Thank you". The request is in Waiting with a **Shop link** tag, and doesn't count as a walk-in. Receiving that size messages you. A size that's in stock comes in as "Something else" with "It's in stock: invite them in". Switching the link off shows a closed page. |
| S27 | Connect a POS (API key) | Settings → **Connections** → Create a key "Test", Read and change stock → copy it. Then run the `curl` lines from `docs/api.md` (stock **add**, then a **sale**, then the same sale again with the same Idempotency-Key). Revoke the key | The key is shown only once. **add** messages a waiting customer; the sale takes stock down; sending the same sale again changes nothing. After revoking, the key gets 401. |

## If something doesn't match

Note the scenario number, what you did, and what you saw (a screenshot helps). For WhatsApp problems I can read Twilio's delivery log for you.
