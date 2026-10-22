# Phase 2 design brief: design system, app shell, sign-in and Settings

**Status:** draft for the owner's confirmation · 22 Oct 2026
**Inputs:** `PRODUCT.md`, `DESIGN.md`, the approved spec (`docs/design/retail-os-design-spec.html`), and the owner's answers on 22 Oct:
- convert all current pages now
- build the working core of Settings
- follow the device's theme, light first

Visual-direction probes were skipped because this environment has no built-in image generation. The spec's mockups are the visual reference.

## 1. Feature summary

Replace the neon frame with the Retail OS design system: tokens, IBM Plex, components as Django template partials, and one responsive shell (sidebar on desktop, slim sidebar on tablet, bottom tab bar on phone). Every current page moves into the shell with the new look, sign-in becomes plain, and Settings gets its working core. Shop owners and staff should see one calm, consistent tool on any device from this phase on.

## 2. Primary user action

From any screen, reach any job in one tap, and **log a missed sale from anywhere**: the top-bar button on desktop and tablet, the central **+** on the phone tab bar.

## 3. Design direction

- **Colour strategy:** Restrained. Tinted green-grey neutrals, petrol as the only accent (primary actions, current selection, focus), status tones only on badges. Clay is used only for "a customer is waiting on you" (the In conversation badge and the unread count).
- **Scene:** a shop owner at the till under bright shop lights or daylight, a budget Android phone in one hand, mid-conversation with a customer. **Light is the default.** The app follows the device when it's set to dark, and each person can override this in Settings → Look.
- **Anchors:**
  - **Shopify admin (Polaris):** page header with one primary action, index tables, settings as a list of sections.
  - **Odoo Settings:** grouped settings with plain help text next to each control.
  - **Linear:** density and calm; nothing decorates, everything is reachable.
- **Not this:** neon, glow, blur, gradients, background photos, blue or violet, sand and clay mixes, floating cards, fake numbers, or customise buttons on the dashboard.

## 4. Scope

- **Fidelity:** production-ready, shipped quality.
- **Breadth:**
  - the shell
  - sign-in and the "no shop yet" page
  - **every current page** (dashboard, missed sales list and form, products list and form, customers list and form, messages, the simulator restyled)
  - Settings core
- **Interactivity:** real Django pages with server-rendered forms. JavaScript only where the current pages already need it (charts, the quick-record panel's add-customer/product/variation steps).
- **Time intent:** polish until it ships. Phase 3 then redesigns the key screens (Home work queue, Waiting, To order, Conversations, Floor mode); Phase 2 gives them their building blocks.

## 5. Layout strategy

**Shell**

| Screen | Navigation | Top bar |
|---|---|---|
| Phone (< 600px) | Bottom tab bar: Home · Missed sales · **+** · Messages · More. "More" opens a sheet with Products, Customers, Reports, Settings, Sign out | Shop name and avatar |
| Tablet (600–1023px) | Slim sidebar: icons with short labels under them | Search slot and **Log missed sale** |
| Desktop (≥ 1024px) | 220px sidebar: shop at the top; groups Customers / Stock / Shop; Settings and the account at the bottom | Search slot, **Log missed sale**, avatar |

Only pages that exist get a nav item, so there are no dead links. Phase 3 adds Waiting, To order and Conversations, and renames items as they're rebuilt.

- **Page pattern:**
  - **Header:** title (21px/600), a one-line description, and at most one primary action plus secondary actions.
  - **Content:** max 1200px wide for lists, 720px for forms.
  - **Spacing rhythm:** 24px between sections, 16px inside panels.
- **Lists:** index tables on desktop and tablet; on phones each row becomes a stacked card with the key value right-aligned. Status always shows as a badge (dot plus word).
- **Forms:** one column, label above the control, help text below, and the error message under the field in crit colour. Save is at the bottom; there's no sticky save bar in this phase.
- **Settings:**
  - **Desktop and tablet:** two panes, a section list on the left and the open section on the right.
  - **Phone:** the section list is one page; each section opens as its own page with a back link.

## 6. Key states

| State | What the user sees |
|---|---|
| Signed out | Plain sign-in: logo, "Sign in to your shop", username or email, password, a Sign in button, and errors in plain words |
| Signed in, no shop | Existing explanation page, restyled |
| Role differences | Cashiers see Settings → Your account and Look only. Owners see everything. Managers see everything except Shop details and Team and roles |
| Empty lists | One sentence on what will appear, plus the action that creates the first item ("No missed sales yet. Log the first one when a customer can't buy.") |
| Saving | Button shows a working state; on success, a toast "Saved" (150–250ms slide, respects reduced motion) |
| Form errors | Field-level messages that say how to fix it; the page scrolls to the first error |
| Permission denied | A clear page saying who can do this ("Only the owner can change team members") with a way back |
| Dark mode | Same layout, dark tokens from DESIGN.md, all text AA |
| Slow connection | Pages work without JavaScript except charts; fonts load with a system-font fallback (`font-display: swap`) |

## 7. Interaction model

- Navigation is plain links; the current page is highlighted (surface-2 background, petrol icon).
- **Log missed sale** opens the existing capture form as a page, not a modal. The form's inline "add customer, product or size" steps stay as small panels until Floor mode replaces them in Phase 3.
- Settings forms post normally and redirect back with a "Saved" toast. Destructive actions (removing a team member, deleting a product type) ask for confirmation on the page itself.
- Keyboard: visible 2px petrol focus ring everywhere, logical tab order, and Escape closes the phone "More" sheet.
- Motion only confirms: toast in and out, the sheet sliding up on phones, a button press scale of 0.97. No page-load animation.

## 8. Content requirements

**Navigation labels:** Home, Missed sales, Products, Customers, Messages, Reports, Settings, Log missed sale, More, Sign out.

**Settings sections (working core)**

| Section | Who | Fields |
|---|---|---|
| Your account | Everyone | First and last name, email, phone, change password |
| Look | Everyone | Theme: Match device / Light / Dark (saved per person) |
| Shop details | Owner | Shop name, phone region (Kenya default), currency, time zone |
| Product types and options | Owner, Manager | List of types. For each: name, up to three option names, and suggested values ("36, 37, 38…"). Add a type; delete one only when no product uses it |
| Team and roles | Owner | Members with role; add a member (name, username, temporary password, role); change role; remove (never the last owner); the "Cashiers can add products" switch |
| Follow-ups and holds | Owner, Manager | Reminder days ("2, 4, 7"), days until expiry after the last reminder, days a unit is held, days to pick up a reservation. These become per-shop values that the automation reads |
| Messaging | Owner, Manager | The default channel for new customers (WhatsApp / SMS / Email), and a read-only line per channel showing what's connected ("WhatsApp: simulator, nothing is sent"). Provider keys stay in `.env` |

**Moved to Phase 3:** Home layout per role (Home doesn't exist yet).

**Removed:**
- the browser currency switcher with made-up exchange rates (currency comes from Shop details)
- the theme toggle in the sidebar (it moves to Settings → Look)
- the background photo

## 9. Recommended references during the build

`reference/spatial-design.md`, `reference/interaction-design.md`, `reference/responsive-design.md`, `reference/typography.md`, `reference/color-and-contrast.md`, plus `reference/product.md` (product register). Then `audit` and `polish` before sign-off, checked at 360, 768 and 1280px in both themes.

## 10. Build notes and open questions

- **CSS:** `static/css/tokens.css` (light and dark tokens, OKLCH with hex fallbacks matching DESIGN.md), `base.css`, `components.css`. No Tailwind; delete `static/js/tailwind.js` and `static/images/dashboard_bg.png`. Replace the 556 KB favicon with a small SVG mark.
- **Fonts:** self-host IBM Plex Sans (400, 500, 600) and Plex Mono (400) as woff2, Latin subset, SIL Open Font Licence.
- **Icons:** a small Lucide SVG sprite (ISC licence), only the icons used.
- **Partials:** `templates/ui/` holds button, badge, field (with label, help and error), page header, empty state, table, toast, nav item and status bar. Python form widgets lose their long class strings; one field partial renders every form.
- **Charts:** Chart.js stays, loaded only on the dashboard, coloured from tokens (petrol and neutrals). Phase 3 replaces this dashboard anyway.
- **Page weight:** under about 200 KB per page before product photos and charts.
- **Open:** the shop logo upload belongs with Shop details, but the mark only needs it for sign-in and receipts later. Proposal: add the field now and display it from Phase 3.

## Done when

- [ ] The shell works at 360, 768 and 1280px in light and dark.
- [ ] Every current page renders in the new shell with the new components.
- [ ] Tailwind, the neon CSS and the background image are gone.
- [ ] The Settings core works with the role rules above.
- [ ] Automation reads the per-shop follow-up and hold values.
- [ ] Tests cover settings permissions and that every page loads.
- [ ] `audit` passes (contrast, focus, tap targets) and `polish` has been run.
