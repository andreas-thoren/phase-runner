# PhaseRunner

A Django web app for tracking workouts and planning training periodization.

**Live at [phaserunner.app](https://phaserunner.app)** — currently invite-only. Contact [@andreas-thoren](https://github.com/andreas-thoren) to request access.

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

### Rebuilding the Database

Drop the database, recreate migrations, and rebuild:

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

- [Issues](https://github.com/andreas-thoren/phase-runner/issues) — bugs, feature requests, and planned work

## License

This project is licensed under the [MIT License](LICENSE).
