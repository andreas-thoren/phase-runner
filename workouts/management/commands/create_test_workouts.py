"""Management command to generate randomised test workouts for development."""

import random
from datetime import datetime, timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from workouts.enums import WorkoutStatus
from workouts.models import (
    Workout,
    WorkoutSubtype,
    AerobicDetails,
    StrengthDetails,
    GenericDetails,
)


class Command(BaseCommand):
    help = "Create test workouts for all workout types"

    def handle(self, *args: Any, **options: Any) -> None:
        self.create_test_workouts()

    def create_test_workouts(self) -> None:
        now = timezone.now()
        one_year_ago = now - timedelta(days=365)
        workout_statuses = list(WorkoutStatus)
        User = get_user_model()
        try:
            user = User.objects.get(username="test")
        except User.DoesNotExist:
            user = User.objects.create_user(
                username="test", email="test@example.com", password="password"
            )

        aerobic_subtypes = list(WorkoutSubtype.objects.filter(parent_type="aerobic"))
        strength_subtypes = list(WorkoutSubtype.objects.filter(parent_type="strength"))
        generic_subtypes = list(WorkoutSubtype.objects.filter(parent_type="generic"))

        aerobic_names = ["Morning Run", "Trail Run", "Cycling", "Swimming", "Easy Jog"]
        strength_names = ["Upper Body", "Leg Day", "Full Body", "Core Session"]
        generic_names = ["Yoga", "Stretching", "Recovery", "Walking"]

        for _ in range(1500):
            subtype = random.choice(aerobic_subtypes) if aerobic_subtypes else None
            gui_fields = self._random_gui_fields(subtype)
            workout = self._create_base_workout(
                user,
                random.choice(aerobic_names),
                workout_statuses,
                one_year_ago,
                now,
                workout_type="aerobic",
                subtype=subtype,
            )
            AerobicDetails.objects.create(
                workout=workout,
                duration=timedelta(minutes=random.randint(10, 120)),
                distance=random.randint(1000, 30000),
                load=random.choice([None, random.randint(1, 100)]),
                additional_data={"gui_fields": gui_fields} if gui_fields else {},
            )

        for _ in range(1000):
            subtype = random.choice(strength_subtypes) if strength_subtypes else None
            gui_fields = self._random_gui_fields(subtype)
            workout = self._create_base_workout(
                user,
                random.choice(strength_names),
                workout_statuses,
                one_year_ago,
                now,
                workout_type="strength",
                subtype=subtype,
            )
            StrengthDetails.objects.create(
                workout=workout,
                duration=timedelta(minutes=random.randint(30, 90)),
                num_sets=random.randint(5, 30),
                total_weight=random.randint(500, 5000),
                load=random.choice([None, random.randint(1, 100)]),
                additional_data={"gui_fields": gui_fields} if gui_fields else {},
            )

        for _ in range(500):
            subtype = random.choice(generic_subtypes) if generic_subtypes else None
            gui_fields = self._random_gui_fields(subtype)
            workout = self._create_base_workout(
                user,
                random.choice(generic_names),
                workout_statuses,
                one_year_ago,
                now,
                subtype=subtype,
            )
            GenericDetails.objects.create(
                workout=workout,
                duration=timedelta(minutes=random.randint(15, 90)),
                load=random.choice([None, random.randint(1, 100)]),
                additional_data={"gui_fields": gui_fields} if gui_fields else {},
            )

    @staticmethod
    def _random_gui_fields(subtype: WorkoutSubtype | None) -> dict:
        if not subtype or not subtype.gui_schema:
            return {}
        fields = {}
        for key, schema in subtype.gui_schema.items():
            if "pct" in key:
                fields[key] = random.randint(0, 100)
            elif key == "rpe":
                fields[key] = random.randint(1, 10)
            elif key == "avg_hr":
                fields[key] = random.randint(100, 180)
            elif key == "max_hr":
                fields[key] = random.randint(150, 200)
            elif key == "cadence":
                fields[key] = random.randint(60, 200)
            elif key == "laps":
                fields[key] = random.randint(10, 100)
            elif key == "pool_length_m":
                fields[key] = random.choice([25, 50])
            elif key == "elevation_m":
                fields[key] = random.randint(100, 2000)
            elif key == "avg_power":
                fields[key] = random.randint(100, 350)
            elif key == "exercises":
                fields[key] = random.randint(3, 12)
            elif schema.get("type") == "number":
                fields[key] = random.randint(1, 100)
        return fields

    def _create_base_workout(
        self,
        user: Any,
        name: str,
        statuses: list[str],
        start: datetime,
        end: datetime,
        workout_type: str = "generic",
        subtype: WorkoutSubtype | None = None,
    ) -> Workout:
        random_timestamp = random.uniform(start.timestamp(), end.timestamp())
        random_datetime = timezone.make_aware(
            timezone.datetime.fromtimestamp(random_timestamp),
            timezone.get_current_timezone(),
        )
        return Workout.objects.create(
            user=user,
            name=name,
            start_time=random_datetime,
            workout_status=random.choice(statuses),
            workout_type=workout_type,
            subtype=subtype,
        )
