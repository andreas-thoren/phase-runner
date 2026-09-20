# Reorder Cycles — Implementation Plan

Feature branch: `reorder-cycles`
Mock-up: `docs/mockups/reorder.html` (open directly in a browser, no server needed)

Lets a user reorder mesocycles within a macrocycle, and microcycles within *or between*
mesocycles, from a single screen.

---

## 1. Decisions already taken

| Question | Decision | Why |
| --- | --- | --- |
| One combined view, or one per level? | **One view** | Microcycles must be droppable into another mesocycle, so the micro view has to render mesocycle grouping anyway — two views means building ~80% of it twice, and a worse UX. |
| Drag-and-drop? | **No — tap-to-select, then tap-to-place** | Identical behaviour on mouse, touch and keyboard. HTML5 DnD does not work on touch at all, so drag would mean vendoring SortableJS. ~60 lines of JS instead. |
| Mesocycle reordering UI | **▲ ▼ buttons** | Only 5–10 mesocycles, each a tall block. Buttons stay usable at phone width and are accessible for free. |
| Reordering past (already-trained) cycles | **Allowed, but made visible** | Every shifted row shows `was <date> · ±Nd`; a banner counts how many shifted rows overlap already-trained dates. |
| Confirm dialog before saving a shift that touches trained weeks? | **No — banner only** | The warning is on screen the whole time you edit. No other mutation view in the app gates on a modal (not even macrocycle delete). |
| Mesocycle left with zero microcycles | **Allowed** | `hydrate()` already handles it (0 days, `start == end`). Keeps reorder a pure move operation — you can empty a phase en route to refilling it. Rendered explicitly as `Empty — 0 days`. |
| Drop `CHECK ("order" >= 0)` to simplify staging? | **No** | Buys nothing: `order = -order` and `order = order + 10000` are the same single statement. Costs an `AlterField` migration on both models and removes the only guard against a negative order, since `.update()` bypasses Django field validation. |

### Out of scope (deliberately)

- Editing `duration_days`, `micro_type` or `meso_type` from this screen.
- Re-deriving `micro_type` after a move. `_fill_microcycles()` assigns `DELOAD` to the last
  microcycle of each mesocycle at generation time; after a reorder that no longer holds.
  We leave it alone — silently rewriting the user's own classifications would be worse than
  a stale label. Worth a follow-up issue if it turns out to bother you in practice.
- Undo/redo beyond the in-page **Reset** button (which restores the order the page loaded with).

---

## 2. Database analysis

No migrations are required. Nothing about the schema changes — only `order` values and
`Microcycle.mesocycle_id` are written. (So the CLAUDE.md "does production have real data?"
question does not arise here.)

Three facts from the live schema drive the whole backend design:

```sql
CONSTRAINT "uq_meso_order"  UNIQUE ("macrocycle_id", "order")
CONSTRAINT "uq_micro_order" UNIQUE ("mesocycle_id", "order")
"order" smallint unsigned NOT NULL CHECK ("order" >= 0)
```

**(a) The unique constraints are immediate, not deferrable.** The FKs are
`DEFERRABLE INITIALLY DEFERRED`; the unique constraints are not. Neither SQLite nor
PostgreSQL defers a unique check to end-of-statement, so any `UPDATE … SET order = order ± 1`
across a range can raise a duplicate-key error part-way through, depending on the order the
backend happens to visit rows in.

This is a **latent bug in the existing `OrderMixin.compact_siblings()`** (`models.py:108`).
Decrementing survives today only because rows tend to be visited ascending; visited
descending, `6→5` collides with the live `5`. Since we are touching `OrderMixin` anyway,
this gets fixed by the same mechanism.

**(b) `order` cannot go negative**, so the usual "stage at `-order`" trick is unavailable.

**(c) Therefore: two-phase renumber with a high staging offset.**

```
Phase 1  UPDATE … SET order = order + 10000   -- park every affected row
Phase 2  write the final 1..N
```

This is safe *by construction*, independent of row visit order, because the target range of
each phase is disjoint from the live range at the time it runs:

- Phase 1 moves `1..N` → `10001..(10000+N)`. No new value can equal any old value (given
  `N < 10000`), and the new values are distinct among themselves.
- Phase 2 writes `1..N` while every live row sits at `10001+`. Again disjoint, again distinct.

`smallint` maxes at 32767 and a plan has well under 100 cycles, so the headroom is ample —
but assert `N < STAGING_OFFSET` anyway and fail loudly rather than corrupting order values.

Because *all* microcycles in the macrocycle are parked before any are written, a microcycle
can change `mesocycle_id` and `order` in the same statement without risk: its new
`(mesocycle_id, order)` pair can collide neither with a parked row (order ≥ 10001) nor with
an already-written row (different mesocycle, or different index).

This also means `bulk_update()` is safe here even though it emits one multi-row
`UPDATE … CASE WHEN` — the parking phase is what makes that true.

**(d) Lock the macrocycle, not the parents.** A cross-mesocycle move touches two `mesocycle`
rows. `OrderMixin._lock_parent()` (`models.py:103`) locks one, so two concurrent A→B / B→A
moves could deadlock. Reordering is a plan-level operation, so take a single
`select_for_update()` on the `Macrocycle` row — one lock, no lock-ordering discipline needed.

> **Testing limitation, stated up front:** `select_for_update()` is a no-op on SQLite, and
> SQLite will not reproduce PostgreSQL's transient unique-violation behaviour. Neither the
> locking nor the collision-safety can be regression-tested in dev. They are correct by
> construction (disjoint ranges, single lock); the tests below verify the *resulting order*,
> which is the best proxy available locally.

---

## 3. Backend

### 3.1 `workouts/models.py` — `OrderMixin`

```python
class OrderMixin(models.Model):
    _order_parent_field: str
    ORDER_STAGING_OFFSET = 10000

    @classmethod
    def park_orders(cls, queryset: models.QuerySet) -> None:
        """Move `order` out of the live 1..N range so it can be rewritten collision-free."""

    @classmethod
    def apply_order(cls, parent_id: int, ordered_pks: list[int]) -> None:
        """Park, then write 1..N for a single parent. Used by delete and meso reordering."""
```

- `compact_siblings()` is reimplemented on top of `park_orders()` + a renumber, closing the
  latent collision bug. Its public contract is unchanged: it still returns the lazy queryset
  of affected siblings, so the documented subclass-override hook keeps working.
- `delete()` is untouched.
- The existing `OrderMixin` tests (`test_models.py:497+`) must keep passing unmodified — they
  are the regression net for this refactor.

### 3.2 `workouts/utils.py` — `apply_cycle_order()`

Single-parent `apply_order()` is not enough for microcycles, because a microcycle can move
*between* parents: every microcycle in the macrocycle must be parked before any is written.
That whole-tree case lives here.

```python
class StaleOrderingError(ValueError):
    """The submitted ordering no longer matches what the database holds."""


def apply_cycle_order(macrocycle: Macrocycle, ordering: list[dict]) -> None:
    """Rewrite the meso/micro ordering of *macrocycle* from a full desired state.

    `ordering` is [{"pk": <meso pk>, "micros": [<micro pk>, ...]}, ...] —
    the complete resulting order, not a move instruction.
    """
```

Behaviour:

1. `with transaction.atomic():` → `Macrocycle.objects.select_for_update().get(pk=...)`.
2. **Re-read the tree inside the lock**, then validate against what was read (not against
   anything fetched before the lock).
3. Validate — any failure raises `StaleOrderingError` and rolls back:
   - submitted mesocycle pks, as a set, equal the macrocycle's mesocycle pks exactly;
   - submitted microcycle pks (flattened), as a set, equal all microcycle pks under those
     mesocycles exactly;
   - no duplicates (`len(list) == len(set)`) at either level;
   - `max(len(mesos), len(micros)) < ORDER_STAGING_OFFSET`.

   Set equality is the whole foolproofing: it catches a stale browser tab, a concurrent
   create/delete from another tab, *and* injected pks belonging to another user's plan, in
   one check. There is no separate ownership check to forget.
4. Park mesocycles and microcycles (2 statements).
5. `bulk_update` mesocycles with their new `order`; `bulk_update` microcycles with their new
   `order` **and** `mesocycle`.

Total ~6 queries regardless of plan size. Idempotent: re-submitting the same ordering is a
harmless no-op, so a double-submit does nothing bad.

### 3.3 `workouts/views.py` — `MacrocycleReorderView`

`LoginRequiredMixin, NoCacheMixin, DetailView`, `pk_url_kwarg = "macro_pk"`,
`get_queryset()` filtered to `user=self.request.user` (so another user's plan 404s).

- **GET** — hydrates the macrocycle and renders `macrocycle_reorder.html`.
  Context includes a `reorder_data` dict, serialised into the page with Django's
  `json_script` filter:

  ```python
  {
    "plan_start": "2026-08-10",
    "today": "2026-09-20",              # server's date, so the warning matches the server
    "save_url": ..., "cancel_url": ...,
    "mesocycles": [
      {"pk": 11, "label": "Base", "micros": [
        {"pk": 41, "label": "Load", "days": 7, "km": 45.0, "long_km": 14.0, "comment": "..."},
      ]},
    ],
  }
  ```

  `today` comes from the server rather than the browser clock, so the "already trained"
  warning agrees with the date bucketing `_aggregate_workouts()` does server-side.

- **POST** — parses a JSON body, calls `apply_cycle_order()`, returns:
  - `200 {"ok": true, "redirect": "<macrocycle detail url>"}`
  - `409 {"ok": false, "error": "This plan changed somewhere else. Reload and try again."}`
    on `StaleOrderingError`
  - `400 {"ok": false, "error": ...}` on malformed JSON / wrong shape

  Rate limiting is deliberately omitted — this is a user mutating their own rows, unlike the
  export and upload endpoints. Easy to add later if it ever matters.

### 3.4 `workouts/urls.py`

```python
path("plan-<int:macro_pk>/reorder/", views.MacrocycleReorderView.as_view(), name="reorder_cycles"),
```

Sits with the other macrocycle URLs, following the existing `plan-<int:macro_pk>/…` convention.

### 3.5 `workouts/context_processors.py`

- `_URL_SIDEBAR_MAP`: add `"reorder_cycles": ("plans", "all_plans")`.
- `_plan_crumbs()`: add a branch next to the `macrocycle_summary` one —
  `if url_name == "reorder_cycles": return trail + [BreadcrumbItem("Reorder")]`.

---

## 4. Front end

### 4.1 `workouts/templates/workouts/macrocycle_reorder.html`

Extends `base.html` (not `form_base.html` — this is not a ModelForm page).

Contains: heading, help line, plan-meta line, the warning banner element, a toolbar with
**Reset** / **Save order**, an empty `#plan` container, `{{ reorder_data|json_script:"reorder-data" }}`,
and an `aria-live` status region.

**Do not reuse the summary `<table>` markup.** It uses `rowspan` mesocycle headers
(`macrocycle_summary.html:103`), and moving a `<tr>` between rowspan'd groups is a fight with
no upside. Build nested sections (mesocycle group → microcycle rows) and reuse the *visual
language* — the blue mesocycle left bar, the planned-zone tints — via SCSS.

> `json_script` emits `<script type="application/json">`, i.e. a data block, not executable
> code. This is a deliberate, narrow exception to the CLAUDE.md "no inline JS" rule: a whole
> plan tree does not belong in a `data-*` attribute. Note it in CLAUDE.md so it doesn't read
> as an oversight later.

The page is JS-rendered, with a `<noscript>` block pointing at the mesocycle detail pages.
This matches the existing precedent of the FIT upload page, which is likewise fully
client-rendered.

### 4.2 `workouts/static/workouts/js/reorder_cycles.js`

Port of the mock-up script, with the hardcoded `INITIAL` constant replaced by a read of
`#reorder-data`. Structure carried over as-is:

- `computeDates(plan)` — mirrors `Macrocycle.hydrate()`: walk mesocycles in order, microcycles
  in order, each start is the running cursor, cursor advances by `duration_days`.
- `locate` / `place` / `moveMeso` / `toggleSelect` — state mutation.
- `render(message)` — rebuilds `#plan`, recomputes every date, diffs against the pristine
  snapshot, updates the banner and the Reset/Save disabled state.
- Save → `fetch` POST with the CSRF token, then `location.replace(redirect)` on success, or
  populate an inline error banner on 4xx (same pattern `form_handler.js` uses).

**Two changes from the mock-up, both required:**

1. Replace `innerHTML` string building with `createElement` / `textContent`. The mock-up's
   data is hardcoded; the real page renders user-authored comments. `fit_upload.js` sets the
   precedent — all DOM manipulation via safe methods, no `innerHTML`.
2. Load with `defer`, no `DOMContentLoaded` wrapper (CLAUDE.md JS conventions).

### 4.3 `workouts/assets/scss/workouts.scss`

Port the mock-up's `<style>` block. Replace the local `--mk-warn` with a project-level token
defined alongside the existing theme variables, and check it in both light and dark mode.

**Edit the SCSS only — never the compiled CSS.** After finishing, verify the Live Sass
Compiler has regenerated `workouts/static/workouts/css/workouts.css`.

### 4.4 Entry points

- `macrocycle_form.html` — add a **Reorder** link in the existing `{% block below_heading %}`
  `.plan-summary-row`, next to **Summary**, shown on the detail view when mesocycles exist.
- `macrocycle_summary.html` — add a Reorder `icon-btn` to the `.list-toolbar`, since the
  summary is where you actually look at plan structure and notice it's wrong.

---

## 5. Tests

### `workouts/tests/test_models.py`

Existing `OrderMixin` tests must pass unmodified — they guard the `compact_siblings` refactor.

New, against `apply_cycle_order()`:

- move a microcycle within its mesocycle (up, down, to first, to last)
- move a microcycle to another mesocycle
- **fully reverse** a mesocycle's microcycles — the case most likely to expose a collision bug
- **fully reverse** the mesocycle order
- no-op ordering (submit current state) succeeds and changes nothing
- empty a mesocycle: allowed; after `hydrate()` it has `duration_days == 0` and `start == end`
- `order` is gap-free `1..N` per parent after every one of the above
- `hydrate()` produces the expected dates after a reorder, and total plan duration is unchanged
- `StaleOrderingError` on: a missing pk, an extra pk, a duplicated pk, a pk from another
  user's macrocycle, a microcycle pk under a mesocycle not in the payload

### `workouts/tests/test_views.py`

- GET redirects anonymous users to `/login/`
- GET 404s for another user's macrocycle
- GET renders and includes the `reorder-data` block
- POST valid ordering → 200, `redirect` present, DB reflects the new order
- POST stale ordering → 409, DB unchanged
- POST malformed JSON → 400
- POST to another user's macrocycle → 404
- breadcrumb trail ends in "Reorder"; sidebar highlights Plans → All plans

---

## 6. Sequencing

1. **Backend + tests, no UI.** `OrderMixin` refactor, `apply_cycle_order()`, full model test
   suite. Verifiable entirely through `uv run python manage.py test`.
2. **View, URL, template, JS.** Port the mock-up; swap `innerHTML` for safe DOM methods.
3. **SCSS + entry points + breadcrumbs.** Recompile SCSS, check light and dark mode, check
   at phone width.
4. **Docs + format.** `uv run black .`, `uv run pylint workouts/`, update `CLAUDE.md`
   (new view / URL / template / JS file, the `OrderMixin` change, `apply_cycle_order`, and the
   `json_script` exception) and review `README.md`. Then commit.

## 7. Files touched

| File | Change |
| --- | --- |
| `workouts/models.py` | `OrderMixin`: `ORDER_STAGING_OFFSET`, `park_orders()`, `apply_order()`, `compact_siblings()` rewritten on top of them |
| `workouts/utils.py` | `StaleOrderingError`, `apply_cycle_order()` |
| `workouts/views.py` | `MacrocycleReorderView` |
| `workouts/urls.py` | `reorder_cycles` path |
| `workouts/context_processors.py` | sidebar map entry + breadcrumb branch |
| `workouts/templates/workouts/macrocycle_reorder.html` | new |
| `workouts/templates/workouts/macrocycle_form.html` | Reorder link beside Summary |
| `workouts/templates/workouts/macrocycle_summary.html` | Reorder toolbar button |
| `workouts/assets/scss/workouts.scss` | reorder styles (recompile after) |
| `workouts/static/workouts/js/reorder_cycles.js` | new |
| `workouts/tests/test_models.py`, `test_views.py` | new tests |
| `CLAUDE.md`, `README.md` | per the pre-commit checklist |

**No migrations.**
