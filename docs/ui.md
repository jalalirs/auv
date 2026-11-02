# The client's interface: rules

Written 2026-10-18 after the fifth redesign. The four before it each looked
right the week they were made and drifted back, because every screen was
built on its own: twenty font sizes, ten corner radii, one stylesheet edited
per screen, no history, paragraphs standing in for interface. These rules are
what a page is checked against before it is shown to anybody. The numbers are
in `apps/client/src/renderer/ui/tokens.css`, the parts in `ui/components.tsx`.

## 1. Every page has an address, and Back

- Pages are addresses (`#/runs`, `#/place?id=…`) held in the window's history
  (`ui/router.ts`). Moving to a page pushes; Back pops.
- Back works from the mouse's side buttons, a trackpad swipe, Cmd-[ and the
  page's own crumb (`‹ Places`). A detail page always has its crumb.
- A page come back to keeps its scroll, and a list keeps its filters while it
  stays on screen.
- Nothing strands anybody: no screen without a way to where they came from.

## 2. Type: one font, five sizes

Inter, bundled (`ui/fonts`, OFL). Whole pixels only:

| token | size | for |
|---|---|---|
| `--t-meta` | 12 | labels, column heads, timestamps, units |
| `--t-body` | 14 | everything read |
| `--t-strong` | 16 | a row's name, a card's title, a value that matters |
| `--t-section` | 20 | a section heading |
| `--t-title` | 28 | the page title, once |

Numbers in tables are tabular. Nothing under 12 px.

## 3. Space and shape

A 4 px grid (`--s1` 4 to `--s7` 48). Two radii: 6 for controls, 12 for
surfaces, and round for status pills. Two control heights: 32 and 40.

## 4. Buttons

- Three kinds: **primary** (the accent fill), **secondary** (outlined),
  **ghost** (text), and danger for what destroys.
- **At most one primary per page**, in the page head's actions. A row may
  have one primary-looking action only if it is *the* thing the row is for.
- A row's other actions go in its **⋯ menu**, not as four buttons in a line.
- No oversized buttons inside pictures or heroes.

## 5. Zoom and width

- Zoom is held between 80% and 125% (Electron main; no pinch).
- Every page is checked at 1280 px wide, at 100% and at 125%.
- Tables never scroll sideways: low-priority columns drop
  (`priority` 2 under 900 px of table, 3 under 1150 px).

## 6. The frame stays, the content scrolls

The rail, the page head (crumb, title, subtitle, actions, tabs, toolbar) do
not move. Only the page body scrolls. A list's toolbar stays above it.

## 7. Lists

Any list that can pass about twenty rows is a `Table`: search, filters with
counts per value, sortable columns, pages of 25. Grouped things (a sweep's
runs, a controller's versions) fold under one row or into a section on the
thing's own page, never a tab of their own.

## 7a. No tab per concept (2026-11-02)

A different kind of thing never gets a tab. A thing's parts live on the
thing: a controller's versions on its page, a sweep as a run under several
conditions, a store place as a copy in Places. A switch (`Segmented`) is only
for two views of the same list, such as every run against repeated runs.

## 8. Words

- A page subtitle is **one line**. The long version goes behind the title's
  (i).
- Labels say what a thing is, in plain words, sentence case.
- Never placeholder data on a screen without saying so where it is shown.
- Every number keeps its kind (measured, derived, chosen, assumed) where it
  matters.

## 9. Every page has a job

A page shows things somebody acts on, and the actions are on it. A page that
is only explanation is merged into the page where the thing is used, or
taken off the rail until it has something to do.

## 10. States

Loading, empty and failed look the same everywhere: an empty list says what
fills it and offers the action that does; a failure says what failed and
offers to try again.

## Checking a page

1. Screenshot it at 1280 x 800 at 100% and at 125%.
2. Count the primary buttons (≤ 1) and the font sizes (only the five).
3. Open something from it and press Back: same page, same scroll.
4. Shrink the window to 1100 px: nothing scrolls sideways.
