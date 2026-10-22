# Research: Reatech360 (features only)

- **Source:** public homepage https://reatech360.com/, captured 22 Oct 2026 with REA (`inspect_web_page`, `capture_web_screenshot`) in an isolated headless browser. No sign-in, no private pages.
- **Scope agreed with the owner:** borrow **features only**, never Reatech360's look, branding or code. Its blue brand and photo hero are explicitly not for us (see `PRODUCT.md` anti-references).

## What it is

An AI-powered ERP and CRM for businesses in Kenya (Westlands, Nairobi). Its modules are invoicing, payments, expenses, payroll and HR, projects, CRM, WhatsApp and email delivery, a call centre, a web studio and an AI assistant ("Rena"). Each customer gets its own isolated workspace.

## Features worth borrowing, and where they land

| Reatech360 feature | What we take | Our phase |
|---|---|---|
| Invoice states "paid / partial / overdue"; the balance updates itself when a payment lands | Reserved requests show **deposit paid, balance due and pickup-by**. "Paid in full" is computed from recorded payments, not a toggle | 1 (data), 3 (screens) |
| Customers pay by **M-Pesa, card or bank** | Payment methods on deposits: M-Pesa (with reference), cash, card, bank | 1 (manual), 4 (M-Pesa confirmation) |
| **One profile per customer** with balances and history | Customer profile: every request, message, deposit and payment on one timeline, plus total deposits held | 1 (timeline data), 3 (screen) |
| Documents **delivered on WhatsApp or email** | Deposit receipts and pickup reminders sent on the customer's channel | 1 (gateway), 3 |
| **Role-based access + 2FA**, workspace isolated per business | Owner / Manager / Cashier roles, each shop's data scoped to the shop; 2FA for owners later | 1 (roles, shop scoping), later (2FA) |
| **"We set up your workspace"**: subdomain, branding, starter data | Guided first-run setup in Settings with fashion starter data (product types, size runs, reasons, message templates) | 2 |
| Reports **export to PDF / Excel** | Keep PDF and CSV exports; add Excel-friendly CSV for the To order list and the recovered report | 3 |
| AI assistant that acts **only after the user confirms** | The Phase 6 assistant drafts replies and actions; staff confirm before anything is sent or saved | 6 |

## Not borrowed

Payroll, leave, projects and time, the call centre, the web studio, multi-currency invoicing (we are KSh-first), the visual design, and the marketing copy.
