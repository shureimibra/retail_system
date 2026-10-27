# Connecting a POS or another system to Retail OS

This guide is for the person connecting a till system, an online store or a script to one shop's Retail OS. You can:
- read the shop's items and the **To order** list;
- send stock counts, deliveries and sales.

## 1. Get a key

The shop owner opens **Settings → Connections → Create a key** and chooses what the key may do:
- **Read only:** read items and the To order list.
- **Read and change stock:** also send counts, deliveries and sales.

The key looks like `ros_1a2b3c4d_…`. It is shown once, so copy it then. If it's lost or leaks, the owner revokes it on the same page and creates another; a revoked key stops working at once.

Send the key with every request:

```
Authorization: Bearer ros_1a2b3c4d_…
```

The address is the shop's Retail OS address followed by `/api/v1/connect/`, for example `https://kimathi.example.com/api/v1/connect/`. The Connections page shows the exact address.

Everything is JSON. A key only ever sees and changes its own shop.

## 2. Items: `GET products/`

```bash
curl -H "Authorization: Bearer $KEY" https://…/api/v1/connect/products/
```

```json
{"products": [
  {"sku": "AU-42-GRE", "item": "Adidas Ultraboost", "type": "Shoes", "size": "42", "colour": "Grey",
   "price": "18700.00", "in_stock": 2, "held_for_customers": 1, "available": 1}
]}
```

- **in_stock:** units in the shop.
- **held_for_customers:** units put aside for customers who asked for them; don't sell these to someone else.
- **available:** in_stock minus held.

**Match your system's items to Retail OS by SKU.** If your POS uses different codes, the owner can type yours into the SKU column of the stock spreadsheet (Products → Import stock).

## 3. What customers are waiting for: `GET to-order/`

```bash
curl -H "Authorization: Bearer $KEY" https://…/api/v1/connect/to-order/
```

This returns the same list as the To order page: the items customers asked for that haven't been ordered yet, most money first.

## 4. Stock changes: `POST stock/`

You can send up to 500 changes at a time. Each change has a `sku` and **exactly one** of:

| Field | Meaning | Example |
|---|---|---|
| `set` | A count: what's on the shelf now (0 or more) | after a stock take |
| `add` | A delivery arrived (1 or more). **Customers waiting for that size are messaged.** | supplier delivery |
| `remove` | Taken out, not sold (1 or more) | damaged, returned to supplier |

```bash
curl -X POST https://…/api/v1/connect/stock/ \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: delivery-DN-2210" \
  -d '{"reference": "DN-2210", "changes": [
        {"sku": "AU-42-GRE", "add": 3},
        {"sku": "AU-44-GRE", "set": 5}
      ]}'
```

```json
{"results": [
  {"sku": "AU-42-GRE", "ok": true, "in_stock": 3},
  {"sku": "AU-44-GRE", "ok": true, "in_stock": 5}
]}
```

- Each change succeeds or fails on its own. A failed one has `"ok": false` and an `error` in plain words, for example an unknown SKU.
- Stock can never go below the units held for customers; such a change is refused.
- `reference` is optional. It's saved in the stock history with the key's name, for example "Loyverse: DN-2210".

## 5. A sale at the till: `POST sales/`

```bash
curl -X POST https://…/api/v1/connect/sales/ \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: receipt-1043" \
  -d '{"reference": "Receipt 1043", "items": [{"sku": "AU-44-GRE", "quantity": 1}]}'
```

```json
{"results": [{"sku": "AU-44-GRE", "ok": true, "sold": 1, "in_stock": 4}]}
```

- Stock goes down, and the sale counts as a walk-in who bought (for walk-in conversion in Reports).
- A sale never takes a unit held for a customer. If you sell more than are free, `sold` is lower than `quantity` and a `warning` asks the shop to count that item again.

## 6. Sending the same thing twice

Bad connections make systems retry. Add an `Idempotency-Key` header to every `POST`, using something unique to that event, like the receipt or delivery note number. If Retail OS has already seen that key:
- it returns the first answer;
- it adds the header `Idempotent-Replay: true`;
- it changes nothing.

Keys are remembered for each API key separately.

## 7. Errors

| Status | Meaning |
|---|---|
| 400 | The body isn't what's described here; `error` says what's wrong |
| 401 | Missing, wrong or revoked key |
| 403 | The key is read only |
| 429 | More than 300 requests a minute; wait and retry |

## Not yet

- Retail OS doesn't call your system when something changes (outgoing webhooks).
- Ready-made connectors for particular POS systems. Each one will be built on these four calls when a shop needs it.
