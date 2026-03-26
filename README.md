# PhaseRunner

A Django web app for tracking workouts and planning training periodization.

Log workouts across three types — **aerobic**, **strength**, and **generic** — each with a mandatory activity (e.g. Running, Cycling, Swimming) that provides flexible, schema-driven fields. Plan training blocks with a macrocycle → mesocycle → microcycle hierarchy, and compare planned goals against actual results in a summary view.

## Tech Stack

- **Backend:** Django 5, Python 3.11+
- **Frontend:** Pico CSS, vanilla JavaScript
- **Database:** SQLite (dev), PostgreSQL-ready
- **Tooling:** [uv](https://docs.astral.sh/uv/) (deps), Black (format), Pylint (lint)

## Getting Started

```bash
# Install dependencies
uv sync

# Run migrations
uv run python manage.py migrate

# Load initial fixture data (activity types and subtypes)
uv run python manage.py loaddata workouts/fixtures/initial_data.json

# Start dev server
uv run python manage.py runserver
```

## Development

### Common Commands

```bash
# Run all tests
uv run python manage.py test

# Format
uv run black .

# Lint
uv run pylint workouts/
```

### Fixtures

Load predefined lookup data (workout subtypes and their GUI schemas):

```bash
uv run python manage.py loaddata workouts/fixtures/initial_data.json
```

After modifying lookup tables, dump only the subtype model:

```bash
uv run python manage.py dumpdata workouts.workoutsubtype --indent 2 --natural-foreign --natural-primary > workouts/fixtures/initial_data.json
```

### Rebuilding the Database

Drop the database, recreate migrations, and reload fixtures:

```bash
uv run python manage.py rebuild_db
uv run python manage.py rebuild_db --create-test-data  # also generates test workouts
```

### Test Data

Generate 3000 randomised workouts (1500 aerobic, 1000 strength, 500 generic) for a test user:

```bash
uv run python manage.py create_test_workouts
```

### SQL Debugging

Log all SQL queries Django executes:

```bash
uv run python manage.py runserver --settings=phaserunner.settings.sql_debug
```

### Keyboard Shortcuts

| Shortcut | Context | Action |
|----------|---------|--------|
| `Ctrl+S` / `Cmd+S` | Create / Edit views | Save the form |
| `E` | Detail views | Navigate to edit |

## Architecture

See [docs/schema_diagrams.md](docs/schema_diagrams.md) for visual database diagrams.

## Contributing

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

## Dev

- [TODO](docs/TODO.md) — possible future features

## License

This project is licensed under the [MIT License](LICENSE).
