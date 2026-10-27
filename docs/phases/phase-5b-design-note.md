# Phase 5b design note: Log missed sale without internet

**Status:** approved by the owner 27 Oct 2026 ("provided it doesn't interrupt what works now") · built on `phase-5b/offline-capture`
**Owner's ask (27 Oct 2026):** "Offline Log missed sale". Only capture works offline; everything else stays online.
**Still free:** this uses only the browser (an installable web app). No app store, no paid service.

## 1. What this phase delivers

When the shop's internet drops, staff keep logging missed sales on the phone as normal. Nothing is lost. When the connection comes back, the records send themselves, and customers are messaged then.

## 2. How it works for staff

- **Install once:** the browser offers **Add to Home screen**. Retail OS then opens like an app.
- **Offline:**
  - A bar at the top says **"Offline: saving on this phone"**.
  - Log missed sale works exactly as now: item, size or colour, reason, number, Save. **They bought after all** works too.
  - After Save: "Saved on this phone. It sends when you're back online."
- **Back online:** sending is automatic. The bar shows "Sending 3…", then "All sent". Each record then goes through the same rules as if it had been saved online.
- **Waiting count:** while records are waiting, the top bar shows **"3 not sent yet"**, so nobody switches the phone off thinking they're done.

## 3. The hard parts, and how each is handled

| Challenge | What we do |
|---|---|
| Messages can't go out offline | Records wait on the phone. On sending, the restock or price rules run normally, so customers are told, just later. |
| Stock on the phone may be out of date | The phone keeps the item list and stock from the last time it was online, and says "Stock as of 10:42". When a record arrives, the server checks again. If the size turns out to be in stock, it's saved as **Something else: "It's in stock now: invite them in"**, so the customer isn't lost. |
| The same record sent twice (weak signal) | Each record gets its own id on the phone. The server saves it once, however many times it arrives. |
| Customer numbers stored on the phone | Records are deleted from the phone as soon as the server confirms them. **Sign out** wipes anything left, after warning "3 records haven't been sent". Records older than 7 days are never kept. |
| Sign-in expires while offline | Records are kept, and the bar says "Sign in to send 3 records". Nothing is thrown away. |
| New items or sizes typed offline | Allowed, as online. They're created when the record arrives, with the same rules (cashiers' new items are marked "Needs review"). |
| iPhone limits | iPhones don't send in the background reliably, so sending also starts whenever the app is opened or comes back to the front. To be tested on a real iPhone and Android in UAT. |
| One phone, several staff | Each record keeps who logged it. If someone else signs in, they see "records from Amina waiting", and the records send under Amina's name. |

## 4. What gets built

- **App setup:** a web app manifest and icon, so it can be installed; a service worker that keeps the Log missed sale page, styles and icons available offline.
- **Phone storage:** a small queue in the browser's database (IndexedDB) for unsent records, plus the last item and stock list.
- **Sending:** a new endpoint that takes one record with its phone id, applies the usual Log missed sale rules, and answers "saved" or "already had it".
- **Server:** a `client_ref` on missed sales and visits, unique per shop, so a repeat send is recognised.
- **Status bar:** the online, offline and not-sent state on Log missed sale and in the app's top bar.

## 4b. Not interrupting what works now
- Online, Log missed sale behaves exactly as before. The only difference is a hidden id on each save, which also stops a double-tapped Save from creating two records.
- The offline helper only steps in for Log missed sale and the app's own styles and icons. Other pages are never served from the phone's copy, so they're always current.
- If the browser doesn't support it (very old phones), nothing changes: the page works online as today.

## 5. Not in this phase

- Any other screen offline (Waiting, Conversations, Reports, Settings).
- Replying to customers or taking payments offline.

## 6. Tests and UAT

- **Automated tests:**
  - a repeated send saves once;
  - a size that came back in stock becomes Something else;
  - an expired sign-in keeps the queue;
  - wrong-shop records are refused.
- **UAT on your phone:**
  - airplane mode on, log 3 missed sales and 1 "bought";
  - airplane mode off: all arrive once, and customers are messaged;
  - repeat with sign-out while offline (warning, then wipe).
