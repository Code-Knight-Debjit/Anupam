---
target: public marketing site
total_score: 18
max_score: 40
na_heuristics: 
p0_count: 2
p1_count: 3
timestamp: 2026-07-31T12-29-08Z
slug: templates-core-home-html
---
⚠️ DEGRADED: single-context (user declined sub-agent spawn)

Target: Anupam Bearings public marketing site — `templates/core/*`, `templates/products/*`, `templates/contact/*`, `templates/base.html`, `static/css/main.css`, `static/js/main.js`
Mode: Persuade
Evidence: Django dev server at :8765, Chrome desktop @1440 (home full scroll, products list), `detect.mjs` CLI scan, full source read. Mobile @390 and product-detail browser passes NOT captured — Chrome extension disconnected mid-run. Mobile findings below are inferred from CSS/markup and labeled as such.

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Enquiry success is a 4s toast then nothing; chatbot can spin 45s on typing dots; count-up stats display false intermediate numbers |
| 2 | Match System / Real World | 3 | Genuinely fluent bearing vocabulary; undercut by "Uncategorized" and "gcfgcfvb" surfacing as public taxonomy |
| 3 | User Control and Freedom | 1 | Unskippable 3.4s intro; two autoplay carousels with no pause; modal has no Esc; select auto-navigates |
| 4 | Consistency and Standards | 2 | `.btn-primary` defined 8× in one stylesheet; `›`/`→`/`>` + emoji icons + inline SVG mixed; 3 different support emails |
| 5 | Error Prevention | 1 | Both forms `novalidate` with zero client validation; 3 of 4 hero CTAs point at anchors that don't exist |
| 6 | Recognition Rather Than Recall | 2 | Search and category filter are placeholder-only, no labels; enquiry modal drops all product specs |
| 7 | Flexibility and Efficiency | 1 | Complete typeahead in main.js is dead code (bound to an id no template renders); no bulk enquiry; no spec filtering |
| 8 | Aesthetic and Minimalist Design | 3 | Real strength — dark hero, disciplined orange, confident type scale; chatbot bubble permanently covers body copy |
| 9 | Error Recovery | 1 | Three generic toasts total; no field-level errors; empty catalog tells the customer to run `python manage.py seed_data` |
| 10 | Help and Documentation | 2 | RAG chatbot is a real asset but slow and unscoped; no sizing guide, cross-reference, or datasheets |
| **Total** | | **18/40** | **Poor — major UX overhaul required** |

Every heuristic applies. 7 and 10 are not `n/a` here: the site ships a searchable catalog with pagination and sells technical parts where spec guidance is the purchase decision.

## Design Specificity Verdict

**LLM assessment.** Split verdict, and the split is the whole story.

The *surface* is specific. The Timken product photography is excellent and genuinely owned. The bearing-race SVG in the intro is a real idea. The copy speaks fluent industry — "SNT Plummer block", "four-row cylindrical and tapered roller bearings for hot and cold rolling", "axle boxes, bogies, and marine propulsion". Nobody wrote that from a template.

The *structure* is completely interchangeable. Hero carousel → about split with animated stat counters → 5 category cards → 4 numbered "why us" cards → industries carousel → dark CTA banner → 6-column mega footer. That is the default 2019 industrial-distributor template. Replace the photos and the copy and this is any B2B supplier in any category.

And the specific thing the business actually has never becomes a design idea. Anupam Bearings' real assets are 150,000 SKUs, two warehouses, and decades of matching a part number to a machine that is currently stopped. The interface expresses none of that. There is no part-number lookup, no SKF→Timken cross-reference, no bore/OD/width filter, no stock indicator, no "is this in Bengaluru or Chennai today". A maintenance engineer whose line is down at 2am — the actual buyer — has no path here except a search box and a contact form. The most valuable inventory in the business is presented as body copy.

**Deterministic scan.** `detect.mjs` on `templates/base.html templates/core templates/products templates/contact`: **1 finding**, severity warning — `overused-font` at `templates/base.html:75` (Space Grotesk). Exit 0.

The detector under-reported: line 75 loads **both** Space Grotesk and Inter, and Inter is named in that same rule's description. Two overused faces, one flagged. The detector also cannot see the defects that matter here, all of which are content and behavior rather than markup pattern — it passed a page that ships keyboard-mash test data.

**Visual overlays.** Not attempted. The Chrome extension disconnected before the injection step, so no user-visible overlay exists. Do not expect highlights in the browser.

## Overall Impression

Someone with real taste built this, and then it shipped without anyone reading it as a stranger would. The hero is legitimately good — better than most of its category. Then the homepage carousel rotates to a card labeled **"gcfgcfvb"** with the description **"asjjd"**, next to a category card called **"Uncategorized"**.

The gap here is not design ability. It is that nothing in the pipeline separates "demo state" from "production state." Test rows, seed-data instructions, hotlinked Unsplash placeholders, and three contradictory inventory figures all reach the customer. On a B2B site whose entire job is to make an unfamiliar supplier look competent enough to send a purchase order to, that is the product.

Biggest opportunity: stop treating the catalog as a grid of cards and start treating it as a part-number lookup. That is the one move that would make this site not-interchangeable.

## What's Working

**The hero composition.** Dark ground, Timken product photography bled to the right edge, orange accent used once on one word. The product photography is doing real work — you can read the roller cage and the race. Most competitors use a stock factory photo with a blue gradient over it. This does not.

**The domain voice.** "Our specialists guide you to the exact right bearing — not the nearest match." That is a sentence written by someone who understands that the buyer's fear is getting a part that almost fits. The industry card copy is similarly precise. This is the strongest raw material on the site.

**Genuinely accessible bones in places.** `role="navigation"` with a label, `aria-label` on every icon button, `role="log"` + `aria-live="polite"` on the chat transcript, correct `width`/`height` on hero images to prevent layout shift, `loading="lazy"` used correctly below the fold. Someone knew what they were doing; it just was not applied evenly.

## Priority Issues

### [P0] Placeholder and test content is live on the homepage
- **What**: The "Industries We Serve" carousel renders a card titled **`gcfgcfvb`** with description **`asjjd`** and tag "LEARN MORE" (`templates/core/home.html:296-317`, from DB). The homepage category grid renders a card called **`Uncategorized`** and one called **`Bearings`** that duplicates `Rolling Bearings`, both with empty descriptions (verified in rendered HTML). The empty-catalog state prints **"Run `python manage.py seed_data` to load products"** to the customer (`templates/products/product_list.html:137`). Twelve `images.unsplash.com` hotlinks ship on every homepage load, and photo `1504328345606` illustrates both "Heavy Engineering" and "Steel Rolling Mills".
- **Why it matters**: This is the first screen a purchasing manager sees before deciding whether to trust you with an order. Keyboard mash next to a Timken certification badge does more damage than a plain page would. The `seed_data` line additionally tells a stranger what stack you run and that the catalog is unseeded.
- **Fix**: Filter `industries` and `categories` querysets to published/non-empty records in the view. Delete the "Uncategorized" and duplicate "Bearings" categories or exclude them from public queries. Rewrite the empty state as customer copy ("Our catalogue is being updated — call +91-98844-00741 and we'll check stock for you"). Host the industry photography locally or drop the fallback section entirely.
- **Suggested command**: `/impeccable harden`

### [P0] Both "Call" buttons on the contact page dial a number that appears nowhere else
- **What**: `templates/contact/contact.html:90` — "Call Chennai" → `tel:+919840088509`. Line 116 — "Call Bengaluru" → `tel:+919840088509`. Same number for both cities, and it matches neither the Chennai number printed directly above it (044-4691-2265) nor the Bengaluru one (+91-98844-00741), nor either number in the footer.
- **Why it matters**: The highest-intent action on the entire site. A buyer who taps the primary orange button on the contact page reaches an unknown number. On mobile that button *is* the conversion.
- **Fix**: Point each button at the number printed in its own card. Add a phone-number constant or model field so the footer, hero CTA, contact cards, and chatbot fallback messages cannot drift apart — there are currently at least five hardcoded phone numbers across templates and JS.
- **Suggested command**: `/impeccable clarify`

### [P1] The inventory claim contradicts itself three ways on the same visit
- **What**: Homepage stat card: `data-count="150000"` → "150,000+ bearing types in inventory" (`home.html:139`). Homepage "why us" card: "Over 1,50,000 bearing types in stock" (`home.html:232`). Products page hero: **"500+ genuine Timken bearing products"** (`product_list.html:27`). And because the counter animates from 0 over 2 seconds, a visitor who scrolls at normal speed reads **"479+ customers"** and **"14365+ bearing types"** — I captured exactly that mid-scroll.
- **Why it matters**: Inventory depth is the single reason to pick a distributor over the manufacturer. Stating it three different ways signals that none of the numbers are real. And the count-up animation makes the trust number *false* for the duration it is on screen — the one element on the page that must be believed is the one showing wrong values.
- **Fix**: Pick one figure, source it from the database if possible, and use it everywhere. Kill the count-up animation on trust figures — render the final number immediately. Animated counters are decoration applied to the one place decoration costs credibility.
- **Suggested command**: `/impeccable clarify`

### [P1] Motion the visitor cannot stop, skip, or opt out of
- **What**: A full-screen intro overlay blocks the homepage for **3.4s desktop / 2.6s mobile** with no skip affordance — no click-to-dismiss, no Esc, no button (`main.js:8-23`). The hero carousel auto-advances every 5s and `startAuto()` restarts even after manual interaction (`main.js:235-256`). The industries Swiper autoplays every 3.5s with `disableOnInteraction: false`, so it resumes even after the user grabs it (`home.html:550`). A cursor-glow div follows the mouse on every desktop page (`main.js:563-571`). And there are **zero** `prefers-reduced-motion` rules in 68KB of CSS — I grepped; the count is 0.
- **Why it matters**: WCAG 2.2.2 (Pause, Stop, Hide) and 2.3.3 both fail. A visitor with vestibular sensitivity gets no relief anywhere on the site. Everyone else gets 3.4 seconds of nothing before the first content on a page where bounce is measured in seconds — and a hero that rotates the offer away while they are reading it.
- **Fix**: Add a skip control to the intro and cap it at ~1.2s, or drop it. Pause both carousels on hover and on focus, and stop autoplay permanently after any manual interaction. Wrap every animation in `@media (prefers-reduced-motion: no-preference)` and add a reduced-motion block that sets `animation: none; transition: none`.
- **Suggested command**: `/impeccable animate`

### [P1] Forms have no validation and one generic error message
- **What**: Both the contact form (`contact.html:33`) and the enquiry modal (`base.html:242`) carry `novalidate`, and `main.js` adds no client-side validation — it serializes and POSTs whatever is there (`main.js:330-388`). Native browser validation is disabled and nothing replaces it. Every failure produces one of three strings: "Failed to send. Try again.", "Failed to send. Please try again.", "Network error. Please try again." No field is ever named. Success is a toast that disappears after 4 seconds (`main.js:538`) with no confirmation screen, no reference number, and no statement of when anyone will reply. The enquiry modal has no Esc handler and no focus trap. On the contact form **Phone is required and Email is optional** — the reply channel is the optional one.
- **Why it matters**: This is the conversion moment for the whole site. A buyer who mistypes an email gets "Failed to send. Please try again." and no idea what to fix; most will leave rather than guess. A buyer who succeeds gets a 4-second toast and then silence — no artifact proving the enquiry exists.
- **Fix**: Remove `novalidate` or add real inline validation with field-level messages. Replace the success toast with a persistent confirmed state that names the product, echoes the contact details, and commits to a response window. Bind Esc to close and trap focus in the modal. Make Email required.
- **Suggested command**: `/impeccable harden`

## Persona Red Flags

**Jordan (confused first-timer)** — Waits 3.4 seconds at a black screen before seeing anything, with no indication it is loading versus broken. Reaches the homepage and the first product taxonomy card says "Uncategorized". Scrolls to "Industries We Serve" and reads "gcfgcfvb". Clicks "View Housings ›" in hero slide 2 and lands at the top of an unfiltered 500-product catalog, because `#bearing-housings` does not exist on that page — the products template has no such id. Jordan cannot tell whether the site is broken or the company is. Abandons before the contact form.

**Riley (stress tester)** — Submits the contact form empty: `novalidate` plus no JS validation means it POSTs, and the response is a generic toast. Types `<script>` in the product search: the dead typeahead would inject `q` straight into `innerHTML` at `main.js:627` and product names unescaped at 635 — latent XSS the moment that feature is wired up. Opens the enquiry modal and presses Esc: nothing happens, and `document.body.style.overflow` stays `hidden`. Tabs through the hero: `.hero-slide` uses `opacity:0` rather than `visibility:hidden`, so all four slides' links stay in the tab order and all **four `<h1>` elements** stay in the accessibility tree. Views source and finds `id="industries-heading"` duplicated (lines 285 and 333) and a hidden 10-slide carousel shipped on every load.

**Casey (distracted mobile, one thumb, factory floor)** — Burns 2.6s on the intro over a 3G connection that has not yet delivered the hero image. Every primary action sits at the top of the screen; the thumb zone holds only the chatbot FAB. `.btn-primary` on mobile computes to roughly **38px tall** (`padding:.7rem .875rem` at `font-size:.8rem`, `!important`), under the 44px minimum — inferred from CSS, not measured in-browser. The Name/Phone row on the contact form uses an **inline** `grid-template-columns:1fr 1fr` with no class and no media query (`contact.html:35`); with exactly one `[style]`-attribute selector in the entire 68KB stylesheet, it almost certainly stays two-up at 390px, giving ~170px-wide inputs. Two Google Maps iframes load on that same page. Gets interrupted mid-enquiry, returns, and the modal is gone with the form reset — nothing is persisted.

## Minor Observations

- `.btn-primary` is redefined **8 times** in `main.css`, including three identical `{width:100%;justify-content:center}` blocks and one `!important` override. The primary button has no single source of truth.
- `main.css` is committed as a **single 68,832-byte minified line**. There is no unminified source in the repo. Every future design change is an edit to a one-line file. `staticfiles/` also holds a stale 130KB unminified copy and an empty hashed file.
- Google Fonts is loaded **twice** — `@import` at `main.css:1` and `<link>` at `base.html:75`. The `@import` serializes the font request behind the CSS download. The `<link rel="preload" as="style">` two lines above the real stylesheet link buys nothing.
- Three external origins on every page: cdnjs (GSAP + ScrollTrigger), jsdelivr (Swiper CSS + JS), Google Fonts. Swiper's CSS is render-blocking in `extra_head`.
- The live-search typeahead (`main.js:576-647`) — debounced, arrow-key navigable, with match highlighting — binds to `#product-search-input`, an id that appears in **no** public template. A finished feature nobody can reach.
- `main.js:260-280` filters `.products-section` elements on category-tab click. Those elements do not exist in `product_list.html`; the tabs navigate via `onclick="window.location=..."` instead. Dead handler racing a page load.
- Category tabs are `<button onclick="window.location=...">` — no middle-click, no open-in-new-tab, announced as "button" not "link". "Enquire Now →" is `<a href="#">` — a link that is not a link.
- `rgba(255,255,255,0.35)` on the footer's "Bengaluru · Chennai" line at 0.8rem computes to roughly **3.1:1** against the near-black footer — below AA's 4.5:1.
- No skip-to-content link and no `sr-only` utility anywhere in the stylesheet, despite `<main id="main-content">` being ready for one.
- `<p class="category-card-cat"></p>` (`home.html:175`) is empty on every category card, reserving vertical space for nothing.
- The footer is 6 columns of 22 links, which the grid wraps into a second row leaving a large void to the right of "Contact".
- Support email differs by surface: `info@` (footer, Chennai card), `sales@` (footer), `blr@` (Bengaluru card).
- Hero slide 3's headline reads "Automatic & Lubrication Pumps & Speciality Lubrications." — two ampersands, a trailing period in a display headline, and a label above it that repeats itself ("Automatic Lubrication & Lubrications").
- Slider dots carry `role="tab"` inside `role="tablist"` with no `aria-selected` and no tabpanel — broken ARIA is worse than none.
- Detector: `overused-font` at `base.html:75`. Not a false positive, but the least consequential finding on this page.

## Questions to Consider

- The business's real advantage is 150,000 SKUs and two warehouses. Why is there no part-number search on the homepage — the one thing a maintenance engineer with a stopped line actually needs?
- What would this site look like if the hero were a search field instead of a carousel?
- A buyer holding an SKF part number needs the Timken equivalent. That cross-reference is the highest-value page you could build, and it does not exist. Why not?
- The chatbot can take 45 seconds to answer. Would a "call this number now" button convert better than any of it?
- If a visitor sees exactly one screen, is a rotating hero the right bet — or should slide 1 simply be the whole hero?
