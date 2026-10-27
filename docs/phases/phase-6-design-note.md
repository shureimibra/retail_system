# Phase 6 design note: an assistant for the owner, free

**Status:** approved by the owner 27 Oct 2026 · built on `phase-6/assistant` (after Phase 5b)
**Owner's decisions (27 Oct 2026):**
- The assistant must be free for now. It's an **Ask box inside Retail OS that uses no AI API**: it answers set questions from the shop's own data, so no customer data leaves the system and nobody needs a subscription.
- No MCP tool for now.
- Reply drafts: free smart quick replies now, real AI later.

**Later, real AI:** the Ask box and quick replies are built so a language model can be switched on behind them, using one platform key that the owner of Retail OS holds and pays for. It would never use a shop owner's own account, and it stays off until then.

## 1. What this phase delivers

1. **Ask panel.** Opened from an **Ask** button in the top bar. Type or tap a question like "What should I order?" or "Who's waiting for size 42?", and get a short answer with a link to the full page.
2. **Order suggestions on To order.** Each size shows how many to buy, and why.
3. **Smart quick replies in Conversations.** From the customer's last message, the chat suggests the right ready-made reply, already filled in. Staff edit it and press Send.

## 2. The Ask box

**Where (owner's ask, 27 Oct: "don't crowd Home"):** not on Home. An **Ask** button in the top bar, next to Log missed sale, for the owner and managers.
- It opens a panel: from the right on a computer, full screen on a phone. Closing it puts it away.
- Inside the panel: a question box, 4 tap-to-ask examples that change with what's happening (for example "Who's waiting for my answer?" when replies are waiting), and the questions and answers shown like a chat.
- It uses the app's normal look. No sparkles or "AI" styling: it's a tool, and it says what it can answer.

**How it understands:** it looks for known words and details in the question, not free conversation:
- a size (42) or a colour;
- an item or customer name;
- a period: today, this week, last week, this month.

If it can't tell what's meant, it says so and shows the list of questions it can answer. It never guesses.

**The questions it answers (please confirm or change):**

| # | You can ask, for example | It answers with |
|---|---|---|
| 1 | What should I order? / What to buy this week? | The order suggestions: item, size, how many, and why |
| 2 | Who's waiting for size 42? / Who wants Nike Air Zoom? | The customers waiting for it, oldest first, with how long |
| 3 | How much did we recover this month? | The money recovered and how many sales, compared with the period before |
| 4 | How much money is waiting? | The value of everything customers are waiting for, and for how many customers |
| 5 | Why aren't people buying? | The top reasons this period, with counts |
| 6 | Which items are asked for most? | The most-requested items and sizes this period |
| 7 | Who's waiting for my answer? | The customers who replied and haven't been answered |
| 8 | What's reserved? / Which pickups are due? | Deposits held and pickup dates, overdue first |
| 9 | How many Adidas 42 do we have? | The stock for that item and size: in the shop, held for customers, free |
| 10 | Tell me about Wanjiku / 0712 345 678 | That customer's open requests and their last message |
| 11 | How are we doing this week? | Recovered, money waiting and walk-in conversion against last week |
| 12 | What came in through the shop link? | Requests from the link this period |

- **Language:** English for now. A few common Swahili words are understood too ("wanangoja" for waiting, "bei" for price, "leo" for today, "wiki hii" for this week).
- **Who can ask:** the owner and managers. Cashiers don't see money totals, so questions 3, 4 and 11 are owner and manager only.

## 3. Order suggestions on To order

Each size gets a **Suggested** number:

> suggested = customers waiting now + expected demand until the delivery − free stock

- **Expected demand:**
  - how many asked for that size over the last 8 weeks;
  - plus how many sold at the till, when a POS or Excel counts send sales;
  - scaled to the shop's usual delivery time, a new setting in Follow-ups and holds (7 days by default).
- **Shown with its reason**, for example: "3 waiting + about 2 more in a week, 1 in stock → order 4".
- **No demand, no suggestion.** It never adds a size nobody asked for.
- **Advice, not an automatic order.** The owner still ticks what they ordered.

## 4. Smart quick replies in Conversations

The chat reads the customer's last message and puts the best matching quick reply first, marked **Suggested**, with the text already filled in. Nothing is sent until staff press Send.

| Customer writes (English or common Swahili/Sheng) | Suggested reply |
|---|---|
| pay, M-Pesa, till, paybill, lipa, pesa | Payment details, with the balance (plus "Ask for M-Pesa payment" when M-Pesa is on) |
| deposit, half, part, nusu, kidogo kidogo | "You can pay a deposit of KSh … to hold it until …" |
| when, come, pick, Saturday, kesho, leo, nikuje | Confirm pickup, with the date it's held until |
| price, discount, last price, bei, punguza | "The price is KSh …", with a note to staff if a price drop is due |
| other size, colour, another, rangi, saizi | Offer another option, listing the sizes and colours in stock |
| yes, ok, sawa, ndio, I want it | Payment details, or Confirm pickup if a deposit is already paid |
| no, not now, sitaki, later | Highlights **Close as declined**, and suggests a polite thank-you |

The existing three quick replies stay. There are two new ones: **Deposit** and **Price**.

## 5. Not in this phase

- Any AI API, paid or free.
- The MCP tool.
- Automatic replies with no person checking.
- Anything that changes prices or orders stock by itself.

## 6. Order of work

1. Order suggestions on To order, plus the delivery-time setting.
2. The Ask panel: the questions above, examples under the box, and the "I can answer these" list.
3. Smart quick replies.
4. Tests, then your UAT, sign-off and merge.
