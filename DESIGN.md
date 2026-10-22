---
name: Retail OS
description: Missed-sale recovery and retail operations for local fashion shops
colors:
  petrol: "#0B6670"
  petrol-hover: "#08525A"
  petrol-subtle: "#E1EEEF"
  petrol-ink: "#0A5C65"
  clay: "#B4491F"
  stone-bg: "#F5F6F4"
  surface: "#FFFFFF"
  surface-2: "#F0F2EF"
  border: "#DFE3DE"
  border-strong: "#C6CDC6"
  ink: "#18201D"
  ink-2: "#4A5550"
  ink-3: "#626D68"
  ok: "#2B6E37"
  ok-bg: "#E2F0E3"
  warn: "#8F5208"
  warn-bg: "#FAEED8"
  crit: "#B0261E"
  crit-bg: "#FAE6E4"
  neutral-bg: "#EAEDE9"
  dark-bg: "#0F1312"
  dark-surface: "#161B1A"
  dark-surface-2: "#1C2221"
  dark-border: "#29312F"
  dark-ink: "#E6EBE9"
  dark-ink-2: "#AAB4B0"
  dark-petrol: "#5DB6BE"
  dark-clay: "#E5875D"
typography:
  headline:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "21px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "14.5px"
    fontWeight: 600
    lineHeight: 1.4
  metric:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "27px"
    fontWeight: 600
    lineHeight: 1.2
    fontFeature: "tnum"
  body:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  table:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
  label:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    letterSpacing: "0.05em"
  mono:
    fontFamily: "IBM Plex Mono, Cascadia Mono, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
rounded:
  control: "6px"
  card: "8px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
  3xl: "32px"
  4xl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.petrol}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
  button-primary-hover:
    backgroundColor: "{colors.petrol-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
  button-floor:
    backgroundColor: "{colors.petrol}"
    textColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "13px 22px"
    height: "50px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "7px 10px"
  badge:
    rounded: "{rounded.pill}"
    padding: "1px 8px"
---

# Design System: Retail OS

The approved visual reference with live components and screen mockups is `docs/design/retail-os-design-spec.html` (published at https://claude.ai/artifact/BtUkFTN8KtV8E18rogHvJq). If this file and the spec disagree, the spec wins, and this file should be corrected.

## 1. Overview

**Creative North Star: "The Shop Ledger."** A calm, exact working tool that a shop owner trusts like their own sales book. Dense where staff scan (lists, tables), generous where they tap (floor mode). Flat surfaces separated by 1px borders, one brand colour, and status tones that only appear when they mean something. It must not feel like an AI demo, a crypto dashboard or a lifestyle brand.

Two densities share one system. **Back office** uses 14–15px text and 36–40px rows. **Floor mode** (the tablet or phone at the till) uses 16–24px text and 50px+ targets. The design is phone-first: built at 360px, then 600–1023px (tablet) and 1024px+ (desktop).

## 2. Colors

### Primary
- **Petrol** (#0B6670; dark theme #5DB6BE): primary buttons, selected nav, links, focus rings, the brand mark and the current step in a status bar. It means "the shop acts here". White text on it passes AA.
- **Petrol subtle** (#E1EEEF): selected rows and nav, outgoing chat bubbles, "Back in stock".

### Secondary
- **Clay** (#B4491F; dark theme #E5875D): used in exactly two places. The "In conversation" badge and the unread count on Conversations, meaning "a customer replied and is waiting on you". Never anywhere else.

### Neutral
- **Stone background** (#F5F6F4 / #0F1312): the page.
- **Surface** (#FFFFFF / #161B1A): cards, nav, top bar.
- **Surface 2** (#F0F2EF / #1C2221): table headers, chips, hover.
- **Border** (#DFE3DE / #29312F) and **Border strong** (#C6CDC6): every separation.
- **Ink** (#18201D), **Ink 2** (#4A5550), **Ink 3** (#626D68): text, secondary text, captions.

### Status tones (badges only)
- **Open:** warn text #8F5208 on #FAEED8.
- **On order:** petrol outline.
- **Back in stock:** petrol on petrol subtle.
- **Notified:** ink 2 on neutral #EAEDE9.
- **In conversation:** clay, solid.
- **Reserved:** ok-green outline (#2B6E37).
- **Recovered:** ok #2B6E37 on #E2F0E3.
- **Declined:** neutral.
- **Expired:** border-strong outline.
- **Send failed:** crit #B0261E on #FAE6E4.

### Named Rules
- **No blue or violet, anywhere.** Not as brand, not as status, not in charts.
- **One brand colour.** Petrol is the only accent; clay is a signal, not a second brand colour.
- **Status needs a word.** Every badge is a dot plus a label.

## 3. Typography

IBM Plex Sans for everything, IBM Plex Mono for SKUs, phone numbers and codes. Plex has tabular figures and clear 0/O and 1/l, which matters for SKUs and phones. Self-host the fonts. Use `font-variant-numeric: tabular-nums` wherever digits align.

### Hierarchy
- **Headline** (600, 21px, 1.3): page titles ("Waiting customers").
- **Metric** (600, 27px, tabular): KPI values ("KSh 84,600").
- **Title** (600, 14.5px): card titles.
- **Body** (400, 15px, 1.55): running text, max ~68ch.
- **Table** (400, 14px, tabular): list and table cells.
- **Label** (600, 12px, 0.05em, uppercase): section labels and table headers.
- **Mono** (400, 12px): SKUs (NIKE-AZ-42-BLK), phones (+254 712 345 678).
- **Floor** (500, 16–24px): floor-mode labels, chips and the phone keypad.

## 4. Elevation

Flat. Cards and panels use a 1px border and **no shadow**. Hierarchy comes from surface tone (stone → surface → surface 2) and borders.

### Shadow Vocabulary
- **Pop** (`box-shadow: 0 6px 20px rgba(18,28,24,.12), 0 1px 3px rgba(18,28,24,.08)`): only for things that float above the page, such as menus, modals, toasts and popovers.

### Named Rules
- **No glow, no blur, no gradients** on surfaces, buttons or text.

## 5. Components

### Buttons
- **Shape:** 6px radius (floor-mode buttons 8px, 50px+ tall).
- **Primary:** petrol with white text, 7px 14px. One primary per view.
- **Hover / Focus:** hover darkens to #08525A; focus is a 2px petrol outline offset 2px; `:active` scales to 0.97. Transitions are 150ms ease-out.
- **Secondary:** surface with a 1px border-strong outline and ink text. **Plain** buttons are text-only in petrol ink. **Critical** buttons use crit text.

### Chips (floor mode)
- **Style:** surface with a 1px border-strong outline and 8px radius, min 50×66px, 16px text, and an optional 11.5px caption (stock count).
- **State:** selected is a 2px petrol border on petrol subtle. Out-of-stock options show their caption in crit.

### Cards / Containers
- **Corner Style:** 8px.
- **Background:** surface.
- **Shadow Strategy:** none (see Elevation).
- **Border:** 1px border.
- **Internal Padding:** 16px (back office), 16–18px (floor).

### Inputs / Fields
- **Style:** 1px border-strong outline, surface background, 6px radius, 7px 10px. The label sits above at 13.5px/500; help text sits below at 12.5px ink 3.
- **Focus:** 2px petrol outline.
- **Error:** crit border and a crit message that says what's wrong and how to fix it. Phone fields have a "+254" prefix and open the number pad.

### Navigation
- **Desktop (1024px+):** a 220px left sidebar grouped Customers / Stock / Shop, with Settings at the bottom. Active items get surface 2 with ink text. Counts are 11.5px; unread Conversations get a clay pill.
- **Tablet:** slim sidebar.
- **Phone:** a bottom tab bar (Home, Waiting, a central petrol "+" to log a missed sale, Chats, More). Settings sits under More.

### Status Bar (signature)
A segmented strip of lifecycle stages in the record header. Done stages use surface 2; the current stage is solid petrol.

### Index tables
Header row on surface 2 with 12.5px ink 3 labels, then 10px 12px cells with tabular numbers right-aligned. On phones, tables become cards.

## 6. Do's and Don'ts

### Do:
- **Do** keep petrol as the single accent and reserve clay for "customer waiting" only.
- **Do** link every metric to the records behind it.
- **Do** design at 360px first and check 360 / 768 / 1280px.
- **Do** use tabular numbers for money, counts and SKUs.
- **Do** keep motion to 120–300ms ease-out and only to confirm an action (toast, status change, count update).
- **Do** put all configuration and customisation in Settings.

### Don't:
- **Don't** use blue or violet, neon, glow shadows, glassmorphism, gradient text or background photos.
- **Don't** add shadows to cards, or radii above 8px (except pills and the phone tab bar's round "+").
- **Don't** put customise or edit-layout controls on the dashboard.
- **Don't** use floating or drifting decorative elements. The designed sign-in and landing page are a later brand phase.
- **Don't** show hardcoded or illustrative numbers in the product.
- **Don't** introduce another font or a second accent colour.
