# Plan: plugging Retail OS into POS systems and online stores

For the owner, and the developer who builds the connectors. It covers what exists now (Phase 5) and what comes next. The technical how-to for an existing connection is `docs/api.md`.

## 1. What's already built

| Piece | What it does | Where |
|---|---|---|
| **API keys** | The owner creates a key per system (read only, or read and change stock), shown once, revocable | Settings → Connections |
| **Connection points** | Read items and To order; send stock counts, deliveries, stock taken out, and till sales. A repeated send is applied once | `/api/v1/connect/…`, `docs/api.md` |
| **Excel or CSV import** | For shops with no POS: count, upload, preview, save | Products → Import stock |
| **Shop link and QR code** | Customers ask for a missing size themselves | Settings → Shop link |

So **any POS whose maker or user can write a small script can connect today**, using `docs/api.md`.

## 2. What a ready-made connector adds

A **connector** is a small piece of Retail OS that talks to one POS by itself, so the shop just clicks **Connect** and signs in. It does three jobs:
1. **Items:** links the POS's items and variants to Retail OS's by SKU. It shows a list of the ones it couldn't match, so the owner can match them once.
2. **Stock:** when the POS's stock changes (a sale, a delivery, a count), Retail OS's count follows. When stock arrives, waiting customers are messaged, as now.
3. **Sales:** POS sales count as walk-ins who bought, so walk-in conversion is real.

**How it gets the changes:**
- **Best:** the POS calls Retail OS when something changes (a webhook).
- **Otherwise:** Retail OS asks the POS every few minutes, using the existing scheduler.

Either way it goes through the same stock rules as everything else: units held for customers are never sold or counted away.

## 3. Which POS first: decide with real shops

The connector to build first is the one the first paying shops actually use. Before building any of them, check (on that day, since APIs and plans change):
- **Does it have an API?** Is it open to us, or only to partners?
- **Which plan does the shop need for it?** Some POS keep their API for paid plans.
- **Does it have webhooks?** If not, only checking every few minutes is possible.
- **Is it common with Kenyan fashion shops?**

Candidates to research:

| POS or platform | Why it's a candidate | To check |
|---|---|---|
| **Loyverse** | Free POS, popular with small shops in Kenya; has an API and webhooks | Which plan the API needs |
| **Shopify** (online store and POS) | Fashion shops selling online; mature API and webhooks | Shop must be on Shopify; app review if listed publicly |
| **WooCommerce** | Shops with a WordPress website; REST API and webhooks | Shop's hosting reliability |
| **Odoo** (Point of Sale) | Larger shops; open source | Version differences between shops |
| **Excel and Google Sheets** | No POS at all, the most common case today | Already covered by the import; a Google Sheets live link is a possible upgrade |

## 4. Other plug-ins

- **Website widget:** the shop link's form inside a shop's own website, as a small embed. The page already exists, so this is a small job when a shop with a website asks.
- **Outgoing webhooks:** Retail OS tells another system when something happens: "customer waiting for 42", "sale recovered", "stock held". This lets a POS or an accounting tool react. Signed with a secret, retried if the other side is down.
- **Accounting:** recovered sales into the shop's books (e.g. QuickBooks, Zoho Books). Only if shops ask.
- **M-Pesa statements:** match till payments to deposits automatically. That needs Safaricom's C2B confirmation set up per shop (see `docs/going-live-messaging.md`, section 6).

## 5. Order of work, after launch

1. Ask the first 5–10 shops what they use. **The answer decides the first connector.**
2. Build that connector (a design note first, as always), with a "Connect" button in Settings → Connections.
3. Outgoing webhooks: a small job that makes every other integration easier.
4. The website widget, when a shop with a website asks.

## 6. Rules every connector follows

- It uses an **API key per shop**, or the POS's own sign-in (OAuth), stored encrypted. Never a staff password.
- It **never deletes** in either system. Stock changes go through the same services as the screens.
- **Every change it makes is in the stock history**, named after the connector, e.g. "Loyverse: receipt 1043".
- **If the POS is down,** it retries quietly and shows "Last synced 10:42" in Settings → Connections. Waiting customers are never messaged twice.
