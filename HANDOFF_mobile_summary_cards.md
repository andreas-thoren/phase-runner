# Handoff: mobile summary cards (temporary — delete when done)

Status as of 2026-09-23: **design discussion, nothing implemented.** Only mockups exist.

## Goal

Replace the summary page's phone-width (≤640 px) microcycle cards with a richer card
design: plan vs actual with progress bars, an HR-zone intensity bar, and loads. The
desktop table stays as it is.

## Files

- `docs/mockups/microcycle-card-mockup.html` + `microcycle_card_mockup.png`: the
  original mockup (a starting point; don't copy its fonts or colours).
- `docs/mockups/microcycle-card-mockup-v2.html`: the revised mockup. It links the real
  Pico and app CSS. Open it in a browser at phone width; the controls at the top switch
  the current-week style and light/dark.

## Decisions made

- **Keep Pico themes and current fonts.** Take nothing literally from the original
  mockup's colours or fonts.
- **Two link areas per card (option A):**
  - **Header** (label, date, type, comment) goes to the microcycle and gets a blue tint.
  - **The rest** (plan vs actual + intensity) goes to the workouts and gets a green tint,
    with a visible "Workouts ›" link in its section heading.
  - Each area is one real `<a>` whose `::after` stretches over the area, so each card
    has two Tab stops, no `tabindex` and no click JS. Focus uses
    `.mc-area:has(.mc-link:focus-visible)` for the tint plus a 2px primary ring. The ring
    is the only ring used, so it must not be reused for anything else.
  - The workouts link needs a unique accessible name, e.g.
    `aria-label="Workouts, Mon 14 – Sun 20 Sep"`.
- **Render twice:**
  - Keep the `<table>` for desktop and add a card list (`<article>`s) for ≤640 px,
    switched by media query.
  - Both read the same `rows` from `_build_summary_rows()`; the DB work happens once.
    Put the card in an `{% include %}` partial.
  - This replaces the current CSS-grid restyle of the table cells on mobile (including
    the `section-heading` `<th>`s and the `:has()` heading tints), which can then be
    removed.
  - `summary_nav.js` would then drive only the desktop table.
- **Current week:** a `now` chip (reuse `.chip.chip--now` from the reorder page) plus
  one more marker, chosen from the options in the mockup (see open questions). Don't
  use a border or ring, since those would look like focus.
- **No session dots.** Use a progress bar or plain text.
- **Progress bars:** native `<progress value max>`.
  - Colours: `--pico-primary` while in progress, `--pico-ins-color` when met.
  - Never red for going over; `<progress>` stops at full on its own.
  - Always set `value`; without it the bar is indeterminate and animates.
- **New Z1–Z5 colour tokens** (SCSS, light and dark values) are fine. The mockup has
  proposed values.
- **Future weeks:** plan only, with empty bars and no Intensity section.
- **Mesocycle heading:** keep today's heading and blue left bar. Skip the original
  mockup's segmented progress bar.
- **Design changes from the original mockup:**
  - no filled boxes inside the card: use dividers and text hierarchy instead
  - one layout for every week: when there's no plan, rows show only the actual value
    with no "/ planned" and no bar, and the section heading reads "Actual" instead of
    "Plan vs actual"
  - cross-training and strength as plain text (`Cross-training 1 / 1 · Strength 0 / 1`),
    hidden when there's neither a plan nor a session; no pill chips, which look tappable
  - type badge in a neutral style
  - header label `Base 2 / 3`, adding `· N days` only when the week isn't 7 days
  - no comment block when there's no comment
  - both loads on one line: `Run load 322 · Total load 389`
- The `cols` filter (comment/x/str/zones/sportload/totload) must still hide the
  matching card parts.
- The zone bar needs per-segment widths in the markup, e.g. `style="flex-grow: 28"`.
  That's an inline style, not inline JS, so it's allowed, but it's the one place that
  isn't pure SCSS.

## Open questions (to answer next)

1. **Current-week style:** "chip only", "chip + tint" (the mockup default), or
   "chip + top edge"?
2. **When does a goal count as met?** 22.8 / 23 km currently shows as not met (blue).
   Should there be a tolerance, e.g. 95% or more counts as met, or stay strict?
3. **Type badge:** its border is faint and almost disappears on the tinted current-week
   card. Make it a filled chip?
4. **Workouts link text:** keep the generic "Workouts ›", or show a count ("3 workouts ›")?
   A count reads oddly as "0 workouts" on future weeks.
5. **Optional:** scroll to the current week's card when the page opens?

## Implementation sketch (once the design is settled)

1. Add the row keys the card needs, if they're missing:
   - whether each goal is met
   - whether the week is the current one (use the same `today` as `_aggregate_workouts()`)
   - a flag for a non-7-day week
2. New partial `workouts/partials/summary_card.html`, and a card list in
   `macrocycle_summary.html` grouped with the same `{% regroup rows by meso_pk %}`.
3. SCSS:
   - card styles in `workouts.scss`, reusing the `_cards.scss` mixins where they fit
   - Z1–Z5 tokens
   - hide the table and show the cards at ≤640 px
   - remove the old mobile table-card rules
4. Update the tests (`test_clickable_zones_in_html` and the summary view tests), and
   update `CLAUDE.md` (the `MacrocycleSummaryView` and `_cards.scss` paragraphs).
5. Don't compile SCSS by hand. Live Sass Compiler handles it.
