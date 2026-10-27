# Phase 6 design note: AI and an assistant for the owner

**Status:** draft for the owner's approval · built after Phase 5b
**From the approved spec:** "MCP server, forecasting, reply-drafting assistant."
**Owner's rule:** nothing paid for now. That shapes this phase more than any other, because AI that writes text runs on a paid model. Below, each part says whether it's free.

## 1. What this phase delivers

1. **Ask your shop questions in Claude** (free for Retail OS to run). The owner asks, in their own words, "What should I order this week?" or "Who's waiting for size 42?", and Claude answers from the shop's live data.
2. **Order suggestions** (free, no AI). To order shows how many to buy of each size, based on what customers asked for and what sold.
3. **Reply drafts in Conversations** (a decision for you, see section 4).

## 2. Ask your shop questions: an MCP server

**What MCP is:** a standard way to let Claude (the desktop app or Claude Code) use a tool safely. We build a small Retail OS tool that runs on the owner's laptop. It talks to Retail OS with an API key from Settings → Connections, the same kind of key a POS uses.

**What it can read:**
- what's waiting and for how long;
- To order, with suggestions;
- recovered money for a period;
- reasons customers didn't buy;
- stock of an item;
- one customer's open requests.

**What it can do:** nothing by default. With a key that can change stock, it can also record a delivery, which messages waiting customers. Every change asks the owner to confirm in Claude first.

**Privacy:**
- Phone numbers are shortened (`+254 7•• ••• 281`) unless the owner asks for one customer by name.
- Customers' message texts are never sent to Claude.

**Cost:** free for Retail OS. The owner uses their own Claude account. The tool is built with the official open-source MCP library.

**New read points for it (and for any connected system):**
- `GET waiting/`
- `GET summary/` (recovered, waiting, reasons, for a period)
- `GET customers/<phone or name>/` (masked by default)

All are read-only and work with a Read-only key.

## 3. Order suggestions (no AI, free)

On **To order**, each size gets a **Suggested** number:

> suggested = customers waiting now + expected demand until the delivery − free stock

- **Expected demand** is how many asked for that size, plus how many sold at the till (when a POS or the Excel counts send sales), over the last 8 weeks, scaled to the shop's usual delivery time. That time is a new setting in Follow-ups and holds, 7 days by default.
- **Shown with its reason**, for example: "3 waiting + about 2 more in a week, 1 in stock → order 4".
- **Never rounds a size people haven't asked for into an order:** with no demand, there's no suggestion.
- The owner can always type a different number. A suggestion is advice, not an automatic order.

This is plain arithmetic on the shop's own data, so it is free and works today.

## 4. Reply drafts: your decision

**Why it needs a decision:** writing a natural reply to "Can I pay half now and the rest Friday?" needs a language model, and every good one charges per message. Options:

| Option | Cost | Quality | Notes |
|---|---|---|---|
| **A. Build it, switched off** until you're ready to pay | Free now; later a small charge per draft (checked against current prices when you decide) | Good | You turn it on in Settings when you're ready; nothing else changes |
| **B. Smarter quick replies, no AI** | Free | Fair | Suggests the right ready-made reply (deposit, pickup date, price, payment details) from keywords in the customer's message, with their name and item filled in |
| **C. Both:** B now, A ready to switch on | Free now | Fair now, good later | Recommended |

Drafts are never sent automatically. Staff read, edit and press Send.

## 5. Not in this phase

- Automatic replies with no person checking.
- AI that changes prices or orders stock by itself.
- Image recognition of products.

## 6. Order of work

1. Order suggestions on To order.
2. New read points, then the MCP tool, with a short setup guide for Claude Desktop.
3. Reply drafts as you choose in section 4.
4. Tests (no real AI calls in tests), then your UAT, sign-off and merge.
