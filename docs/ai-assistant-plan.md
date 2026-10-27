# Plan: a real AI model behind Ask and reply drafts

For the owner and the developer who builds it. Status: **a plan, not built**. Today the Ask panel and quick replies use no AI. They answer set questions and match words, for free (Phase 6). This is how a real model goes in behind them, when the owner is ready to pay for it.

## 1. What changes for the shop

- **Ask** understands any question in normal words, English, Swahili or Sheng: "Nani anangoja Nike 42 na amelipa deposit?", "Compare this month with last month". It answers from the shop's own records, with links, like today.
- **Reply drafts:** in a conversation, a **Draft a reply** button writes a reply that fits what the customer said, using the item, price, balance, hold date and payment details. Staff edit it and press Send. **Nothing is ever sent without a person.**
- **If the AI is switched off, or can't be reached,** everything falls back to today's free behaviour. Nothing breaks.

## 2. Whose account pays

**One platform API key, held by the owner of Retail OS** (an Anthropic API account, billed per use). Shops never need their own AI account. The cost is priced into what shops pay for Retail OS, or into an "AI" plan. The Claude subscription used for coding is separate and can't be used for this.

## 3. Which model

Anthropic's current models and list prices (per million tokens, as of October 2026). **Check the pricing page before deciding:**

| Model | ID | Input / output | Fit |
|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | $4 / $20 | Most capable of the three. Best answers to hard or mixed-language questions |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | $2 / $10 | Fast and capable, half the price of Opus |
| Claude Haiku 5.5 | `claude-haiku-5-5` | $0.10 / $0.50 | Cheapest and quickest; for simple, short tasks |

**How to choose:** the choice of model is the owner's, and it should be measured, not guessed.
1. Build with **Opus 5.5** first.
2. Write down 30–50 real questions shops ask, and 30–50 real customer messages with a good reply for each.
3. Run the same set on Sonnet 5.5 and Haiku 5.5, and compare quality and cost per answer.
4. Choose per feature. Reply drafts, which are short and frequent, may do well on a cheaper model. Ask may need more.

## 4. How it works (for the developer)

**Ask = the model plus the shop's own data functions as tools.** The model never gets raw database access. It can only call read-only functions that already exist and are tested:

| Tool | Uses today's code |
|---|---|
| `to_order` (suggestions) | `analytics.selectors.get_to_order` |
| `waiting_for(item, size, colour)` | `dashboard.ask._who_waits` logic |
| `recovered(period)` / `key_numbers(period)` / `reasons(period)` / `conversion(period)` | `dashboard.selectors` |
| `needs_you()` | `dashboard.selectors.needs_you` |
| `stock(item, size, colour)` | `ProductVariation` lookups in `dashboard.ask._stock` |
| `customer(name or phone)` | `dashboard.ask._customer` (phone masked) |

- **Built with:**
  - the official `anthropic` Python SDK;
  - its **tool runner**, with every tool scoped to the signed-in user's shop;
  - `strict: true` tool schemas;
  - `output_config.effort` tuned per feature (lower for drafts);
  - streaming, so answers appear as they're written.
- **Reply drafts are a single call.** The deal facts (item, price, balance, hold date, payment details) and the last few messages go in, and one draft comes out. No tools are needed.
- **Prompt caching:**
  - the instructions and tool list go first and never change, so they're cached and cost much less after the first call;
  - the shop's data goes after them.
- **Limits:**
  - a daily spend cap per shop, and a monthly cap for the platform;
  - a cap on questions per user per hour;
  - a short timeout, after which Ask falls back to the free answers.
- **Errors and refusals:** handled; the user sees "I couldn't answer that, here's what I can do" and the free list.
- **Tests** never call the real API. They use recorded responses, and a small evaluation set (step 2 in section 3) is run before changing models or prompts.

## 5. Privacy and safety

- **Send the least possible:**
  - phone numbers are masked (`+254 7•• ••• 281`);
  - customer messages are sent only for the conversation being drafted, and only the last few;
  - no payment codes.
- **Tell the shops,** in the terms and the privacy notice, that AI features send some shop data to Anthropic to produce answers, and that it isn't used to train models under the API terms (confirm the current terms at the time).
- **Keep it switchable:** a shop setting turns AI off, falling back to the free behaviour.
- **Keep it read-only:**
  - Ask never changes anything;
  - a future "record this delivery" style action would need the person to confirm on screen first.

## 6. Steps when the owner says go

1. **Agree** the model plan (section 3) and the monthly budget.
2. **Create** the Anthropic API account and key. Put it in `.env` (`ANTHROPIC_API_KEY`) on the server only.
3. **Build:**
   - the tool layer;
   - Ask with streaming;
   - the Draft a reply button;
   - the spend caps;
   - the fallback to free answers.
4. **Run** the evaluation set on the candidate models and choose.
5. **Turn it on** for one shop, watch cost and quality for two weeks, then for all.
