"""Management command to drop the database, recreate migrations, and rebuild."""

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

import workouts


class Command(BaseCommand):
    help = "Drop DB, recreate migrations, and migrate."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--create-test-data",
            action="store_true",
            default=False,
            help="Also run create_test_workouts after migrating.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        db_path = Path(settings.DATABASES["default"]["NAME"])
        migrations_dir = Path(workouts.__file__).parent / "migrations"

        # 1. Delete database
        if db_path.exists():
            db_path.unlink()
            self.stdout.write(f"Deleted {db_path}")
        else:
            self.stdout.write("No database file found, skipping.")

        # 2. Delete migration files (keep __init__.py)
        for f in migrations_dir.glob("*.py"):
            if f.name != "__init__.py":
                f.unlink()
                self.stdout.write(f"Deleted migration {f.name}")

        # 3. Create fresh migrations
        self.stdout.write("Running makemigrations...")
        call_command("makemigrations", "workouts")

        # 4. Migrate
        self.stdout.write("Running migrate...")
        call_command("migrate")

        # 5. Optionally create test data
        if options["create_test_data"]:
            self.stdout.write("Creating test data...")
            call_command("create_test_workouts")

        self.stdout.write(self.style.SUCCESS("Done."))
