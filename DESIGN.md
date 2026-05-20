---
version: alpha
name: Pawrrtal
description: >
  Craft Agents-inspired chat interface with a flat, editorial aesthetic. Six
  semantic colors, neutral interpolation variants, and a 16px-rooted Tailwind v4
  scale. Dual-theme (light + dark, Codex/GitHub-adjacent in dark). Default UI
  sans is Google Sans Flex, Google Sans, Helvetica Neue, sans-serif (loaded via
  @font-face rules in frontend/app/globals.css; token --font-sans-stack in
  frontend/app/globals.css).
colors:
  primary: "#9E94D5"
  on-primary: "#FFFFFF"
  background: "#F7F7F4"
  foreground: "#1F1F1F"
  accent: "#9E94D5"
  info: "#87C3FF"
  success: "#1F8A65"
  destructive: "#CF2D56"
  border: "#E8E0C9"
  muted-foreground: "#8A8888"
  user-message-bubble: "#E9EEF6"
  info-text: "#1A4F7A"
  success-text: "#0F4A2A"
  destructive-text: "#6B1A2A"
typography:
  display:
    fontFamily: Newsreader
    fontSize: 3rem
    fontWeight: 500
    lineHeight: 1.05
    letterSpacing: -0.025em
  h1:
    fontFamily: Newsreader
    fontSize: 2.25rem
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: -0.02em
  h2:
    fontFamily: Google Sans Flex
    fontSize: 1.875rem
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.015em
  h3:
    fontFamily: Google Sans Flex
    fontSize: 1.5rem
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.01em
  h4:
    fontFamily: Google Sans Flex
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.3
  body-lg:
    fontFamily: Google Sans Flex
    fontSize: 1.125rem
    fontWeight: 400
    lineHeight: 1.55
  body-md:
    fontFamily: Google Sans Flex
    fontSize: 1rem
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontFamily: Google Sans Flex
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
  caption:
    fontFamily: Google Sans Flex
    fontSize: 0.875rem
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0.01em
  code:
    fontFamily: JetBrains Mono
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
  sidebar-section-header:
    fontFamily: Google Sans Flex
    fontSize: 0.875rem
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: 0
  sidebar-row:
    fontFamily: Google Sans Flex
    fontSize: 0.875rem
    fontWeight: 500
    lineHeight: 1.35
  sidebar-group-meta:
    fontFamily: Google Sans Flex
    fontSize: 0.875rem
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: 0
rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 14px
  bubble: 20px
  bubble-tail: 2px
  full: 9999px
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
components:
  popover:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
  chat-composer:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: 12px
  bubble-user:
    backgroundColor: "{colors.user-message-bubble}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.bubble}"
    padding: 12px
  bubble-assistant:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    padding: 12px
  step-icon:
    backgroundColor: "{colors.foreground}"
    textColor: "{colors.background}"
    rounded: "{rounded.md}"
    size: 64px
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.none}"
    padding: 12px
  button-secondary:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.none}"
    padding: 12px
  badge-info:
    backgroundColor: "{colors.background}"
    textColor: "{colors.info-text}"
    rounded: "{rounded.sm}"
    padding: 4px
  badge-success:
    backgroundColor: "{colors.background}"
    textColor: "{colors.success-text}"
    rounded: "{rounded.sm}"
    padding: 4px
  badge-destructive:
    backgroundColor: "{colors.background}"
    textColor: "{colors.destructive-text}"
    rounded: "{rounded.sm}"
    padding: 4px
  status-dot-info:
    backgroundColor: "{colors.info}"
    rounded: "{rounded.full}"
    size: 8px
  status-dot-success:
    backgroundColor: "{colors.success}"
    rounded: "{rounded.full}"
    size: 8px
  status-dot-destructive:
    backgroundColor: "{colors.destructive}"
    rounded: "{rounded.full}"
    size: 8px
  button-link:
    textColor: "{colors.accent}"
    typography: body-md
  divider:
    backgroundColor: "{colors.border}"
    height: 1px
  dropdown-menu-item-disabled:
    backgroundColor: "Muted tray - Tailwind `bg-muted/50` (theme token `--muted`, see globals.css)"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.sm}"
  metadata:
    textColor: "{colors.muted-foreground}"
    typography: caption
  app-empty-state:
    backgroundColor: "Transparent or `{colors.background}` - tone-dependent (see prose)"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: "Tone-dependent spacing - sidebar/page/card/panel recipes (see prose)"
    typography: "sidebar-row / display / body-sm depending on tone"
  app-form-row:
    textColor: "{colors.foreground}"
    typography: "body-sm label - FieldLabel density for dialog bodies"
    padding: "Vertical rhythm locked between label, helper, control, error"
  app-dialog-callout:
    backgroundColor: "`foreground` wash (`bg-foreground/[0.04]`-`[0.05]`) - tone via prose"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: "12px comfortable density"
  app-dialog-footer:
    backgroundColor: "Inherits modal sheet surface"
    padding: "Sticky footer gap - `flex-col-reverse` narrow / `sm:flex-row sm:justify-end` wide"
  sidebar-nav-row:
    backgroundColor: "Hover `{colors.foreground}` @ 4%; selected @ 7%"
    textColor: "{colors.foreground}"
    rounded: "{rounded.sm}"
    padding: "Comfortable `min-h-9`; compact `h-8` density split"
    typography: sidebar-row
  sidebar-section-header:
    textColor: "{colors.foreground}"
    typography: sidebar-section-header
    padding: "Floating tray hover - absolute inset micro-padding + `rounded-[6px]` wash"
  app-pill:
    backgroundColor: "Semantic washes (`bg-info/15`, `bg-success/15`, etc.) - see prose"
    textColor: "Matched semantic text (`info-text`, `success-text`, ...)"
    rounded: "{rounded.full} pill - `{rounded.sm}` tag shape"
    padding: "4px pill micro-padding - tag `px-1.5 h-5`"
---

## Overview

Pawrrtal is a chat-first AI workspace with a **Craft Agents-inspired** visual
language: warm, flat, and editorial. Surfaces are matte (**no decorative gradients on
buttons/cards**); hierarchy comes from typography, neutral interpolation, and a single
brand accent. **Overlay / frosted stacks** (blur + tint-see **Overlay & frosted surfaces**)
are the exception to flat matte chrome.

The system is dual-theme. Light mode is a warm off-white palette with a
soft purple accent; dark mode is **near-black** (`#141414` canvas, `#9E94D5`
purple accent) — calm, minimal, and developer-native in both modes.

The token names in the front matter document the **light theme** (the `:root`
default in `frontend/app/globals.css`). Dark theme is documented inline in
each section.

## Colors

The palette is six semantic roles plus neutral interpolation. Canonical values
in code are `oklch()` triples; the front matter records the sRGB hex
approximations the linter expects.

- **Background** - page surface. Warm off-white in light, near-black in dark.
- **Foreground** - text and icons. Deep ink in light, soft white in dark.
- **Accent** - interaction and brand. Subdued purple in light, GitHub-blue in dark.
- **Info** - amber. "Ask" mode, warnings, neutral notifications.
- **Success** - green. Connected states, checkmarks, positive confirmations.
- **Destructive** - red. Errors, failed states, dangerous actions.

### Per-User Overrides

Every one of the six color slots, plus the three font slots
(`display`, `sans`, `mono`) and the global behavioral options
(theme mode, contrast, UI font size, pointer cursors, translucent
sidebar) is **fully customizable per user** through the Settings →
Appearance panel. The `AppearanceProvider` mounted in
`app/providers.tsx` reads the persisted overrides via TanStack Query
from `GET /api/v1/appearance`, merges them on top of the
Mistral-inspired defaults in
`frontend/features/appearance/defaults.ts`, and writes the resolved
values onto `<html>` as CSS custom properties. Every surface that
references `--background` / `--foreground` / `--accent` / etc.
inherits the user's overrides automatically - sidebar, chat, modals,
popovers, the lot.

The defaults documented in this file are the values the user gets
when they have never customized anything (or pressed "Reset to
defaults" in the panel). When you change a default here, change it in `frontend/app/globals.css` in the
same commit, and keep `frontend/app/layout.tsx` (Google Sans `<link>`, any
`next/font` loaders for other families) and
`frontend/features/settings/sections/appearance-helpers.ts` (`DEFAULT_FONTS`)
aligned with this spec so the cascade, settings mock defaults, and this file
all agree.

### Neutral Interpolation (Mix Variants)

The system avoids defining gray steps. Instead, `--foreground-N` solid mixes
toward the background give us a continuous tonal scale that auto-inverts
between light and dark themes. Tailwind exposes these as
`bg-foreground-5`, `bg-foreground-10`, ... `bg-foreground-95`.

Common roles:

- `foreground-5` - hover states, sidebar accent surfaces, subtle borders.
- `foreground-10` - input affordances, dividers.
- `foreground-50` - muted body text, secondary copy.
- `foreground-80` - dimmed-but-still-readable text.

Alpha variants (`bg-foreground/10`, `text-accent/60`, etc.) are also valid;
prefer the solid `-N` mixes for surface fills and the `/N` alpha for borders
or overlays where the layer underneath should bleed through.

### Light Mode Anchors

| Role        | Hex (approx) | Canonical                    |
| ----------- | ------------ | ---------------------------- |
| background  | `#F7F7F4`    | `oklch(0.973 0.014 90)`     |
| foreground  | `#1F1F1F`    | `oklch(0.21 0.005 285)`     |
| accent      | `#9E94D5`    | `oklch(0.704 0.102 285)`    |
| info        | `#87C3FF`    | `oklch(0.783 0.119 255)`    |
| success     | `#1F8A65`    | `oklch(0.50 0.12 165)`      |
| destructive | `#CF2D56`    | `oklch(0.55 0.20 355)`      |

The **background** is warm off-white (~#f7f7f4) - high luminance, neutral warm
tone. **Accent** is soft purple (~#9e94d5), a pleasant mid-tone brand color.
**Info** is soft blue (~#87c3ff) for "Ask" mode and warnings, **success** is
forest green (~#1f8a65), and **destructive** is rose red (~#cf2d56).
**Foreground** stays near-black ink (~#1f1f1f) so the light surface reads as a
clean, calm canvas.

### Dark Mode Anchors

Dark mode is near-black canvas with soft purple accent. These hex values are
the **explicit anchors** referenced in `globals.css`:

| Role               | Hex       | Note                          |
| ------------------ | --------- | ----------------------------- |
| background         | `#141414` | Page / workspace canvas       |
| background-elevated| `#191919` | Sidebar, elevated surfaces    |
| foreground         | `#FFFFFF` | Primary text                  |
| accent             | `#9E94D5` | Soft purple                   |
| border             | `#303030` | Hairline dividers             |
| muted-foreground   | `#AAAAAA` | Secondary / metadata copy     |

## Typography

### Canonical UI sans stack (default)

All body UI type (`--font-sans`, `--font-default`, Tailwind `font-sans`, and
`body` in `globals.css`) resolves to this **exact** CSS stack:

`Google Sans Flex, Google Sans, Helvetica Neue, sans-serif`

- **Implementation:** `frontend/app/globals.css` defines the Google Sans Flex /
  Google Sans `@font-face` rules and builds `--font-sans-stack` from the matching
  family names.
- **Front matter below:** tokens labeled `fontFamily: Google Sans Flex` mean "the
  primary face in that stack"; runtime always includes **Google Sans** and
  **Helvetica Neue** before the generic `sans-serif` fallback.

Optional **Inter** remains available via `html[data-font="inter"]` in the same
file (prepend `"Inter"` to the stack); that path is separate from the default.

Three families anchor the system:

- **Newsreader** (`--font-display`) - editorial near-serif, Mistral-inspired,
  used for `display` and `h1` only. Loaded via `next/font/google` in
  `frontend/app/layout.tsx` and exposed as `--font-display-loaded`. The
  display token chain (`--font-display-stack`) falls back to Iowan Old
  Style → Charter → Georgia → Times so the editorial character still reads
  before the web font arrives.
- **Google Sans Flex / Google Sans** (`--font-sans`) - default UI sans for
  everything from `h2` down through body, captions, and sidebar rows. Loaded
  via `@font-face` rules in `frontend/app/globals.css` (same families as the
  old `next/font/google` path; see `globals.css` `--font-sans-stack`), with
  stack fallbacks **Helvetica Neue** →
  generic `sans-serif`. **Inter** remains an opt-in upgrade via
  `<html data-font="inter">`; with Inter active, OpenType features `cv01`-`cv04`
  and `case` switch on for slightly more geometric letterforms.
- **JetBrains Mono** (`--font-mono`) - code, terminals, and the system's
  aliased serif slot. This is a chat surface, not long-form reading; mono
  doubles as serif on purpose.

The contrast - editorial display + geometric sans + monospace - IS the
brand voice. Hero headings carry near-classical character; everything below
the page-title level uses Google Sans Flex for density and legibility.

The root font size is **16px** - `<html>` reads `--font-size-base`, so every
`rem`-denominated value scales off 16. Tailwind v4 utilities (`text-xs`,
`text-sm`, `text-base`, ...) map to the standard rem values and resolve to
clean pixel sizes (12, 14, 16, 18, 20, 24, 30, 36, 48, ...).

### Scale

| Token     | Size      | px @ 16 base | Family      | Common use                        |
| --------- | --------- | ------------ | ----------- | --------------------------------- |
| display   | 3rem      | 48px         | Newsreader  | Hero headings, marketing splash   |
| h1        | 2.25rem   | 36px         | Newsreader  | Page titles                       |
| h2        | 1.875rem  | 30px         | Google Sans Flex | Section heads                     |
| h3        | 1.5rem    | 24px         | Google Sans Flex | Subsection / onboarding step      |
| h4        | 1.25rem   | 20px         | Google Sans Flex | Card titles                       |
| body-lg   | 1.125rem  | 18px         | Google Sans Flex | Lead paragraph, prominent body    |
| body-md   | 1rem      | 16px         | Google Sans Flex | Default body, chat messages       |
| body-sm   | 0.875rem  | 14px         | Google Sans Flex | Secondary body, metadata          |
| caption   | 0.875rem  | 14px         | Google Sans Flex | Labels, dense UI, group metadata  |
| code      | 0.875rem  | 14px         | JetBrains Mono | Inline code, pre blocks       |

Display sizes use **tighter line-height** (1.05 / 1.10) and **stronger
negative letter-spacing** (-0.025em / -0.02em) to give hero type magazine-
grade tightness. Sub-display headings (`h2`-`h3`) keep negative tracking
(-0.015em / -0.01em) but ease leading to 1.20-1.25. Body uses default
tracking. Caption uses slightly **positive tracking** (`+0.01em`) for
legibility at small sizes.

### Sidebar Type Baseline

The sidebar has its own subset of the type scale because rows there are
denser than chat content but **must not** drop below 14px (`text-sm`). The
floor is 14px because rows compete with the UI sans lower-bound legibility
under the warm low-contrast palette and routinely include status glyphs
that would shrink with the row.

| Surface                       | Token                   | Tailwind   | px |
| ----------------------------- | ----------------------- | ---------- | -- |
| Section header (Projects, Chats) | sidebar-section-header  | `text-sm font-semibold` | 14 |
| Conversation row              | sidebar-row             | `text-sm`  | 14 |
| Date-group header (Today, May 3) + count | sidebar-group-meta | `text-sm font-medium` | 14 |
| Status glyph + unread bubble  | -                       | `h-3.5 w-3.5` | (14px square) |

**Do not** drop sidebar text to `text-[11px]` or `text-xs` (12px); the
old 11px on date group headers shipped briefly and looked broken next to
the row text. If a row needs visual de-emphasis, use `text-muted-foreground`
or the `--foreground-N` mix scale, **not** a smaller font size.

## Interactive Affordances

Every element that responds to a click, drag, or hover **must** declare its
intent visually. The Tailwind v4 base layer in `globals.css` does not set
`cursor: pointer` on `<button>` or `[role="button"]` automatically, so each
interactive surface opts in.

### Cursor Rules

| Element kind                          | Required cursor       |
| ------------------------------------- | --------------------- |
| `<button>`, `[role="button"]`         | `cursor-pointer`      |
| `<a href>`                            | `cursor-pointer`      |
| Drop target while a valid drag hovers | `cursor-copy`         |
| Disabled button (`disabled`)          | `cursor-not-allowed`  |
| Resizable handle (sidebar splitter)   | `cursor-col-resize`   |
| Drag handle on a row                  | `cursor-grab` → `cursor-grabbing` while held |
| Non-interactive heading / label       | (default)             |

The verify question for every PR: *"Does every clickable element in this
diff have `cursor-pointer` (or one of the variants above) on it?"* The
project linter does not enforce this - humans and review agents do.

### Hit Targets

Drop zones (project rows, archive bin, etc.) need a **minimum 40px tall
target** with the **whole row reactive**, not just the visible icon or
text inside it. Use `py-2` / `py-3` to pad the row, attach the
`onDragOver`/`onDrop` handlers to the outer row element, and call
`event.preventDefault()` on every nested `onDragOver` so the drop is
delivered to the row.

## Layout

Spacing follows Tailwind v4's `--spacing: 0.25rem` (= 4px) base. Prefer the
named scale below over arbitrary px values; they map 1:1 to Tailwind utilities
(`p-1`, `p-2`, `p-4`, `p-6`, `p-8`, `p-12`).

| Token  | Value | Tailwind | Use                                          |
| ------ | ----- | -------- | -------------------------------------------- |
| xs     | 4px   | `*-1`    | Hairline gaps, icon-text padding             |
| sm     | 8px   | `*-2`    | Tight inline spacing, icon button padding    |
| md     | 16px  | `*-4`    | Default block spacing, card padding          |
| lg     | 24px  | `*-6`    | Section spacing, modal padding               |
| xl     | 32px  | `*-8`    | Top-of-page rhythm, large card gaps          |
| 2xl    | 48px  | `*-12`   | Hero spacing, full-page sectioning           |

### Z-index Scale

A semantic z-index ladder is exposed as CSS variables (`--z-base` through
`--z-splash`). Always reference these tokens; never hard-code z-index values.

| Token             | Value | Use                              |
| ----------------- | ----- | -------------------------------- |
| base              | 0     | Default flow                     |
| local             | 10    | In-component layering            |
| sticky            | 20    | Sticky headers                   |
| titlebar          | 40    | App title bar                    |
| panel             | 50    | Side panels                      |
| dropdown          | 100   | Menus, comboboxes                |
| tooltip           | 150   | Tooltips                         |
| modal             | 200   | Modal dialogs                    |
| overlay           | 300   | Full-page overlays               |
| floating-menu     | 400   | Floating action menus            |
| splash            | 600   | Splash / loading takeover        |

## Elevation & Depth

Shadows are **token-based**, not free-form. The opacity of every shadow scales
with two CSS variables (`--shadow-border-opacity`, `--shadow-blur-opacity`)
that are tuned per theme: subtle in light, stronger in dark.

| Token                  | Use                                                       |
| ---------------------- | --------------------------------------------------------- |
| `shadow-thin`          | Hairline border, no blur. Buttons, input groups.          |
| `shadow-minimal`       | 1px border + light blur. Cards, popovers.                 |
| `shadow-middle`        | Stacked blurs. Modals, important panels.                  |
| `shadow-strong`        | Deep stacked blurs. Dialogs over scrim.                   |
| `shadow-modal-small`   | Modal-style shadow with multiple radii.                   |
| `shadow-panel-floating`| Panels stacked over other panels (chat over sidebar).     |
| `shadow-panel-focused` | Adds a 1px gradient inner border for the focused panel.   |
| `shadow-tinted`        | Tinted variant; pass `--shadow-color` as `r, g, b`.       |
| `shadow-edge`          | 1px white inset + 1px black 4% outer. Use INSTEAD of gray borders. |

In **scenic mode** (`html[data-scenic]`), `shadow-middle` and `shadow-strong`
gain a `backdrop-filter: blur(8px)` and a 1px gradient inner border, turning
solid panels into glass.

### Edges: stop using gray 1px borders

Stack a **1px white inset shadow + 1px black 4% outer shadow** instead of
a flat `border: 1px solid var(--color-border)`. The inset highlight reads
as a top-edge sheen and the outer drop reads as a soft contact shadow -
together they make the element feel sharper and more dimensional, the
same way macOS, Linear, and modern iOS surfaces do, without the muddy
look of a single hairline.

In code:

```css
/* DON'T: */
border: 1px solid var(--color-border);

/* DO (use the utility): */
@apply shadow-edge;

/* Or inline the values when the utility class won't fit: */
box-shadow:
    inset 0 1px 0 0 rgb(255 255 255 / 0.6),
    0 1px 0 0 rgb(0 0 0 / 0.04);
```

The dark-mode variant of the utility (`.dark .shadow-edge`) inverts the
highlight to a low-opacity foreground tint and bumps the outer drop to
40 % so the same affordance reads on dark surfaces.

Reach for `shadow-edge` first when:

- a card, input, toggle, or chip needs a visible perimeter
- the existing `shadow-thin` is *too flat* and reads as a single line
- the `shadow-minimal` is *too elevated* and reads as a popover

Stick with `shadow-thin` (single 1px ring, no drop) when the surface is
explicitly nested inside another bordered surface - `shadow-edge`'s outer
drop competes with the parent's edge in that case.

## Shapes

The system is **flat by default**: `--radius` is `0` and Tailwind's
`rounded-{sm,md,lg,xl}` utilities all resolve to 0. Use the `rounded` scale
above (`sm: 4px`, `md: 8px`, `lg: 14px`) **explicitly** when a component needs
softening - popovers, chat composer surfaces, dropdown menus.

### The Bubble Exception

Chat message bubbles use an **asymmetric "tail" radius** so the bubble
visually attaches to its author edge:

- `--radius-bubble: 1.25rem` (20px) - three rounded corners.
- `--radius-bubble-tail: 0.125rem` (2px) - the corner adjacent to the author.

User messages tail toward the right; assistant messages tail toward the left.
This is the only place in the system that breaks the flat default.

## Overlay & frosted surfaces

**Direction:** Use **background blur** (`backdrop-filter` / stack blur) **plus**
a **subtle tint**-for example a **linear gradient** with roughly **10-15% black**
(or theme-equivalent stops)-**instead of** a **simple flat opacity overlay** (such
as a single dark layer at **~40% opacity** over the viewport).

Blur puts the scene behind the glass; the gradient adds controlled depth without
turning the stack into a flat muddy wash. That reads **refined and glass-like**;
uniform opacity alone reads **flat** and dull.

**In practice:** Prefer the same pattern already described for **`popover`**
(menu panels): blur strength + percentage tint on the panel surface. Apply the
same discipline to **modal scrims**, **sheet backdrops**, and any full-bleed
dimming-reach for **blur + gradient tint**, not **`bg-black/40`**-style solids
unless a deliberate exception is documented.

**Implementation (this repo):** Radix **Dialog**, **Alert dialog**, and **Sheet** overlays use the `.modal-scrim` utility in `frontend/app/globals.css`: **8px** backdrop blur (aligned with `.popover-styled`) plus a **vertical gradient** from ~**10%** to ~**14%** black (`rgba(0, 0, 0, 0.1)` → `rgba(0, 0, 0, 0.14)`), replacing the prior flat **`bg-black/80`** wash.

## Motion

The system prefers **transform-based animation** over property animation
that triggers layout. Three patterns are load-bearing enough to call out.

### Open / close timing

Overlays (dropdowns, popovers, tooltips, context menus) follow Linear-snappy
timing - fast enough to feel responsive, slow enough to read.

| Direction | Duration | Easing                                          |
| --------- | -------- | ----------------------------------------------- |
| Open      | 140 ms   | `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-expo) |
| Close     | 100 ms   | `cubic-bezier(0.7, 0, 0.84, 0)` (ease-in-quint) |

Close is always faster than open. Open is "reveal slowly enough to read";
close is "get out of my way."

Animate **opacity + scale + y + `filter: blur(8 px)`** on enter/exit. The blur
transition makes overlays feel like they're coming into focus rather than
abruptly appearing - element starts blurry and out-of-place, focuses into
clarity. 8 px is the sweet spot: enough to read as motion without making the
contents unreadable mid-transition. Reduced-motion (see below) collapses to
opacity-only.

Larger surfaces use proportionally longer durations:

| Surface                       | Open   | Close  |
| ----------------------------- | ------ | ------ |
| Tooltips, popovers, dropdowns | 140 ms | 100 ms |
| Submenu chains                | 80 ms  | 60 ms  |
| Sheets, drawers               | 220 ms | 180 ms |
| Modals                        | 260 ms | 200 ms |
| Full-screen overlays          | 320 ms | 240 ms |

Submenus run faster than root overlays so cursor traversal between
sibling submenu triggers (e.g. Anthropic → OpenAI → Google in the
model picker) doesn't visibly overlap two panels - the previous
panel finishes exiting before the next one finishes entering.
Easing inherits from the root so the family stays cohesive.

Implementation: `@octavian-tocan/react-dropdown`'s `DropdownRoot` defaults
match the overlay row above. Other Motion call sites (access-request banner,
shimmer, etc.) tune to their own surface needs but follow the open-slower /
close-faster discipline.

### Sidebar Open / Close

The sidebar opens and closes by **translating the panel along the X axis
at its full open width** - not by interpolating its width from `0` to
`288px`. Animating width forces the content area's text and controls to
reflow on every frame, which manifests as right-side controls "creeping"
toward the conversation titles during the animation.

Implementation contract:

- The sidebar lives inside a fixed-width outer wrapper that always occupies
  its open width in the layout.
- The inner panel has `translate-x-0` when open and `-translate-x-full`
  when closed, with `transition-transform duration-200 ease-out`.
- The main content area listens to the same open/closed state and shifts
  via `margin-left` (or grid-template-columns), in sync with the panel
  transform - never via `width`.
- The resize handle is disabled / hidden while the panel is closed; the
  user can't grab a panel they can't see.

### Tooltip Reveal Delay

Every tooltip across the app uses the **same** hover delay before it
becomes visible: **500 ms**. The single source of truth is
`TOOLTIP_DEFAULT_DELAY_MS` exported from
`frontend/components/ui/tooltip.tsx`; it is applied as the
`<TooltipProvider delayDuration>` default, so per-call sites do **not**
re-pass a number.

500 ms reads as "I noticed you paused on this control" without firing
on cursor fly-throughs - a user can scan an entire toolbar at speed
without any tip popping; lingering on a single icon resolves the tip.
Override per-call only when a surface explicitly needs a different
cadence (none currently do).

The earlier value was 300 ms, applied inconsistently - some call sites
re-passed `delayDuration={300}` (matching the default) while others
relied on the provider default, which made future timing tweaks fragile.

### Reduced Motion

Honor `prefers-reduced-motion: reduce` on every animation longer than
~150ms. The sidebar slide, modal entry, and personalization step
transitions all gate their `transition-*` classes behind a reduced-motion
check (`motion-safe:transition-transform`).

## Components

Component tokens record the **typed surfaces** in the chat workspace. Use the
front matter as the source of truth for backgrounds, text colors, and radii;
fall back to the prose below for behavioral notes.

### Menu primitives (`@octavian-tocan/react-dropdown`)

Panel-style dropdowns (sidebar profile menu, composer attachment menus, etc.)
use **`DropdownMenuItem`** from **`@octavian-tocan/react-dropdown`**. The
implementation is vendored at **`frontend/lib/react-dropdown`** (`package.json`
`workspace:*` + **`frontend/tsconfig.json`** path alias → `./lib/react-dropdown/src/index.ts`).

**Tailwind v4 scanning:** Default row chrome lives in
**`frontend/lib/react-dropdown/src/DropdownPanelItems.tsx`**
(`DEFAULT_ITEM_CLASSNAME`). Tailwind only emits utilities for class names it
**scans**. Those files sit outside `app/` / `features/`, so
**`frontend/app/globals.css`** registers the package explicitly:

```css
@source "../lib/react-dropdown/src";
```

(Path is relative to `app/globals.css`.) If you add utilities only inside
`lib/react-dropdown/` and styles "do nothing" at runtime, verify the compiled
CSS contains those classes-missing **`@source`** is the usual cause.

**Disabled rows:** Pass **`disabled`** on **`DropdownMenuItem`**. Visuals rely on
native **`:disabled`** Tailwind variants (`disabled:*`) on the underlying
`<button>`. Disabled rows keep a **steady `bg-muted/50` tray** (same fill on
`:hover` / `:focus` / `:active` so they never flash the enabled
**`hover:bg-foreground/[0.03]`** wash), **`text-muted-foreground`**, and softer
default Lucide icons
(`disabled:[&>svg:not([class*='text-'])]:text-muted-foreground/55`). Enabled
rows stay flat until hover-so unavailable actions read unambiguously.

**Disabled submenu triggers:** **`DropdownSubmenuTrigger`** accepts **`disabled`**.
Implementation merges the shared **`MENU_ROW_DISABLED_VISUAL_CLASSNAME`** module
(`frontend/lib/react-dropdown/src/menu-row-disabled-visual.ts`) with item rows,
skips hover-scheduled open and keyboard open, and sets **`disabled`** on the
underlying `<button>`. Sub-items inside the flyout still use **`DropdownMenuItem
disabled`** as usual (they remain unreachable when the trigger is disabled).

The write-up in **`docs/solutions/ui-bugs/dropdown-disabled-menu-items-not-visually-distinct.md`**
captures the full diagnosis (scan gap + contrast strategy) for future debugging.

### Modal / sheet overlays (`@octavian-tocan/react-overlay`)

Centered **`Modal`** and draggable **`BottomSheet`** patterns live in this package.
The implementation is vendored at **`frontend/lib/react-overlay`** (git submodule),
wired like **`react-dropdown`**: root **`package.json`** **`workspace:*`** +
**`frontend/tsconfig.json`** path alias → **`./lib/react-overlay/src/index.ts`**.

Feature code composes through **`frontend/components/ui/app-dialog.tsx`**
(`AppDialog`), which picks **`Modal`** on desktop and **`BottomSheet`** on narrow
viewports. **`AppDialog`** is a thin shell over **`ResponsiveModal`**
(`responsive-modal.tsx`) with the Pawrrtal contract documented in this section.

**How modals become bottom sheets:** On viewports narrower than **768px** (same
threshold as **`useIsMobile`**), the same
component renders as a draggable sheet from the bottom instead of a centered
dialog. That only delivers the intended UX when you split **chrome** from **body**:
pass **`header`** (e.g. **`ModalHeader`** + **`ModalDescription`** from the
overlay package), **`footer`** (primary/secondary actions), and keep forms and copy
in **`children`**. Then the sheet gets sticky header/footer regions and a
scrollable middle - matching "proper" bottom-sheet behavior. Putting titles and
buttons only inside **`children`** works but stacks everything in one scroll
region; prefer explicit **`header`** / **`footer`** for flows that must feel native
on phones. Optionally set **`sheetTitle`** for short aria text on the sheet
handle/backdrop when it helps screen readers.

**Variants:** Each product surface (create project, rename conversation, delete
confirm, integrations, etc.) should be a small component that wraps **`AppDialog`**
and supplies domain-specific markup - not a one-off overlay implementation.

**Dialog bodies vs full-page forms:** Top-level auth/settings surfaces may keep
**`Field`** / **`FieldLabel`** from **`field.tsx`**. Flows inside **`AppDialog`**
should compose **`AppFormRow`** (label + optional description + error slot),
trust/warning strips via **`AppDialogCallout`** (`tone="info" | "warning"`), and
stack actions with **`AppDialogFooter`** (default `flex-col-reverse` + `sm:flex-row
sm:justify-end`, optional `align="between"`).

### Empty states (`frontend/components/ui/app-empty-state.tsx`)

**`AppEmptyState`** centralizes empty placeholders so sidebar, editorial pages,
cards, and settings panels stop drifting on radius and type scale.

- **`tone="sidebar"`** - Compact sidebar stack (`text-sm`), icon in a **`rounded-md`**
  token container sized for the sidebar rhythm.
- **`tone="page"`** - Editorial headline (`font-display`) + muted description for
  full-column tasks/workspace empties.
- **`tone="card"`** - Bordered inset card for Knowledge-style archives.
- **`tone="panel"`** - Dashed inset panel for Settings archived lists.
- **`layout="inlineCta"`** - Single clickable row; **`title`** doubles as the button
  label (`action` supplies **`onClick`** only).

Feature wrappers (**`ConversationsEmptyState`**, **`TasksEmptyState`**, Knowledge
**`EmptyState`**, etc.) should stay thin and delegate chrome here.

### Dialog scaffolding (`app-form-row`, `app-dialog-callout`, `app-dialog-footer`)

- **`AppFormRow`** - Label (`text-sm font-medium text-foreground`), optional helper,
  **`htmlFor`** wiring, error text slot, consistent vertical gap for modal forms.
- **`AppDialogCallout`** - Info/warning strips with shared radius/density (replaces
  one-off `rounded-[10px]` / `rounded-[8px]` washes).
- **`AppDialogFooter`** - Matches destructive-dialog stacking on phones; widens to
  end-aligned rows from **`sm:`** upward.

### Sidebar navigation chrome (`frontend/components/ui/sidebar-nav-row.tsx`)

**`SidebarNavRow`** owns hover/selected fills for sidebar lists:

- **Hover:** `hover:bg-foreground/[0.04]`
- **Selected:** `bg-foreground/[0.07]`
- **`density="comfortable"`** - `min-h-9` rows (conversations, projects).
- **`density="compact"`** - `h-8` metadata-heavy rows (tasks sidebar).

**`entity-row.tsx`** keeps selection + context-menu behavior and delegates surface
classes via **`sidebarNavRowSurfaceClassName`**. **`ProjectRow`** composes the same
primitive and layers drag/drop ring locally. **`TasksSubSidebar`** `NavRow` uses
**`density="compact"`**.

### Sidebar section headers (`frontend/components/ui/sidebar-section-header.tsx`)

**`SidebarSectionHeader`** covers:

- **`variant="collapsible"`** - Chevron + label + optional collapsed count meta +
  **`trailingSlot`** (e.g. quick-add). Provide **`toggleButtonProps`** for
  **`aria-expanded`** / **`aria-controls`** / **`aria-label`** on the hit target.
- **`variant="static"`** - Uppercase micro-label for task group labels.

The floating hover tray (`absolute` inset + **`rounded-[6px]`** group-hover wash) is
owned here so **`CollapsibleGroupHeader`**, Projects list headers, and Tasks groups
stay visually aligned.

### Status pills (`frontend/components/ui/app-pill.tsx`)

**`AppPill`** replaces literal emerald/amber utility stacks with semantic washes
(**`bg-info/15`**, **`bg-success/15`**, **`bg-destructive/15`**, etc.) and matched
text tokens.

- **`shape="pill"`** - Uppercase micro-label (integration provider badges).
- **`shape="tag"`** - Sentence-case metadata (**`TagChip`** task tags); neutral tag
  uses a subtle `bg-foreground/[0.04]` tray.

**`KnowledgePageHeader`** count segments compose **`AppPill`** with local casing
overrides where needed.

**Tailwind v4 scanning:** register the package in **`frontend/app/globals.css`**:

```css
@source "../lib/react-overlay/src";
```

(Path is relative to `app/globals.css`.) Without this, overlay-specific utilities
may not appear in the compiled CSS.

- **`dropdown-menu-item-disabled`** - Unavailable **`DropdownMenuItem`** rows
  (`disabled` prop). **Surface:** `bg-muted/50` row tray, **`text-muted-foreground`**
  labels, **4px** row radius (`rounded.sm`) inside the panel. **Do not** recreate
  one-off disabled styling at call sites unless the default is insufficient-fix
  **`DEFAULT_ITEM_CLASSNAME`** instead. See **Menu primitives
  (`@octavian-tocan/react-dropdown`)** above for **`@source`** and file paths.

- **`popover`** - Used by all menu containers via the `popover-styled`
  utility class. 8px radius (`rounded.md`), `shadow-modal-small`, no border.
  Default mode: **8 px backdrop blur** and a **95% background tint** so the
  panel surface reads as solid (the lower 88% used previously caused
  busy sidebar / chat content to bleed through and hurt readability).
  Scenic mode keeps the more-transparent **88% tint + 24 px blur** so the
  user's chosen background image is still visible behind the menu.
  Aligns with **Overlay & frosted surfaces**-avoid swapping this for a **flat
  opacity-only** dim.
- **`chat-composer`** - The message input surface. Soft (`shadow-minimal`),
  no border on focus (the shadow alone defines the edge). Dropdowns opened
  from the composer (e.g. model picker) inherit `chat-composer-dropdown-menu`
  styling - 14px radius (`rounded.lg`), `--foreground-5` background.
- **`bubble-user`** - User message bubbles use `--user-message-bubble` (a
  tinted-foreground alpha) with the asymmetric tail described in **Shapes**.
- **`bubble-assistant`** - Assistant messages have **no bubble** by default.
  They sit on the page background with the foreground color, with prose
  styling for long-form output.
- **`step-icon`** - Onboarding step iconography. 64px square, 16px radius,
  inverse fill (foreground on background-inverse). Inner glyph is 32px.
- **`select-button`** - Project-internal compact picker (see
  `frontend/components/ui/select-button.tsx`). Trigger is a `Button`
  with `bg-foreground/[0.04]` ghost styling, `rounded-[7px]`,
  `h-8`, chevron right. Popover reuses `chat-composer-dropdown-menu`
  so the model picker, theme preset picker, and any future picker
  share visual chrome. **Use this instead of native `<select>`** for
  every dropdown across the app.
- **`settings-section-header`** - Standard top-of-card header used by
  every Settings section (see
  `frontend/features/settings/primitives.tsx`). Title is
  `text-base font-semibold tracking-tight text-foreground`, description
  is `text-sm text-muted-foreground leading-snug text-pretty`, optional
  right-aligned actions slot. Bottom hairline (`border-border/40`),
  `pb-3`. **Every Settings section MUST use this** - bespoke headers
  are a consistency bug. Apply inside a `SettingsCard`; the card
  handles the rounded surface and the header handles the layout.
- **`settings-page-shell`** - Page-level wrapper rendered by
  `SettingsPage` in `frontend/features/settings/primitives.tsx`. Title
  is `text-3xl font-semibold tracking-tight text-foreground` (balanced
  wrap), optional description is `text-sm leading-relaxed
  text-muted-foreground` capped at `60ch`. Children stack with
  `gap-6`. **Every Settings section MUST wrap itself in this** -
  per-section `<header><h1>` blocks are a consistency bug.
- **`settings-card`** - Rounded surface used to group related rows in
  a Settings section. Uses theme-aware tokens (`bg-card`,
  `border-border/60`) so the card tints itself correctly under either
  light or dark mode. `rounded-[14px]`, `px-6 pt-3 pb-3`. Header
  rendered via `settings-section-header`; body is a vertical stack of
  `SettingsRow`s separated by `border-border/40` hairlines.
- **`color-pill`** - Codex-style filled color picker used by the
  Appearance section (see
  `frontend/features/settings/primitives.tsx`). The entire pill
  background renders as the resolved color; the hex literal floats on
  top in `font-mono tabular-nums` with `mix-blend-mode: difference`
  for auto-contrast against any color (no manual fg/bg picking).
  Clicking anywhere on the pill opens the OS color picker via an
  invisible `<input type="color">` overlay. **The native picker is
  uncontrolled** (`defaultValue` + ref-driven re-seed) so mid-drag
  re-renders triggered by upstream state updates don't snap the OS
  picker back to a stale value (the lurping bug). Picker commits are
  RAF-batched upstream so a 60fps drag yields ≤60 PUTs/s.
- **`button-primary`** / **`button-secondary`** - Buttons follow the flat
  default (`rounded.none`). Primary fills with accent; secondary inherits
  the page background and relies on `shadow-thin` for definition.
  **Note on contrast:** white-on-soft-purple (~#9E94D5) has ~4.5:1 contrast ratio, which clears
  WCAG AA *Large Text* (3:1) but not *Normal Text* (4.5:1). Primary CTAs
  always render with `font-medium` body-md (16px+) so they qualify as
  large text; the lint warning here is acknowledged, not a bug. Use a
  darker `--accent` if you ever drop the weight or size.
- **`personalization-modal`** - The home-page personalization surface
  (fires on every load while the feature is WIP). Sits over the same
  scenic dotted backdrop used by the workspace onboarding, with a
  panel-backed card holding the form fields. Field styling matches
  `Field` / `FieldLabel` / `Input` from the form primitives. Typography
  follows the standard `h3` heading + `body-md` body + `caption` helper
  pattern - it does **not** introduce new font sizes. Dismiss closes
  for the session only; no localStorage flag while WIP.
- **`deferred-fetch-on-surface-open`** — Any panel, step, or popover that
  must hit the network the moment it becomes visible should show an
  explicit **loading state** (spinner, skeleton, or muted pulse) until
  the first response resolves — never render a false empty/disconnected
  state while the request is in flight. After data arrives, swap to the
  resolved UI in one transition. Onboarding "Connect Telegram" uses a
  row-level spinner; reuse the same pattern for future channel pickers
  or permission probes.
- **`project-row` (drop target)** - Projects feature wrapper around
  **`SidebarNavRow`** chrome plus **drag-and-drop** affordances. Row hover/selected
  fills come from **`sidebar-nav-row`** tokens (`hover:bg-foreground/[0.04]`,
  selected `bg-foreground/[0.07]`). Project-specific behavior: full-row drop
  target (the whole `<button>` listens for `dragover`/`drop`), `cursor-copy` while
  a valid conversation drag hovers, drag-over ring + tint layered locally. Names are
  set via the project create modal; never auto-named "New Project".

## Do's and Don'ts

### Do

- **Use semantic tokens.** Reach for `text-foreground`, `bg-background`,
  `text-accent`, `bg-foreground-5` before any literal color.
- **Use the `--foreground-N` scale** for tonal grays. It auto-inverts and
  preserves the warm/cool tint of the theme.
- **Keep surfaces flat by default.** If you find yourself adding a radius,
  ask whether it's a popover, composer, or chat bubble - those are the only
  shapes with curvature in this system.
- **Reach for `shadow-minimal` first.** Most surfaces need only a hairline.
  Save `shadow-middle` and `shadow-strong` for true elevation (modals,
  floating panels).
- **Reference z-index tokens** (`z-modal`, `z-tooltip`) - never hard-code.
- **Trust the 16px root.** All Tailwind sizing utilities resolve to clean
  pixels; you should rarely need a literal `px` value outside 1px borders
  and a handful of icon-sized affordances.
- **Prefer frosted overlays over flat opacity washes.** For scrims and stacked
  glass surfaces, use **backdrop blur + subtle gradient tint** (~10-15% black
  equivalent)-not a single **~40% opacity** dark layer. See **Overlay & frosted surfaces**.
- **Register linked UI packages with Tailwind.** Packages resolved under
  `frontend/lib/` (for example `@octavian-tocan/react-dropdown` →
  `frontend/lib/react-dropdown`, `@octavian-tocan/react-overlay` →
  `frontend/lib/react-overlay`) often define Tailwind class strings. Add an
  `@source` path in `frontend/app/globals.css` for each such package so those
  utilities are emitted-see **Menu primitives (`@octavian-tocan/react-dropdown`)**
  under **Components**.

- **Bump up, never down, the sidebar text scale.** The 14px floor is
  load-bearing for the sidebar's legibility under the warm low-contrast
  palette; smaller is unreadable for date-group headers and counts.
- **Translate, don't resize.** When opening or closing a panel, animate
  `transform: translateX()` on a fixed-width inner wrapper and shift the
  content area with `margin-left` (or grid columns) on the same easing.
  Animating `width` causes the right-side content to creep toward the
  panel during the transition.
- **Make every interactive surface declare itself.** `cursor-pointer` on
  buttons + links, `cursor-copy` on drop targets while a valid drag is
  over them, `cursor-not-allowed` on disabled controls. The base layer
  doesn't set these for you.

### Don't

- **Don't put decorative gradients on matte UI chrome** (buttons, cards, flat
  panels). The editorial surface is load-bearing. **Exception:** **overlay /
  scrim / frosted panels** may use a **controlled linear gradient** as part of
  **blur + tint** (see **Overlay & frosted surfaces**)-that is not "decorative chrome,"
  it is depth for glass stacks.
- **Don't use flat opacity-only viewport dims** (e.g. uniform **40% black**) as the
  default scrim pattern when blur + gradient tint can carry the effect-see **Overlay &
  frosted surfaces**.
- **Don't add new `--radius-*` tokens.** Use the existing scale or use 0.
- **Don't use `text-gray-*` or any literal Tailwind color utility.** They
  bypass the theme system and won't invert in dark mode.
- **Don't hard-code shadow stacks.** Reach for the named shadow utilities;
  if none fit, add a new named token rather than inlining `box-shadow`.
- **Don't replace the default UI sans stack** casually - it is fixed to **Google
  Sans Flex, Google Sans, Helvetica Neue, sans-serif** (see Typography). New
  alternate families still need an opt-in `data-*` toggle on `<html>`, mirroring
  how `data-font="inter"` is wired.
- **Don't use the bubble radius outside chat messages.** It's the system's
  one asymmetric shape and exists to anchor bubbles to their author.

---

## Validating This File

This file follows the [DESIGN.md spec](https://github.com/google-labs-code/design.md).

```bash
npx @google/design.md lint DESIGN.md
npx @google/design.md diff DESIGN.md DESIGN-v2.md
npx @google/design.md export --format css-tailwind DESIGN.md > theme.css
```

The canonical token values live in `frontend/app/globals.css`. When tokens
change there, mirror them here in the same PR. For the **UI sans stack**, also
update the matching `@font-face` rules in `frontend/app/globals.css` and
`frontend/features/settings/sections/appearance-helpers.ts` as needed.
