# UX.md — design guardrails for Surge

Read this before any visual, layout, styling, copy, or component work. It exists so
Surge never ships a page that reads as "AI-generated." If you are only touching
backend, tests, or non-visual code, you don't need this file.

The single source of visual truth is the **"Phosphor"** design system in
`frontend/app/globals.css` (the `:root` token block) plus the fonts wired in
`frontend/app/layout.tsx`. This file is the judgment layer on top of those tokens.
When this file and a stray hardcoded style disagree, the tokens win — fix the stray.

---

## 0. The prime directive: never look vibe-coded

A "vibe-coded" site is what you get when a model reaches for the nearest default.
It has a recognizable smell. Never produce any of these:

- **Purple / violet / indigo anything.** No purple hero, no `#6366F1`/indigo-600,
  no violet-to-blue or purple-to-pink gradient. Purple is THE tell. Surge's palette
  is cool graphite + citron + ice on purpose (`globals.css` even labels it "without
  the default AI-purple palette"). The ONLY sanctioned purple in the entire app is
  the Instagram brand wordmark gradient (purple→yellow), which is a deliberate
  platform-logo device — never a UI surface, button, or background.
- **Gradient soup.** No full-bleed multi-stop gradient backgrounds, no gradient
  fills on cards/buttons, no gradient body text as a default. Accent glow via a
  low-opacity radial (already in the token system) is fine; a purple-pink hero is not.
- **The generic AI hero.** Center-stacked headline + subhead + two pill buttons
  ("Get Started Free" / "View Pricing") floating on a gradient, with a row of three
  round stats (`25%` · `95%` · `2025`) underneath. This exact layout is in the
  attached counter-examples. If a layout is trending toward it, change it.
- **Cliché copy.** "Transform your X into Y — instantly," "The future of Z is here,"
  "Revolutionizing … powered by advanced LLMs." Write plain, specific, human copy.
- **Glassmorphism by default** — heavy translucent blur cards, uniform 24px radius on
  everything, one identical drop shadow everywhere, emoji used as product icons.
- **No type hierarchy** — one weight, one size, everything centered.

If you are unsure whether something looks vibe-coded, it probably does. Pull a real
reference (§3) and match it instead of inventing.

---

## 1. Color — tokens only

- Use CSS variables from `globals.css` (`--color-background`, `--color-surface`,
  `--color-card`, `--color-border`, `--color-text-primary`, `--color-text-muted`,
  `--color-accent` citron, `--color-accent-2` ice, `--color-success/-warning/-danger`).
  Derive shades with `color-mix(in srgb, var(--color-x) N%, …)`, never with a new hex.
- **Two accent temperatures, kept distinct:** citron `--color-accent` = *act*
  (primary CTAs, live signals). Ice `--color-accent-2` = *inform* (insights,
  secondary highlights). Don't swap their jobs; don't add a third accent.
- Never introduce a raw hex value in a component when a token exists. If a genuinely
  new color is unavoidable, add it as a token in `:root` first so it cascades and
  stays theme-consistent — don't scatter one-off hexes.
- Dark-only. Don't build a half-baked light mode; the app is a single dark theme.

## 2. Typography — it must be beautiful, and it's already chosen

- Two faces, both loaded via `next/font/google` in `layout.tsx`:
  **Schibsted Grotesk** = display (`--font-display`) for headings, brand, big moments.
  **Instrument Sans** = body (`--font-sans`) for everything else. Don't add a third
  font or fall back to system-ui as the primary face.
- Real hierarchy is mandatory. Headings: display face, heavy weight (700–800), tight
  tracking (`letter-spacing: -.03em` to `-.035em`), fluid sizing with `clamp()`
  (e.g. `clamp(40px,4vw,57px)`) so they scale without media queries. Body: 15–17px,
  `line-height: 1.6`, `--color-text-muted` for secondary text.
- Left-align long-form text. Reserve centering for short hero/section headings, not
  paragraphs. Set a max measure (~50–65ch) so lines don't run edge to edge.
- Never let a heading and its body text share the same weight and size.

## 3. Reference-driven design — follow what the user gives you

When the user provides a reference (screenshot, URL, "make it like X"), that reference
is the brief. Do this before writing CSS:

1. **Extract, don't vibe.** Name the specific things that make it work: layout grid,
   spacing rhythm, type scale and pairing, color restraint, the ONE accent, border/
   radius/shadow treatment, density, motion. Write those down, then build to them.
2. **Translate into Surge tokens.** Keep the reference's *structure and taste*, but
   render it in the Phosphor palette and fonts — don't paste in the reference's colors
   (especially not if they're purple).
3. **Match the level of polish, not just the layout.** Alignment, optical spacing,
   consistent radii, and intentional whitespace are what separate "designed" from
   "generated."
4. If no reference is given, default to restrained, editorial, high-contrast layouts
   (think Linear, Vercel, Stripe) — never the centered-gradient-hero default.

## 4. Layout, spacing, motion

- Consistent spacing scale and container widths (the app uses `width:min(1180px,
  calc(100% - 48px))` for main sections — reuse it, don't invent a new max-width).
- Alignment over centering. Use a real grid; align to edges and baselines.
- Restraint in radius and shadow: a small set of intentional values, not a different
  one per element.
- Motion is subtle and purposeful, and MUST respect `@media (prefers-reduced-motion:
  reduce)` (already honored in `globals.css`). No gratuitous parallax/auto-carousels.
- Hover affordances belong behind `@media (hover: hover) and (pointer: fine)` so touch
  devices don't get stuck hover states.

## 5. Responsive — desktop AND mobile, every time

Both are first-class. A change isn't done until it's correct at both.

- Primary breakpoint is `max-width: 720px` (some sections also adapt at `980px`) —
  follow the existing breakpoints in `globals.css`; don't invent parallel ones.
- On mobile: multi-column grids collapse to one column, hero/section type steps down,
  side-by-side actions stack full-width, nav collapses (secondary links hidden, CTA
  kept), oversized decorative art is hidden or shrunk. There are worked examples in
  the `@media (max-width:720px)` block — mirror that pattern for anything new.
- Use fluid type (`clamp()`), `%`/`fr`/`minmax()` widths, and `max-width:100%` on
  media. Never a fixed pixel width that forces horizontal scroll. The page body must
  never scroll sideways on a 375px viewport.
- Tap targets ≥ ~44px; don't rely on hover to reveal anything essential on touch.

## 6. Always check your work — verification is not optional

After any visual change, verify it in the browser preview before calling it done.
Never ask the user to eyeball it for you. Use the Browser-pane tools:

1. Start/refresh the dev server preview (`surge-frontend`, port 3000).
2. Check `read_console_messages` and `preview_logs` — zero errors.
3. **Desktop pass** (`resize_window` desktop, 1280×800): screenshot the changed
   surface; confirm layout, alignment, type hierarchy, and that nothing is purple/
   gradient-souped.
4. **Mobile pass** (`resize_window` mobile, 375×812): screenshot again; confirm the
   collapse behavior from §5 and that there's no horizontal scroll.
5. Spot-check computed styles with `javascript_tool` + `getComputedStyle` when a color
   or font needs confirming (don't trust the source — confirm the rendered value).
6. Share the before/after or the two screenshots as proof.

> Verification gotcha: a backgrounded/hidden preview tab runs with
> `visibilityState:hidden`, which freezes CSS opacity transitions and `rAF` — reveal
> animations then read as opacity:0 (black) in screenshots even though they're fine.
> Verify those via `getComputedStyle` with transitions disabled, or force the element
> visible, rather than trusting a raw screenshot of a hidden tab.

---

## Quick self-audit before you finish

- [ ] Zero purple/indigo/violet UI (Instagram brand wordmark is the only exception).
- [ ] No default gradient hero/cards/buttons; accent used sparingly and correctly
      (citron = act, ice = inform).
- [ ] Colors are tokens; no stray hardcoded hex.
- [ ] Schibsted Grotesk display + Instrument Sans body; real size/weight hierarchy;
      tight heading tracking; sane measure.
- [ ] If the user gave a reference, the result demonstrably follows it (in Phosphor).
- [ ] Correct and screenshotted at BOTH 1280px and 375px; no horizontal scroll.
- [ ] Console/log clean; reduced-motion respected.
- [ ] It looks intentionally designed, not generated. If in doubt, it isn't done.
