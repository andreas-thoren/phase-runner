# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run dev server
uv run python manage.py runserver

# Run all tests
uv run python manage.py test

# Run a single test class or method
uv run python manage.py test workouts.tests.test_models.WorkoutModelTest
uv run python manage.py test workouts.tests.test_models.WorkoutModelTest.test_duration_validation

# Lint
uv run pylint workouts/

# Format
uv run black .

# Load fixture data (required after fresh migrate)
uv run python manage.py loaddata workouts/fixtures/initial_data.json

# Dump fixture data (after changing lookup tables)
uv run python manage.py dumpdata workouts --indent 2 --natural-foreign --natural-primary > workouts/fixtures/initial_data.json

# Create 3000 test workouts (requires fixtures loaded first)
uv run python manage.py create_test_workouts

# Rebuild DB from scratch (drop db + migrations, recreate, load fixtures)
uv run python manage.py rebuild_db
uv run python manage.py rebuild_db --create-test-data  # also creates test workouts

# Deploy to production
git push dokku main
```

## Architecture

Single Django app (`workouts`) with one `Workout` model and optional detail models (OneToOne) for type-specific data.

### SlugFieldMixin

- Abstract model mixin adding an auto-created, unique `slug` field (`editable=False`).
- Slug is regenerated on every `save()`/`clean()` from the field named by `_slug_source_field` (default `"name"`). Override `get_slug()` for custom logic. Changing the source field automatically updates the slug.
- Collision handling: appends `-1`, `-2`, etc. via `_unique_slug()`.
- Used by: `WorkoutSubtype`.
- Fixtures must include explicit `slug` values since `loaddata` bypasses `save()`.

### OrderMixin

- Abstract model mixin that ensures gap-free ordering among siblings on delete.
- Subclasses set `_order_parent_field` to the FK field name scoping the order (e.g. `"macrocycle"` for Mesocycle, `"mesocycle"` for Microcycle).
- On `delete()`: decrements `order` for all siblings above the deleted row.
- Used by: `Mesocycle`, `Microcycle`.

### Model Design

- **`WorkoutSubtype`**: named subtype (e.g. Running, Cycling) linked to a parent `WorkoutType`. Has a `gui_schema` property that reads from the `GUI_SCHEMAS` Python constant (keyed by slug), defining dynamic UI inputs (key → `{type, label}`). Protected from deletion while workouts reference it (`on_delete=PROTECT`). Has `natural_key()` (`name`, `parent_type`) so fixtures use natural keys instead of hardcoded PKs.
- **`Workout`**: core model — user, name, start_time, description, workout_status (CharField keyed to `WorkoutStatus` enum, default `PLANNED`), workout_type (no default), subtype (mandatory FK → WorkoutSubtype). Subtype is set at creation and not editable afterwards. `clean()` validates subtype's `parent_type` matches `workout_type`. `gui_fields` property reads dynamic field values from the detail's `additional_data["gui_fields"]`.
- **`DetailBase`** (abstract): shared detail fields (duration, additional_data). Auto-registers concrete subclasses via `__init_subclass__` into `DetailBase._detail_registry`, keyed by `WorkoutType` enum. `get_related_name()` introspects the OneToOne `related_name` for dynamic `select_related` and reverse accessor lookups. `clean()` validates that the detail's `_workout_type` matches `workout.workout_type` and that `additional_data["gui_fields"]` keys are a subset of the subtype's `gui_schema`.
- **`AerobicDetails`**: OneToOne → Workout. `distance` is a `PositiveIntegerField` storing meters (same convention as `Microcycle.planned_distance`). `distance_km` property converts to km for display. `speed` (km/h), `pace` (seconds/km), and `pace_display` (`M:SS min/km`) are computed from the meters value. The form (`AerobicDetailsForm`) accepts km input and converts to/from meters.
- **`StrengthDetails`**: OneToOne → Workout. Adds num_sets, total_weight.
- **`GenericDetails`**: OneToOne → Workout. No extra fields beyond DetailBase (duration, additional_data).
- `DetailBase.save()` always calls `full_clean()`, enforcing model validation on every save.
- **GUI fields**: dynamic subtype-specific fields stored in `additional_data["gui_fields"]`. Schema defined in the `GUI_SCHEMAS` constant in `models.py`, keyed by subtype slug. Accessed via `WorkoutSubtype.gui_schema` property. Create/edit views render a dropdown to add fields; detail views display them read-only. `load_garmin` (Garmin training load) is a gui field present on all subtypes; the summary view reads it from gui_fields for load aggregation.

### Periodization Models

- **`Macrocycle`** → **`Mesocycle`** → **`Microcycle`**: hierarchical training plan structure. Dates are computed bottom-up from `Microcycle.duration_days` (the single source of truth).
- **`Macrocycle`**: user-scoped (`user` FK, CASCADE). `name` is unique per user (`UniqueConstraint(fields=["user", "name"])`). Stores `start_date`, `description`. `end_date` and `scheduled_duration` are computed properties.
- **`Mesocycle`**: ordered within a macrocycle via `order` (auto-incremented on create, `UniqueConstraint`). Uses `OrderMixin` (gap-free on delete). Has `meso_type` keyed to `MesocycleType` enum. `start_date`, `end_date`, `duration_days` are computed properties.
- **`Microcycle`**: ordered within a mesocycle via `order`. Uses `OrderMixin` (gap-free on delete). `duration_days` (default 7) drives all date computation. Has `micro_type` keyed to `MicrocycleType` enum (default `LOAD`). Has planning goal fields (`planned_num_runs`, `planned_distance`, `planned_long_run_distance`, `planned_strength_sessions`, `planned_cross_sessions`).
- **Hydration**: All computed date/duration properties require hydration — accessing them without it raises `AttributeError`. Call `macro.hydrate()` (instance method) to fetch the full tree (2 queries), compute dates in Python, and cache on instances. Access children via `macro.hydrated_mesocycles` / `meso.hydrated_microcycles`.
- **`create_default_cycles(macrocycle, target_duration_days, meso_duration_days, micro_duration_days)`** (in `utils.py`): standalone function that auto-generates mesocycles and microcycles for a macrocycle. Uses `transaction.atomic()`. Guards: raises `ValueError` if mesocycles already exist. Each meso gets `meso_duration_days` days, filled with full-length micros and one shorter remainder micro if needed. Macro-level remainder meso uses the same fill logic. Meso types cycle through a 5-value subset: BASE → BUILD → SHARPEN → PEAK → TRANSITION. Helper `_fill_microcycles()` assigns `LOAD` to all microcycles except the last per mesocycle which gets `DELOAD`.
- **`ActiveMacrocycle`**: one-per-user mapping (`user` OneToOneField as PK) to the currently active macrocycle. CASCADE on both FKs.
- Cascade delete: deleting a macrocycle removes its mesocycles and their microcycles.

### Authentication

- **Django built-in auth** with `LoginRequiredMixin` on every view. Anonymous users are redirected to `/login/`.
- **Invite-only**: no self-registration. Admin creates users via `/admin/`. Self-registration can be added later.
- **Password reset**: Django's built-in 4-view flow (`/password-reset/` → email → `/reset/<uidb64>/<token>/` → done). Console email backend for dev (`EMAIL_BACKEND` in settings); swap to SMTP for production.
- **Auth URLs** defined at project level in `phaserunner/urls.py` (names: `login`, `logout`, `password_reset`, `password_reset_done`, `password_reset_confirm`, `password_reset_complete`).
- **Templates** in `workouts/templates/registration/`: `login.html`, `password_reset_form.html`, `password_reset_done.html`, `password_reset_confirm.html`, `password_reset_complete.html`. All extend `base.html` with `narrow-page` app class. Form templates use the `form_field.html` partial and `button-row` layout.
- **User-scoped data**: all querysets filter by `request.user`. `Workout` and `Macrocycle` have `user` FK. Child models (Mesocycle, Microcycle) are secured via parent lookup (`MacrocycleChildMixin`, `MesocycleChildMixin`).
- **Context processors** (`grouped_subtypes`, `sidebar_navigation`) return empty data for anonymous users.
- **`base.html`** hides sidebar/breadcrumb for anonymous users; shows username + Logout link for authenticated users. Provides `{% block app_class %}` on `div.app` for per-page CSS class injection.
- **OAuth** (Google/Outlook) not yet implemented but the setup is compatible with `django-allauth` for future addition.

### View Architecture (all CBVs)

- **`PaginationMixin`**: adds a sliding page-range window (`pagination_window = 5`) to any paginated `ListView`. Used by `BaseWorkoutListView` and `MacrocycleListView`.
- **`BaseWorkoutListView`**: shared base for workout list views. Provides `select_related`, filtering (date range, status via `WorkoutFilterForm`), and `show_filters` query param.
- **`WorkoutListView`**: extends `BaseWorkoutListView`. Adds activity (subtype) filter. Uses `workout_list.html`.
- **`RunningListView`**: extends `BaseWorkoutListView`. Filtered to Running subtype with `select_related` on `aerobic_details` for distance/pace. Uses `running_list.html`.
- **`MacrocycleListView`**: paginated list of macrocycles ordered by `-start_date`. Uses `macrocycle_list.html`.
- **`FormContextMixin`**: auto-resolves `view_type`, `read_only`, and CRUD URLs (`edit_url`, `delete_url`) for `form_base.html`. Derives model name from `self.model._meta.model_name` and URL kwargs from `self.kwargs`. Concrete views only set `view_type` as a class attribute. URL names must follow the convention `edit_{model}`, `delete_{model}`, `{model}_detail`, `{model}_list`. Also provides `cancel_url` for mutation views: `get_absolute_url()` for update/delete, `get_parent_url()` or list URL for create. `get_parent_url()` is used by `get_success_url()` and `cancel_url` for post-create/delete redirects; child models without a list view override it to return the parent's URL.
- **`MacrocycleChildMixin`**: resolves parent macrocycle from `kwargs["macro_pk"]`, scopes `get_queryset()` by macrocycle, and provides `get_parent_url()` returning the macrocycle detail URL. Used by Mesocycle CRUD views.
- **`MesocycleChildMixin`**: resolves parent mesocycle from `kwargs["macro_pk"]` + `kwargs["meso_pk"]`, scopes `get_queryset()` by mesocycle, and provides `get_parent_url()` returning the mesocycle detail URL. Used by Microcycle CRUD views.
- **`IndexView`**: redirects to the active macrocycle's summary page if an `ActiveMacrocycle` exists for the user, otherwise redirects to the macrocycle list (`/plans/`).
- **`MacrocycleDetailView`/`MacrocycleCreateView`/`MacrocycleEditView`/`MacrocycleDeleteView`**: CRUD views for Macrocycle using `MacrocycleForm`. Share `macrocycle_form.html` template, branching on `view_type`. Detail view hydrates the macrocycle and renders a mesocycle table (master-detail) via `{% block after_form %}`. Detail view provides `can_create_defaults` and `create_defaults_url` context for the empty-state link to generate cycles. Detail view adds `is_active` and `toggle_active_url` context for the active-badge toggle.
- **`MacrocycleCreateDefaultCyclesView`**: GET+POST `FormView` using `CreateCyclesForm` (non-model form with `target_duration_days`, `meso_duration_days`, `micro_duration_days`). GET renders the form; POST validates and calls `utils.create_default_cycles()`, then redirects to macrocycle detail. If the macrocycle already has mesocycles, renders an error message instead of the form. Does not use `FormContextMixin` — provides `view_type`, `cancel_url`, and `submit_label` ("Create") manually. Template: `create_cycles_form.html`. URL: `plan-<int:macro_pk>/create-defaults/` (name: `create_default_cycles`).
- **`ToggleActiveMacrocycleView`**: POST-only view. Toggles the `ActiveMacrocycle` row: if the macrocycle is already active, deletes it (deactivate); otherwise, `update_or_create` sets it as active (replacing any previous). Redirects to the macrocycle detail. URL: `plan-<int:macro_pk>/toggle-active/` (name: `toggle_active`).
- **`MacrocycleSummaryView`**: read-only overview table (extends `DetailView`, not `FormContextMixin`). Hydrates the macrocycle, flattens mesocycles→microcycles into rows with planned goals (distance, long run) on the left and aggregated actual workout stats (runs, distance, load, cross, strength) on the right. Single query via `_aggregate_workouts()` buckets workouts into microcycles by date range. Template: `macrocycle_summary.html` (extends `base.html`). URL: `plan-<int:macro_pk>/summary/` (name: `macrocycle_summary`). Linked from the macrocycle detail page toolbar when mesocycles exist.
- **`MesocycleDetailView`/`MesocycleCreateView`/`MesocycleEditView`/`MesocycleDeleteView`**: CRUD views for Mesocycle using `MesocycleForm` + `MacrocycleChildMixin`. Share `mesocycle_form.html` template. Create sets `macrocycle` FK from URL; edit/delete scope queryset by parent macrocycle. Detail view hydrates the macrocycle and renders a microcycle table (master-detail) via `{% block after_form %}`.
- **`MicrocycleDetailView`/`MicrocycleCreateView`/`MicrocycleEditView`/`MicrocycleDeleteView`**: CRUD views for Microcycle using `MicrocycleForm` + `MesocycleChildMixin`. Share `microcycle_form.html` template. Lookup by PK (`pk_url_kwarg = "micro_pk"`). Create sets `mesocycle` FK from URL; all redirects go to parent mesocycle detail.
- **`WorkoutMutateMixin`**: shared base for `WorkoutCreateView` and `WorkoutEditView`. Provides unified `get_workout_type()` (from existing object or URL kwarg), `get_context_data()` (detail form, gui schemas/fields), and `form_valid()` (detail create/update/delete + gui_fields storage). Only stores `gui_fields` in `additional_data` when non-empty.
- **`WorkoutCreateView`**: extends `WorkoutMutateMixin`. Renders `WorkoutForm` + detail form based on `workout_type` URL kwarg. Requires `?subtype=<slug>` query param (set by navbar dropdown); 404 if missing or mismatched. Subtype is not a form field — it's set on the instance in `get_form()`.
- **`WorkoutEditView`**: extends `WorkoutMutateMixin`. All context and save logic inherited from the mixin. If all detail fields and gui_fields are cleared, the detail row is deleted. If no detail exists but fields are filled in, a new detail row is created.
- **`WorkoutDetailView`/`WorkoutDeleteView`**: render workout + detail forms read-only, branching on `view_type` context variable.
- `list_base.html` is shared across all list views via template blocks (`page_title`, `heading`, `toolbar`, `table_head`, `table_body`, `empty_message`). Includes table and pagination markup. Loads `clickable_rows.js` via `{% block scripts %}`; child templates that need additional scripts use `{{ block.super }}`.
- `partials/workout_filters.html` is the filter bar partial, included via `{% include %}` with optional `show_activity=True` variable.
- `form_base.html` is the shared base for all CRUD form templates. Sets `narrow-page` app class on `div.app` to constrain width. Provides heading, action icons (detail view), form wrapper with CSRF, and button row (create/update/delete). Loads `form_handler.js` via `{% block scripts %}`; child templates that override this block must include `{{ block.super }}`. Concrete templates extend it and fill `page_title`, `heading`, `after_heading`, `scripts`, `form_content`, `button_row`, and `after_form` blocks. Views provide context: `view_type`, `read_only`, `edit_url`, `delete_url` (detail), `cancel_url` (mutation views), `submit_label` (defaults to "Save"). The `button_row` block wraps the Cancel + Submit buttons and can be overridden by child templates (e.g. to suppress buttons conditionally). Edit/delete icon links and cancel buttons use `data-replace` + `form_handler.js` for `location.replace()` navigation, keeping mutation views out of browser history. Cancel falls back to `history.back()` via `data-back` if `cancel_url` is not provided. Form submissions on mutation views are intercepted by `form_handler.js` (fetch POST + `location.replace()` on redirect, normal submit on validation errors). Ctrl+S / Cmd+S triggers Save on create/edit views (not delete).
- `macrocycle_summary.html` extends `base.html` — two-header-row summary table with planned vs actual columns per microcycle.
- `create_cycles_form.html` extends `form_base.html` — form for generating default mesocycles/microcycles (non-model form). Shows error message if cycles already exist; overrides `button_row` to hide buttons in that case.
- `macrocycle_form.html` extends `form_base.html` — renders macrocycle form fields.
- `mesocycle_form.html` extends `form_base.html` — renders mesocycle form fields.
- `microcycle_form.html` extends `form_base.html` — renders microcycle form fields.
- `workout_form.html` extends `form_base.html` — renders workout + detail forms, gui fields, and gui schema scripts.
- Detail forms are mapped in `forms.py` via `DETAIL_FORMS` dict (WorkoutType → form class).

### Enums

- All domain enums inherit from `ChoicesEnum` (a `StrEnum` subclass providing a Django-compatible `choices()` classmethod).
- `WorkoutType`: `AEROBIC`, `STRENGTH`, `GENERIC` — identifies workout types.
- `WorkoutStatus`: `PLANNED`, `COMPLETED`, `CANCELLED`, `POSTPONED` — workout lifecycle states.
- `MesocycleType`: `BASE`, `PREP`, `BUILD`, `SHARPEN`, `SPECIFIC`, `PEAK`, `TRANSITION` — mesocycle training phases.
- `MicrocycleType`: `INTRO`, `LOAD`, `OVERLOAD`, `CONSOLIDATE`, `DELOAD`, `TAPER`, `RACE` — microcycle load profiles.
- `ViewType` (StrEnum): `CREATE`, `UPDATE`, `DETAIL`, `DELETE` — used by templates.

### Breadcrumbs

- **`BreadcrumbItem`** (frozen dataclass): `label: str`, `url: str = ""` (empty = current page, not a link). Defined in `context_processors.py`.
- **`_build_breadcrumbs(url_name, kwargs, request)`** dispatches to `_plan_crumbs()` (macro/meso/micro hierarchy) and `_workout_crumbs()` (workout pages). Returns `list[BreadcrumbItem]`.
- **DB lookups**: one lightweight `values_list` query per ancestor level (PK index), max 3 queries for deepest pages (microcycle edit/delete). Fallback labels ("Plan", "Mesocycle", etc.) on `DoesNotExist`.
- **`_URL_SIDEBAR_MAP`** handles sidebar highlighting separately — maps url_name → `(section, item)` tuple. Breadcrumb labels and hierarchy are built independently.
- **Template** (`partials/breadcrumb.html`): dynamic `{% for crumb in breadcrumbs %}` loop. Hamburger button in `.breadcrumb-hamburger` `<li>`.
- **SCSS** (`navigation.scss`): breadcrumbs visible on all screen sizes. On desktop (>= `$sidebar-breakpoint-lg`): hamburger hidden via `.breadcrumb-hamburger { display: none }`, breadcrumb sits in `breadcrumb` grid area above main content. On mobile: sticky positioning, horizontal scroll for long trails.

### Static Files / CSS

- **Pico CSS** framework in `static/css/pico.min.css` with overrides in `pico_override.css`.
- SCSS source in `workouts/assets/scss/`, compiled by VS Code Live Sass Compiler to `workouts/static/workouts/css/`. Shared SCSS variables in `_variables.scss` partial (imported via `@use 'variables' as v`).
- **NEVER edit CSS files directly** — only edit the SCSS source files. The CSS files are compiler output. After finishing SCSS edits, remind the user to verify the Sass compiler has recompiled.
- **CSS convention**: Use Pico CSS for component styling (buttons, forms, tables, nav, typography). Use CSS Grid or Flexbox for layout.
- **Narrow-page layout**: `div.app.narrow-page` constrains page width to `$form-max-width` (1024px) + padding. Used by `form_base.html` and all auth templates. On desktop (>= `$sidebar-breakpoint-lg`), pages with a sidebar (`:has(#sidebar-menu)`) expand to `$form-page-max-width` (1024px + sidebar + gap + padding). The desktop 2:1 left-margin shift and CSS grid layout on `main` are also scoped via `:has(#sidebar-menu)`, so auth pages (no sidebar) stay centered.

### JavaScript

- **No inline JS**: all JavaScript must live in dedicated `.js` files under `workouts/static/workouts/js/`. No `<script>` blocks or inline event handlers (`onclick`, etc.) in templates. To pass Django template data to JS, use `data-*` attributes on HTML elements that the JS file reads.
- **Load with `defer`**: script tags go in the `<head>` (or a `{% block scripts %}`) with the `defer` attribute. Do not use `DOMContentLoaded` wrappers — `defer` already guarantees the DOM is ready before execution.

### Deployment

- **Hetzner VPS + Dokku** (PaaS). Deploy via `git push dokku main`. The `Procfile` includes a release task that runs `migrate --noinput` automatically on every deploy — no manual migration needed.
- **Domain**: `phaserunner.app` managed via **Cloudflare** with DNS proxy enabled (orange cloud). `.app` domains are HSTS-preloaded (HTTPS-only in browsers).
- **SSL**: Let's Encrypt on Dokku for origin certificate; Cloudflare handles edge SSL (proxy status: orange cloud). SSL must be set up before the site is accessible because `.app` domains reject HTTP.
- **Buildpack**: Heroku Python buildpack detects `uv.lock` natively — no `requirements.txt` needed. A `.python-version` file (minor version only, e.g. `3.13`) is required.
- **SSH**: `/etc/ssh/sshd_config` must include `AllowUsers deploy dokku` — the `dokku` user handles `git push` authentication.
- **Healthcheck**: `/healthcheck/` is exempted from `SECURE_SSL_REDIRECT` via `SECURE_REDIRECT_EXEMPT` in production settings, and `localhost` is in `ALLOWED_HOSTS`. These fixes are unverified — the deploy that succeeded had checks disabled. Both are harmless to keep; need to verify on next deploy with checks enabled.
- Detailed setup steps in `dev_documents/django_hertzner_tuturial.md` and `dev_documents/DEPLOYMENT.md`.

## Code Style

- Max line length: 100 (pylint config)
- Formatter: black
- Linter: pylint with `pylint-django` plugin
- Docstrings not required (disabled in pylint)
- Use modern type hints (`int | None`, `list[str]`, etc.) when creating or editing functions, methods, and classes — do not use `Optional`, `Union`, or `typing` equivalents

## Pre-commit Checklist

Before every commit, always:
1. Run `uv run black .` to format the entire repo.
2. Review and update `CLAUDE.md` and `README.md` if the changes affect architecture, commands, or conventions — even if the user doesn't explicitly ask.
