# Product

## Register

product

The app (Home, Waiting, To order, Conversations, Products, Customers, Reports, Settings, Floor mode) is the primary surface. The landing page, marketing site and a designed sign-in are a separate, later `brand` phase and start only after the whole app pipeline is done. Until then, sign-in stays plain.

## Users

Local, independent shop owners and their staff, starting with fashion retail: clothing, shoes, bags and accessories. Many are one-person shops where the owner is also the cashier; others have an owner, a manager and cashiers.

They use whatever device is in the shop. That is most often a budget Android phone, sometimes a tablet at the till, a laptop or a shop desktop. Connections can be slow mobile data. They are busy, standing, often mid-conversation with a customer, under shop lighting.

The job: when a customer can't buy what they came for (size, colour, out of stock, price, budget), record it in seconds, get the item, re-engage the customer, and turn the lost sale into a paid one.

## Product Purpose

Retail OS starts as a missed-sale recovery tool and grows into a retail operating system. The core loop:

1. Every walk-in visit gets an outcome: bought, or didn't buy with a reason.
2. Staff capture the exact item (product, colour, size), reason, phone and email, and consent.
3. The owner's morning "To order" list shows what to buy and who is waiting for it.
4. When stock arrives, units are held and each waiting customer gets a WhatsApp with a photo of the exact item. SMS and email are fallbacks.
5. Follow-ups go out up to four times until the customer replies.
6. Replies land in one inbox, where staff agree a pickup, change the item or take a deposit.
7. A sale counts as **Recovered** only when it is paid in full.

Price-too-high and over-budget requests wait for a price drop, not a restock.

Lifecycle: Open → On order → Back in stock → Notified → In conversation → Reserved → Recovered. The exits are Declined (closed, never counted as revenue) and Expired.

Success means more recovered sales in shillings, honest numbers, and a capture fast enough that staff actually use it.

## Brand Personality

Calm, trustworthy, practical. It should feel like a dependable shop tool, not a tech demo. The voice is plain and direct, uses the shop's own words ("waiting customers", "to order", "paid"), and never uses jargon ("intents", "webhooks"). The emotional goal is that the owner feels in control of every sale they nearly lost.

## Anti-references

- The previous UI: neon cyan, violet and pink, glow shadows, glassmorphism, background photos and gradient text.
- Any blue or violet as a brand or status colour. The owner reads it as the "AI look".
- Sand/beige with mixed clay, orange and red accents and expressive display fonts. This was tried in draft 2 and rejected as over-aesthetic, with too many colours.
- Floating, drifting cards and decorative motion inside the app or on the current sign-in.
- Hardcoded or decorative metrics (the old fake "recovery funnel" percentages).
- Customisation controls on the dashboard. All customisation lives in Settings.

## Design Principles

1. **Work first, decoration never.** Colour only for the brand action and status meaning.
2. **Every number is real.** Each figure links to the records behind it; "recovered" means paid.
3. **The next action is obvious.** Home is a work queue, not a wall of charts.
4. **Phone first, any screen.** One web app, designed at 360px, then tablet and desktop. No native app.
5. **Built to plug in.** Every screen action is also an API action, for future POS integrations.
6. **Local by default.** Currency (KSh), timezone and phone format (+254) come from the shop's settings.

## Accessibility & Inclusion

- WCAG AA contrast for all text, in light and dark themes.
- Status is never conveyed by colour alone: every badge has a dot and a word.
- Tap targets at least 44px, and 50px+ in floor mode.
- Respect reduced motion.
- Pages stay light for slow mobile data and budget phones. Inputs open the right keyboard (number pad for phone and price).
