# PhaseRunner

A Django web app for tracking workouts and planning training periodization.

**Live at [phaserunner.app](https://phaserunner.app)** — currently invite-only. Contact [@andreas-thoren](https://github.com/andreas-thoren) to request access.

Log workouts across three types — **aerobic**, **strength**, and **generic** — each with a mandatory activity (e.g. Running, Cycling, Swimming) that provides flexible, schema-driven fields. Plan training blocks with a macrocycle → mesocycle → microcycle hierarchy, and compare planned goals against actual results in a summary view.

## Usage

### Planning a training block

Planning is the core of the app — everything else (logging, summaries, exports) revolves around comparing what you did against what you planned.

1. Open **Plans** in the sidebar → **Create macrocycle**. Pick a primary sport, start date, name.
2. From the macrocycle detail page, click **Create default cycles** to auto-generate mesocycles and microcycles (configurable durations). Or add them manually.
3. Set the macrocycle as **active** (the badge on the detail page) to make the home page redirect to its summary.
4. Open **Summary** to compare planned goals (sessions, distance, long session) against aggregated actuals from your logged workouts.

### Logging workouts

Two ways to add workouts:

1. **Manually** — pick a subtype under **Create Workout** in the sidebar (Running, Cycling, Strength, etc.), fill in the form, save.
2. **In bulk from `.fit` files** — see below.

### Uploading `.fit` files

Garmin (and most fitness platforms) export activities as `.fit` files. PhaseRunner parses them entirely in the browser — nothing is uploaded until you confirm.

1. In the sidebar, open **Workouts → Upload .fit**.
2. Click the file input and select one or more `.fit` files.
3. A preview table appears showing **Datetime**, **Activity**, and auto-generated **Name** (e.g. *Morning Run*, *Afternoon Ride*). Pagination shows 15 rows per page.
4. *(Optional)* Click **Import names from CSV** to replace the auto-generated names with your own — see next section.
5. Click **Upload**. A results panel summarises created, skipped (duplicates), and failed rows.

**Behaviour**

- Duplicates are detected by `(user, start time, subtype)` and skipped silently.
- Supported sports: Running (incl. trail), Cycling (incl. e-bike), Swimming (incl. open water), Skiing, Walking/Hiking, Strength, Mobility. Unmapped sports land in the **Generic** bucket.
- Metrics extracted per sport: HR (avg/max), cadence, power, elevation, training load, pool length / laps (swim), time-in-zone. Distance and duration are always captured for aerobic activities.
- **Limits**: 500 workouts per upload, 20 upload requests/hour, 5000 workouts/week per user (counter resets Monday).

### Patching workout names from a CSV

Useful when you keep workout titles in a spreadsheet and want them applied to a batch of Garmin files on upload.

**Tip — getting a compatible CSV from Garmin Connect.** `.fit` files don't include the custom names you've given your activities, but Garmin Connect does. Open **Activities** in Garmin Connect and use **Export CSV** — the resulting file contains your activity titles alongside their start times, which is exactly what this feature needs. The activities list is lazy-loaded, so scroll to the bottom until all activities you want to include appear before exporting; only loaded rows end up in the CSV.

**CSV requirements**

- Must be a real `.csv` (comma-separated, first row is headers).
- Must contain at least **two columns**:
  - a **name** column (your custom title)
  - a **datetime** column (the activity's start time)
- Extra columns are ignored. Column order doesn't matter — you pick them in the dialog.

**Workflow**

1. After selecting your `.fit` files, click **Import names from CSV** and pick the CSV.
2. A dialog opens with two dropdowns: **Name column** and **Datetime column**. Common headers (`name`, `date`, `datetime`, plus Swedish equivalents `namn`, `datum`) are auto-selected; override if needed.
3. Click **Apply**. The preview table updates with matched names and shows e.g. *"Matched 12 of 15 CSV row(s) to 12 workout(s)."*
4. Click **Upload** as normal.

**Datetime format and matching**

- Accepted formats: `YYYY-MM-DD HH:MM:SS` or `YYYY-MM-DDTHH:MM:SS` (ISO 8601).
- Values are parsed as **browser local time**, then converted to UTC for matching. Make sure the CSV timestamps are in the same timezone as your local clock.
- Matching tolerance is **±1 second**. Each CSV row matches at most one workout.
- CSV rows with no matching workout are silently ignored; workouts with no matching row keep their auto-generated name.

### Exporting

- **Workouts** — filter the list, then click **Export CSV** in the toolbar. Exports respect current filters. Max 5000 rows per export.
- **Plan summary** — click **Export CSV** on the summary page. Column headers match the macrocycle's primary sport (e.g. *Runs / Long run* vs *Rides / Long ride*).

Exports open cleanly in Excel regardless of locale (the file includes a UTF-8 BOM and a `sep=,` hint line).

<details>
<summary>Reading exported CSVs in Python</summary>

Use `encoding="utf-8-sig"` and `skiprows=1`:

```python
import pandas as pd
df = pd.read_csv("workouts_2026-04-13.csv", encoding="utf-8-sig", skiprows=1)
```

**Why these flags?** The file starts with a UTF-8 BOM so Excel detects the encoding correctly on Windows — `utf-8-sig` strips it (without this, the first column name would come through as `\ufeff<name>`). The first line is an Excel-only `sep=,` hint that tells Excel which delimiter to use regardless of the system's list separator; pandas would otherwise treat it as a data row, so `skiprows=1` discards it.

</details>

### Keyboard shortcuts

| Shortcut | Context | Action |
|----------|---------|--------|
| `Ctrl+S` / `Cmd+S` | Create / Edit views | Save the form |
| `E` | Detail views | Navigate to edit |

## For developers

### Tech stack

- **Backend:** Django 5, Python 3.11+
- **Frontend:** Pico CSS, vanilla JavaScript
- **Database:** SQLite (dev), PostgreSQL-ready
- **Tooling:** [uv](https://docs.astral.sh/uv/) (deps), Black (format), Pylint (lint)

### Getting started

```bash
# Install dependencies
uv sync

# Run migrations
uv run python manage.py migrate

# Start dev server
uv run python manage.py runserver
```

### Common commands

```bash
# Run all tests
uv run python manage.py test

# Format
uv run black .

# Lint
uv run pylint workouts/
```

### Rebuilding the database

Drop the database, recreate migrations, and rebuild:

```bash
uv run python manage.py rebuild_db
uv run python manage.py rebuild_db --create-test-data  # also generates test workouts
```

### Test data

Generate 3000 randomised workouts (1500 aerobic, 1000 strength, 500 generic) for a test user:

```bash
uv run python manage.py create_test_workouts
```

### SQL debugging

Log all SQL queries Django executes:

```bash
uv run python manage.py runserver --settings=phaserunner.settings.sql_debug
```

### Architecture

See [docs/schema_diagrams.md](docs/schema_diagrams.md) for visual database diagrams.

### Contributing

1. Fork the repo and create a feature branch from `main`.
2. Install dependencies: `uv sync`
3. Make your changes.
4. Format and lint:
   ```bash
   uv run black .
   uv run pylint workouts/
   ```
5. Run the test suite: `uv run python manage.py test`
6. Open a pull request against `main`.

### Issues

- [Issues tracker](https://github.com/andreas-thoren/phase-runner/issues) — bugs, feature requests, and planned work

## License

This project is licensed under the [MIT License](LICENSE).
