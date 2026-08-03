# Design System Specification: Industrial Precision & Editorial Depth
 
## 1. Overview & Creative North Star: "The Kinetic Architect"
This design system moves away from the static, "boxy" nature of traditional industrial sites. Our North Star is **The Kinetic Architect**. We aim to mirror the high-precision world of bearing manufacturing: frictionless movement, perfect structural integrity, and heavy-duty reliability. 
 
To achieve a premium B2B feel, we utilize **Intentional Asymmetry**. By breaking the standard centered layout and using generous, purposeful white space, we create an editorial experience that feels curated rather than templated. We replace rigid lines with tonal depth, suggesting that the interface—like a precision bearing—is a series of perfectly machined layers working in harmony.
 
---
 
## 2. Color & Surface Philosophy
We leverage a high-contrast palette where deep blacks and industrial greys are punctuated by a high-energy "Kinetic Orange."
 
### The "No-Line" Rule
**Strict Mandate:** Designers are prohibited from using 1px solid borders to define sections. 
Boundaries must be created through:
*   **Background Shifts:** Moving from `surface` (#fbf8fd) to `surface-container-low` (#f5f3f8).
*   **Tonal Nesting:** A `surface-container-highest` card sitting on a `surface-container-low` background. This creates a "machined" look where elements feel recessed or extruded from a single block of material.
### Signature Textures & Glass
*   **The Glassmorphism Rule:** Floating elements (like the navigation and chatbot) must use semi-transparent surface colors with a `backdrop-filter: blur(12px)`. This prevents the UI from feeling "pasted on" and allows the industrial imagery to bleed through.
*   **Machined Gradients:** Use a subtle linear gradient (135°) from `primary` (#a14000) to `primary_container` (#ff6a00) for primary CTAs. This mimics the light reflection on polished metal.
---
 
## 3. Typography: Mechanical Geometry
The type system pairs the brutalist, geometric strength of **Space Grotesk** with the utilitarian clarity of **Inter**.
 
*   **Display & Headlines (Space Grotesk):** These are our "structural beams." Use `display-lg` for hero sections with tight letter-spacing (-0.02em) to emphasize mechanical precision.
*   **Body & Labels (Inter):** These represent our "technical manuals." They must be highly legible. Use `body-md` for standard prose and `label-sm` (all caps, +0.05em tracking) for technical specifications or categories.
| Role | Token | Font | Size | Weight |
| :--- | :--- | :--- | :--- | :--- |
| Hero | `display-lg` | Space Grotesk | 3.5rem | 700 |
| Section | `headline-md` | Space Grotesk | 1.75rem | 600 |
| Subhead | `title-lg` | Inter | 1.375rem | 500 |
| Prose | `body-lg` | Inter | 1.0rem | 400 |
 
---
 
## 4. Elevation & Depth: Tonal Layering
We avoid the "shadow-heavy" look of consumer apps. Instead, we use **Tonal Layering** to define hierarchy.
 
*   **The Layering Principle:** 
    *   Base Floor: `surface` (#fbf8fd)
    *   Recessed Content: `surface-container-low` (#f5f3f8)
    *   Primary Cards: `surface-container-highest` (#e4e2e6)
*   **Ambient Shadows:** For floating elements (Modals, Chatbot), use a "Ghost Shadow": `0px 20px 40px rgba(27, 27, 31, 0.06)`. The shadow must be large, soft, and barely perceptible.
*   **Ghost Borders:** If a separator is required for accessibility, use the `outline_variant` (#e2bfb0) at **15% opacity**. Never use pure black or high-contrast lines.
---
 
## 5. Signature Components
 
### The Kinetic Chatbot (Floating Action)
*   **Visuals:** A 64px circle using the Machined Gradient (`primary` to `primary_container`).
*   **Effect:** A subtle "pulse" animation using a secondary ring at 30% opacity that expands and fades every 3 seconds, suggesting a mechanical heartbeat.
*   **Glass Shield:** When expanded, the chat window uses `surface-container-lowest` with 80% opacity and a heavy backdrop blur.
### Sticky Navigation (The "Precision Rail")
*   **Structure:** A slim, full-width bar. 
*   **Style:** `surface-container-lowest` at 85% opacity.
*   **Interaction:** On scroll, the container height subtly contracts from 80px to 64px, mimicking a mechanical part locking into place.
*   **Active State:** Instead of an underline, use a 4px `primary` dot centered beneath the active nav item.
### Technical Spec Cards
*   **Rule:** Forbid the use of divider lines.
*   **Layout:** Use 24px vertical white space between attribute blocks. Use `label-sm` in `secondary` (#5f5e5e) for titles and `title-sm` in `on_surface` (#1b1b1f) for values.
*   **Corner Radius:** Strict `sm` (0.125rem) for a sharp, industrial feel.
### Buttons (Machined Action)
*   **Primary:** Machined Gradient, white text, `md` (0.375rem) radius. Hover state: slight increase in gradient saturation.
*   **Secondary:** Ghost Border (15% opacity `outline`) with `on_surface` text. Hover state: shift background to `surface-container-high`.
---
 
## 6. Do’s and Don’ts
 
### Do
*   **DO** use asymmetric margins (e.g., 10% left, 20% right) for hero text to create an editorial, high-end feel.
*   **DO** use "Industrial Breathing Room." Give technical specs 2x the padding you think they need.
*   **DO** use `surface-tint` (#a14000) at 5% opacity for large background sections to add warmth to the dark grey/black scheme.
### Don't
*   **DON'T** use 1px solid borders. This immediately cheapens the B2B experience.
*   **DON'T** use standard "drop shadows" (e.g., `offset-y: 2px, blur: 4px`). They feel like consumer-grade templates.
*   **DON'T** use generic icons. Use thin-stroke, geometric icons that match the weight of the Inter typeface.