# Phase 5 design note: plug in

**Status:** approved by the owner 27 Oct 2026 · built on `phase-5/plug-in`
**Owner's answers (27 Oct 2026):** shops don't use a particular POS yet; many keep stock on paper or in Excel. Retail OS must still be ready to plug into a POS later. Customers should be able to ask for a missing size themselves through a **shareable link**, not an embed on a website.
**Still free:** nothing here needs a paid service. Everything runs on the laptop, and the tunnel makes the link reachable from phones.

## 1. What this phase delivers

After Phase 5:
- **Shops on paper or Excel** fill in one spreadsheet and upload it. Stock is correct in Retail OS without typing each size by hand, and anyone waiting for a size that just arrived is messaged automatically.
- **Customers ask for themselves.** Each shop gets a link, like `…/ask/kimathi-street-store/`, to put in the Instagram bio, a WhatsApp status, TikTok, or a QR code at the counter. A customer picks the item and their size, leaves their number, and it lands in Waiting like any missed sale.
- **Any POS can plug in later.** The owner creates an API key in Settings. A POS (or a developer working for the shop) uses it to send stock changes and sales to Retail OS, and to read the To order list. Connecting a specific POS becomes a small adapter on top of this, not a rebuild.

## 2. What gets built

### 2.1 Stock from Excel (Products → Import stock)
- **Download the template:** an Excel file with the shop's items already filled in. Columns: Item, Type, Size, Colour, Price, **In stock**. Staff only change the In stock numbers, or add rows for new items.
- **Upload it.** Retail OS shows a preview before saving anything: "12 counts changed, 3 new sizes, 1 new item, 2 rows have problems (row 7: price is not a number)". Nothing is saved until you press **Save these changes**.
- **What saving does:** each In stock number is a **stock count**. Where stock went up, waiting customers are told, exactly as with **Receive stock**. Units held for customers are never taken away by an import.
- `.xlsx` and `.csv` both work. Owner or manager only.
- Library: `openpyxl` (free, open source).

### 2.2 The "Ask for your size" link
- **One public page per shop**, phone-first, showing the shop's logo and name.
- **Three steps, no account:** choose the item (photos, searchable), then the size and colour (or type one in), then the phone number, an optional name, and the WhatsApp tick.
- It creates a normal missed sale, marked **From the link** so staff can tell it apart in Waiting and Reports. Price and stock counts are never shown to the public.
- **Settings → Shop link:** copy the link, download a QR code to print, switch the link off.
- **Protection:** a hidden trap field against bots, a limit per phone number and per address, a phone check, and no page that ever reveals other customers.
- Library: `segno` for the QR code (free, open source, no other dependencies).

### 2.3 API keys (Settings → Connections)
- Owner only. **Create key** asks for a name ("Loyverse", "Website") and what it may do: *Read*, or *Read and change stock*.
- The key is shown **once**. Only a scrambled (hashed) copy is stored, like a password. Each key shows when it was last used, and **Revoke** stops it immediately.
- Every request with a key works for that one shop only.

### 2.4 The connection points a POS uses
All under `/api/v1/`, using the key:

| What | Does |
|---|---|
| `POST stock/` | Send one or many changes by SKU: "set to 5" (a count) or "+3 / −1" (received or sold). Goes through the same rules as the screens, so restock messages go out. |
| `POST sales/` | A sale at the till: counts a walk-in sale and takes the stock down. |
| `GET to-order/` | The supplier shopping list. |
| `GET products/` | Items, sizes, colours, SKUs and stock. |

- Each request can carry an **idempotency key**. If a POS sends the same change twice (common on bad connections), it's applied once.
- `docs/api.md` documents this in plain words, with copy-paste examples.

### 2.5 Small fix carried in
- Today the stock of a sold item goes down only when a **missed sale** is Paid in full. Through `POST sales/` and the Excel count, ordinary sales also bring stock down, so "0 in stock" stays true.

## 3. Not in this phase
- A ready-made connector for one particular POS. That comes when a shop actually uses one: it's a thin adapter on 2.4.
- Retail OS sending events out to other systems (outgoing webhooks).
- An embed for shop websites. The link page can be embedded later with no new design.
- The AI and MCP work: Phase 6.

## 4. Data changes
- `ApiKey`: shop, name, prefix, hashed key, permission, created by, last used, revoked.
- `Shop`: a short `slug` for the link, and "link on/off".
- Missed sale: a `source` (Log missed sale / Shop link / API).
- `StockImport`: who uploaded what and when, with the preview result, so a count can be traced.

## 5. Tests and UAT
- Automated tests for each piece, with no real messages sent.
- New UAT rows S25 onwards:
  - import a filled template and check the preview, then save and check the messages;
  - ask through the link from your phone (via the tunnel);
  - create and revoke a key;
  - send a stock change with `curl` and check it arrives once.

## 6. Order of work
1. Excel import (most useful today).
2. Shareable link and QR code.
3. API keys, then the connection points and `docs/api.md`.
4. Tests, then your UAT, your sign-off, and the merge.
