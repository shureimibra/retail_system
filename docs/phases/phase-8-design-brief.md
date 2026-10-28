# Phase 8 design brief: the marketing website

**Status:** draft for the owner's approval · branch `phase-8/landing` · the site itself is built in the separate `../retail-os-marketing` workspace
**Sources:**
- the owner's references: a MotionSites screen recording and Pinterest images;
- a creative direction written from them in the owner's Claude chat, saved as `retail-os-marketing/briefs/creative-direction-2026-10-28.md`. Section numbers like "§4.3" below point into that file.

**This brief decides; that file explains.** Where they differ, this brief wins.

## 1. What we're building

A **marketing website, separate from the app**. It's phone-first, with real motion: scroll-driven scenes, a hands-on mini demo, and 3D on bigger screens. It does two jobs:
1. make a fashion-shop owner feel the sale they lose every day, and see it come back as a paid one;
2. send them to **Try the demo** (built in Phase 7, at `/demo/`) or **Talk to us on WhatsApp**.

**Register:** brand (a marketing page), not product. So it's allowed more expression and motion than the app, but it stays inside the brand rules in §3.

## 2. The concept: "The slip that comes back" (Direction A)

One missed sale, written on a shop slip ("Black sneaker · 42 · Grace · 07xx"), travels down the page and comes back as a paid receipt:
- **Logged** (the visitor fills in the slip themselves in the hero);
- **To order**;
- **Set aside** (a tag on the real item);
- **Sent** (a WhatsApp with a photo);
- **Replied** (it turns **clay**, the only clay on the page);
- **Deposit** (M-Pesa);
- **Paid** (a stamped receipt).

The page goes from dark (closing time, the lost sale) to light (morning, stock in, paid). The empty spot on the shelf in the hero is filled in the footer.

**Why this one:**
- It's the exact story: one lost sale becoming one paid sale, in the shop's own words.
- It works at 360px with no 3D. Desktop gets the 3D as a bonus.
- It teaches what clay means before visitors open the app.

Direction B (a 3D wall that fills up) was rejected: it falls apart on phones.

## 3. Rules the site follows

| Topic | Decision |
|---|---|
| **Colours** | Petrol `#0B6670` (light sections) and the app's existing dark-theme petrol `#5DB6BE` (dark sections). Clay `#B4491F` / `#E5875D` only for "a customer replied". Stone neutrals. **The dark sections use the app's approved dark-theme colours, so no new colour is needed.** Checked: dark petrol on the dark page 7.9:1, dark clay 7.1:1 (AA passes). Answers the direction's question 3 |
| **Never** | Blue, violet, neon, glow, frosted glass, gradient text, chrome 3D icons, auto-slideshows, fake crowds ("trusted by hundreds"), partner logos we don't have |
| **Type** | IBM Plex Sans; Plex Mono for slip details (sizes, phone numbers, KSh); **IBM Plex Sans Condensed SemiBold** for big headlines only (one weight, Latin subset). Needs your yes, §8 |
| **Motion feel** | Calm and certain. "Settle" (400–700ms strong ease-out) for things arriving, "Quick" (150–250ms) for taps. No bounce, overshoot or spin. Scroll motion follows the finger |
| **Phones** | Native scrolling (no scroll-hijacking library). CSS transforms and opacity only; no animated blur, shadows or filters. No pinned sections on phones. 3D only at ≥1024px wide, not in Data Saver mode, and not with reduced motion |
| **Reduced motion** | Every section tells the full story with no motion: final states, plain step lists, final numbers, nothing auto-plays |
| **Numbers** | Every figure says **Example** in visible text. "Recovered" means **paid in full**, which is the app's own rule (a deposit means "Reserved"). Answers the direction's question 10 |
| **Speed** | First load on a phone under ~400 KB. Hero image ≤30 KB at 360px (AVIF/WebP). Video loops ≤600 KB, loaded only when near the screen and never in Data Saver mode. Headline readable before any script runs |
| **Accessibility** | WCAG AA, keyboard-usable mini demo and FAQ, tap targets ≥48px, alt text, captions for any narrated video |
| **Images** | **No Pinterest image is ever used on the site:** they belong to others, and most show trademarks. They're mood references only. We use our own photos, licensed stock with East African photographers, or generated images for **textures only** (never people or shops presented as real) |

## 4. Page plan

As in §4 of the creative direction, section by section:
1. **Hero:** "She asked for a 42. You had a 41. Don't lose her." Plus a live four-tap mini demo (item → size → reason → phone → "✓ Saved. Grace is waiting"), and the slip landing in the shelf gap. Desktop: the item in 3D, tilting with the cursor.
2. **The problem:** the page darkens. The paragraph lights up phrase by phrase as you scroll, over a strip of items people asked for (Example).
3. **How it works, in six steps:**
   - desktop: a pinned phone showing real app clips, with the slip travelling a dotted path and the background lightening step by step;
   - phone: six stacked cards with a progress rail.
4. **Key features:**
   - the shop link and QR code;
   - Excel stock import;
   - working offline at the counter;
   - Ask ("What should I order?").
   
   Each card has a small animation that plays once.
5. **Works in your shop:** a real shop photo with solid chips over it (WhatsApp sent, M-Pesa deposit (Example), saved offline, any Android phone).
6. **Example numbers:** counters roll up, a petrol sparkline draws in, and the clay appears only on "Replied". Everything is labelled Example.
7. **Try the demo:** the phone mock. Desktop only: a slowly turning curved shelf of the sample shop's items.
8. **FAQ.**
9. **Footer:** the shelf gap filled, with the PAID slip; both calls to action.

**Copy:** I'll write the FAQ answers from facts the app already has (customers install nothing, any phone with a browser, offline capture, M-Pesa deposit prompts, Excel import, invitations). The price answer waits on §8.

## 5. How it's built

- **Where:**
  - a separate static website in `../retail-os-marketing`;
  - on launch, served by Nginx on the same VPS at your main domain (e.g. `yourbrand.co.ke`), with the app at `app.yourbrand.co.ke`;
  - "Try the demo" links to `app.…/demo/`.
- **Technology:**
  - plain HTML, CSS and a little JavaScript;
  - modern CSS scroll-driven animation where the phone's browser supports it, with a simple fallback elsewhere;
  - **Three.js only for the two desktop 3D moments**, loaded only when needed;
  - no React, no Tailwind and no GSAP, in line with the project's rules. Every effect in the direction can be built without them, and the phone stays light.
- **Built in stages, so it works before every photo exists:**
  1. All sections, motion and the mini demo, using **clearly marked placeholder frames** where photos are missing (never borrowed images). The slip, icons, chips and sparkline are drawn by us in SVG.
  2. Real app screen recordings, made from the demo shop. I can make these myself.
  3. Real shop photos as they arrive. The empty-shelf and restocked frames must be shot on a tripod from the same spot.
  4. The desktop hero 3D. Until a real 3D model of the item exists, a layered-photo effect (2.5D) stands in for it.
- **The launch video:** made with `brag` from the finished site and the demo (installed and reviewed 28 Oct).

## 6. Checks before you sign off

- **Lighthouse on a mid-range Android profile:** Performance ≥90, Accessibility 100. First load under the budget in §3.
- **Screens:** at 360, 768 and 1280px, light sections and dark sections.
- **Reduced motion on:** the whole story still reads.
- **Data Saver on:** no 3D or video loads.
- **Brand check:** clay appears only on "Replied", and nothing breaks the "Never" list.

## 7. Not in this phase

- Self sign-up, pricing pages and billing (Phase 7 §2 and §6, later).
- A Swahili version of the whole site, unless you choose it in §8.
- Blog, careers and press pages.

## 8. Your decisions

1. **Brand name and domain:** is it "Retail OS", or another name? This blocks the launch, not the build.
2. **Language:** English only; English with a few Swahili phrases (e.g. "From *sina size yako* to paid"); or a full Swahili version as well?
3. **The running example:** "Grace" and a black sneaker in size 42? Or a bag or dress, if that fits your first shops better?
4. **WhatsApp and M-Pesa logos:** show them (within their brand rules), or words only with our own icons?
5. **Price on the site:** show a price, or "pricing on invitation"?
6. **Your WhatsApp number**, and the pre-filled first message (e.g. "Hi, I run a shop and want to try Retail OS").
7. **Photos:** can we photograph 3–5 real partner shops (with signed permission)? If not yet, we start with licensed stock and placeholders.
8. **Display typeface:** IBM Plex Sans Condensed for big headlines, yes or no?
9. **Visitor counting:** none at launch, or a cookie-free counter you host yourself (e.g. Umami on your VPS, free), which needs no cookie banner?
