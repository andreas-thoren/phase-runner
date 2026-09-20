from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from workouts.enums import SUBTYPE_TYPE_MAP, WorkoutStatus, WorkoutSubtype, WorkoutType
from workouts.tests.helpers import read_ordering
from workouts.utils import (
    StaleOrderingError,
    apply_cycle_order,
    create_default_cycles,
    parse_ordering,
)
from workouts.models import (
    WEEKLY_UPLOAD_CAP,
    ActiveMacrocycle,
    Workout,
    AerobicDetails,
    StrengthDetails,
    GenericDetails,
    DetailBase,
    Macrocycle,
    Mesocycle,
    Microcycle,
)

User = get_user_model()


class UserModelTest(TestCase):
    def test_create_without_email_rejected(self):
        with self.assertRaises(IntegrityError):
            User.objects.create_user(username="nomail", password="testpass")

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            username="user1", email="same@example.com", password="testpass"
        )
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username="user2", email="same@example.com", password="testpass"
            )


class WeeklyUploadCapTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="capuser", email="cap@example.com", password="testpass"
        )

    def test_fresh_user(self):
        remaining = self.user.get_weekly_upload_remaining()
        self.assertEqual(remaining, WEEKLY_UPLOAD_CAP)
        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        self.assertEqual(self.user.weekly_upload_reset, this_monday)

    def test_new_week_resets(self):
        today = date.today()
        last_monday = today - timedelta(days=today.weekday()) - timedelta(days=7)
        self.user.weekly_upload_count = 3000
        self.user.weekly_upload_reset = last_monday
        self.user.save()
        remaining = self.user.get_weekly_upload_remaining()
        self.assertEqual(remaining, WEEKLY_UPLOAD_CAP)
        self.assertEqual(self.user.weekly_upload_count, 0)

    def test_active_window(self):
        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        self.user.weekly_upload_count = 1000
        self.user.weekly_upload_reset = this_monday
        self.user.save()
        remaining = self.user.get_weekly_upload_remaining()
        self.assertEqual(remaining, WEEKLY_UPLOAD_CAP - 1000)


class WorkoutModelTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )
        self.workout = Workout.objects.create(
            user=self.user,
            name="Morning Run",
            workout_status=WorkoutStatus.COMPLETED,
            subtype=WorkoutSubtype.RUNNING,
        )
        self.aerobic_details = AerobicDetails.objects.create(
            workout=self.workout,
            duration=timedelta(minutes=30),
        )

    def test_duration_validation(self):
        with self.assertRaises(ValidationError):
            self.aerobic_details.duration = timedelta(seconds=-10)
            self.aerobic_details.save()

    def test_get_detail_aerobic(self):
        detail = self.workout.get_detail()
        self.assertIsNotNone(detail)
        self.assertIsInstance(detail, AerobicDetails)

    def test_get_detail_strength(self):
        workout = Workout.objects.create(
            user=self.user,
            name="Leg Day",
            subtype=WorkoutSubtype.STRENGTH,
        )
        StrengthDetails.objects.create(workout=workout, num_sets=5, total_weight=1000)
        detail = workout.get_detail()
        self.assertIsInstance(detail, StrengthDetails)
        self.assertEqual(detail.num_sets, 5)

    def test_get_detail_generic(self):
        workout = Workout.objects.create(
            user=self.user,
            name="Yoga",
            subtype=WorkoutSubtype.MOBILITY,
        )
        GenericDetails.objects.create(
            workout=workout,
            duration=timedelta(minutes=60),
            additional_data={"activity": "outdoor"},
        )
        detail = workout.get_detail()
        self.assertIsInstance(detail, GenericDetails)
        self.assertEqual(detail.additional_data["activity"], "outdoor")

    def test_workout_without_detail_record(self):
        workout = Workout.objects.create(
            user=self.user,
            name="No detail",
            subtype=WorkoutSubtype.MOBILITY,
        )
        self.assertIsNone(workout.get_detail())

    def test_speed_property(self):
        self.aerobic_details.distance = 10000
        self.aerobic_details.duration = timedelta(hours=1)
        self.aerobic_details.save()
        self.assertAlmostEqual(self.aerobic_details.speed, 10.0)

    def test_speed_property_no_distance(self):
        self.aerobic_details.distance = None
        self.assertIsNone(self.aerobic_details.speed)

    def test_distance_km_property(self):
        self.aerobic_details.distance = 42195
        self.assertAlmostEqual(self.aerobic_details.distance_km, 42.195)

    def test_distance_km_none(self):
        self.aerobic_details.distance = None
        self.assertIsNone(self.aerobic_details.distance_km)

    def test_workout_type_mismatch_raises(self):
        workout = Workout.objects.create(
            user=self.user,
            name="Generic",
            subtype=WorkoutSubtype.MOBILITY,
        )
        with self.assertRaises(ValidationError):
            AerobicDetails.objects.create(
                workout=workout, duration=timedelta(minutes=10)
            )

    def test_detail_registry_contains_all_types(self):
        self.assertIn("aerobic", DetailBase._detail_registry)
        self.assertIn("strength", DetailBase._detail_registry)
        self.assertIn("generic", DetailBase._detail_registry)

    def test_workout_type_property(self):
        self.assertEqual(self.workout.workout_type, WorkoutType.AEROBIC)
        strength = Workout.objects.create(
            user=self.user, name="Lift", subtype=WorkoutSubtype.STRENGTH
        )
        self.assertEqual(strength.workout_type, WorkoutType.STRENGTH)

    def test_gui_fields_property(self):
        workout = Workout.objects.create(
            user=self.user,
            name="With GUI",
            subtype=WorkoutSubtype.MOBILITY,
        )
        GenericDetails.objects.create(
            workout=workout,
            additional_data={"gui_fields": {"rpe": 7}},
        )
        self.assertEqual(workout.gui_fields, {"rpe": 7})

    def test_gui_fields_empty_when_no_detail(self):
        workout = Workout.objects.create(
            user=self.user,
            name="No detail",
            subtype=WorkoutSubtype.MOBILITY,
        )
        self.assertEqual(workout.gui_fields, {})


class WorkoutSubtypeEnumTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )

    def test_subtype_type_mapping(self):
        self.assertEqual(WorkoutSubtype.RUNNING.workout_type, WorkoutType.AEROBIC)
        self.assertEqual(WorkoutSubtype.STRENGTH.workout_type, WorkoutType.STRENGTH)
        self.assertEqual(WorkoutSubtype.MOBILITY.workout_type, WorkoutType.GENERIC)

    def test_subtype_label(self):
        self.assertEqual(WorkoutSubtype.RUNNING.label, "Running")
        self.assertEqual(WorkoutSubtype.CYCLING.label, "Cycling")

    def test_subtype_gui_schema(self):
        schema = WorkoutSubtype.RUNNING.gui_schema
        self.assertIn("avg_hr", schema)
        self.assertIn("rpe", schema)

    def test_all_subtypes_have_mapping(self):
        for st in WorkoutSubtype:
            self.assertIn(st, SUBTYPE_TYPE_MAP)

    def test_workout_without_subtype_raises(self):
        workout = Workout(user=self.user, name="Test")
        with self.assertRaises(ValidationError):
            workout.full_clean()

    def test_load_garmin_in_gui_fields(self):
        workout = Workout.objects.create(
            user=self.user, name="Test", subtype=WorkoutSubtype.MOBILITY
        )
        detail = GenericDetails.objects.create(
            workout=workout,
            additional_data={"gui_fields": {"load_garmin": 75}},
        )
        detail.refresh_from_db()
        self.assertEqual(detail.additional_data["gui_fields"]["load_garmin"], 75)

    def test_gui_fields_subset_of_schema_is_valid(self):
        workout = Workout.objects.create(
            user=self.user, name="Run", subtype=WorkoutSubtype.RUNNING
        )
        AerobicDetails.objects.create(
            workout=workout,
            additional_data={"gui_fields": {"rpe": 7}},
        )

    def test_gui_fields_unknown_key_raises(self):
        workout = Workout.objects.create(
            user=self.user, name="Run", subtype=WorkoutSubtype.RUNNING
        )
        with self.assertRaises(ValidationError):
            AerobicDetails.objects.create(
                workout=workout,
                additional_data={"gui_fields": {"rpe": 7, "bogus": 99}},
            )

    def test_gui_fields_empty_is_valid(self):
        workout = Workout.objects.create(
            user=self.user, name="Run", subtype=WorkoutSubtype.RUNNING
        )
        AerobicDetails.objects.create(workout=workout)


class MacrocycleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_create_macrocycle(self):
        macro = Macrocycle.objects.create(
            user=self.user,
            name="Marathon Prep",
            start_date=date(2026, 1, 1),
        )
        self.assertEqual(str(macro), "Marathon Prep")

    def test_end_date_requires_hydration(self):
        macro = Macrocycle.objects.create(
            user=self.user, name="Plan", start_date=date(2026, 1, 1)
        )
        with self.assertRaises(AttributeError):
            _ = macro.end_date

    def test_scheduled_duration_requires_hydration(self):
        macro = Macrocycle.objects.create(
            user=self.user, name="Plan", start_date=date(2026, 1, 1)
        )
        with self.assertRaises(AttributeError):
            _ = macro.scheduled_duration


class MesocycleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def setUp(self):
        self.macro = Macrocycle.objects.create(
            user=self.user, name="Season", start_date=date(2026, 1, 1)
        )

    def test_create_mesocycle(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        self.assertIn("Base", str(meso))

    def test_auto_order(self):
        m1 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        m2 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        self.assertEqual(m1.order, 1)
        self.assertEqual(m2.order, 2)

    def test_cascade_delete(self):
        Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        self.macro.delete()
        self.assertEqual(Mesocycle.objects.count(), 0)

    def test_start_date_requires_hydration(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        with self.assertRaises(AttributeError):
            _ = meso.start_date

    def test_end_date_requires_hydration(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        with self.assertRaises(AttributeError):
            _ = meso.end_date

    def test_duration_days_requires_hydration(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        with self.assertRaises(AttributeError):
            _ = meso.duration_days

    def test_unique_order_constraint(self):
        m1 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        with self.assertRaises(IntegrityError):
            Mesocycle.objects.create(
                macrocycle=self.macro, meso_type="build", order=m1.order
            )

    def test_queryset_ordering(self):
        m1 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        m2 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        m3 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="peak")
        ordered = list(Mesocycle.objects.filter(macrocycle=self.macro))
        self.assertEqual([m.pk for m in ordered], [m1.pk, m2.pk, m3.pk])


class MicrocycleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def setUp(self):
        self.macro = Macrocycle.objects.create(
            user=self.user, name="Season", start_date=date(2026, 1, 1)
        )
        self.meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")

    def test_create_with_goals(self):
        micro = Microcycle.objects.create(
            mesocycle=self.meso,
            planned_sessions=4,
            planned_distance=40000,
            planned_long_distance=18000,
        )
        self.assertEqual(micro.planned_sessions, 4)

    def test_auto_order(self):
        m1 = Microcycle.objects.create(mesocycle=self.meso)
        m2 = Microcycle.objects.create(mesocycle=self.meso)
        self.assertEqual(m1.order, 1)
        self.assertEqual(m2.order, 2)

    def test_macrocycle_property(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        self.assertEqual(micro.macrocycle, self.macro)

    def test_start_date_requires_hydration(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        with self.assertRaises(AttributeError):
            _ = micro.start_date

    def test_end_date_requires_hydration(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        with self.assertRaises(AttributeError):
            _ = micro.end_date

    def test_unique_order_constraint(self):
        m1 = Microcycle.objects.create(mesocycle=self.meso)
        with self.assertRaises(IntegrityError):
            Microcycle.objects.create(mesocycle=self.meso, order=m1.order)

    def test_queryset_ordering(self):
        m1 = Microcycle.objects.create(mesocycle=self.meso)
        m2 = Microcycle.objects.create(mesocycle=self.meso)
        m3 = Microcycle.objects.create(mesocycle=self.meso)
        ordered = list(Microcycle.objects.filter(mesocycle=self.meso))
        self.assertEqual([m.pk for m in ordered], [m1.pk, m2.pk, m3.pk])

    def test_cascade_delete_from_mesocycle(self):
        Microcycle.objects.create(mesocycle=self.meso)
        self.meso.delete()
        self.assertEqual(Microcycle.objects.count(), 0)

    def test_cascade_delete_from_macrocycle(self):
        Microcycle.objects.create(mesocycle=self.meso)
        self.macro.delete()
        self.assertEqual(Microcycle.objects.count(), 0)
        self.assertEqual(Mesocycle.objects.count(), 0)

    def test_micro_type_defaults_to_load(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        self.assertEqual(micro.micro_type, "load")

    def test_micro_type_can_be_set(self):
        micro = Microcycle.objects.create(mesocycle=self.meso, micro_type="deload")
        self.assertEqual(micro.micro_type, "deload")


class HydrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def setUp(self):
        self.macro = Macrocycle.objects.create(
            user=self.user, name="Plan", start_date=date(2026, 1, 1)
        )
        self.meso1 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        self.meso2 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        # meso1: two 7-day microcycles (14 days total)
        Microcycle.objects.create(mesocycle=self.meso1, duration_days=7)
        Microcycle.objects.create(mesocycle=self.meso1, duration_days=7)
        # meso2: one 10-day microcycle
        Microcycle.objects.create(mesocycle=self.meso2, duration_days=10)

    def test_hydrate_macrocycle_dates(self):
        macro = self.macro.hydrate()
        self.assertEqual(macro.scheduled_duration, 24)
        # 24 days: Jan 1 + 23 = Jan 24
        self.assertEqual(macro.end_date, date(2026, 1, 24))

    def test_hydrate_mesocycle_dates(self):
        macro = self.macro.hydrate()
        meso1, meso2 = macro.hydrated_mesocycles
        self.assertEqual(meso1.start_date, date(2026, 1, 1))
        self.assertEqual(meso1.end_date, date(2026, 1, 14))
        self.assertEqual(meso2.start_date, date(2026, 1, 15))
        self.assertEqual(meso2.end_date, date(2026, 1, 24))

    def test_hydrate_microcycle_dates(self):
        macro = self.macro.hydrate()
        micros = macro.hydrated_mesocycles[0].hydrated_microcycles
        self.assertEqual(micros[0].start_date, date(2026, 1, 1))
        self.assertEqual(micros[0].end_date, date(2026, 1, 7))
        self.assertEqual(micros[1].start_date, date(2026, 1, 8))
        self.assertEqual(micros[1].end_date, date(2026, 1, 14))

    def test_hydrate_mesocycle_duration_days(self):
        macro = self.macro.hydrate()
        meso1, meso2 = macro.hydrated_mesocycles
        self.assertEqual(meso1.duration_days, 14)
        self.assertEqual(meso2.duration_days, 10)

    def test_hydrate_returns_self(self):
        macro = self.macro.hydrate()
        self.assertIs(macro, self.macro)

    def test_hydrate_empty_macrocycle(self):
        empty = Macrocycle.objects.create(
            user=self.user, name="Empty", start_date=date(2026, 6, 1)
        )
        macro = empty.hydrate()
        self.assertEqual(macro.scheduled_duration, 0)
        self.assertEqual(macro.end_date, date(2026, 6, 1))

    def test_hydrate_meso_with_no_microcycles(self):
        macro = Macrocycle.objects.create(
            user=self.user, name="Sparse", start_date=date(2026, 3, 1)
        )
        Mesocycle.objects.create(macrocycle=macro, meso_type="recovery")
        macro.hydrate()
        meso = macro.hydrated_mesocycles[0]
        self.assertEqual(meso.duration_days, 0)
        self.assertEqual(meso.start_date, date(2026, 3, 1))
        self.assertEqual(meso.end_date, date(2026, 3, 1))


class OrderMixinTest(TestCase):
    """Tests for gap-free ordering on delete."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def setUp(self):
        self.macro = Macrocycle.objects.create(
            user=self.user, name="Season", start_date=date(2026, 1, 1)
        )
        self.meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")

    def test_delete_middle_mesocycle_closes_gap(self):
        m1 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        m2 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="peak")
        m3 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="sharpen")
        # self.meso=order 1, m1=2, m2=3, m3=4
        m1.delete()
        m2.refresh_from_db()
        m3.refresh_from_db()
        self.assertEqual(m2.order, 2)
        self.assertEqual(m3.order, 3)

    def test_delete_first_mesocycle_closes_gap(self):
        m2 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        m3 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="peak")
        # self.meso=1, m2=2, m3=3
        self.meso.delete()
        m2.refresh_from_db()
        m3.refresh_from_db()
        self.assertEqual(m2.order, 1)
        self.assertEqual(m3.order, 2)

    def test_delete_last_mesocycle_no_change(self):
        m2 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        # self.meso=1, m2=2
        m2.delete()
        self.meso.refresh_from_db()
        self.assertEqual(self.meso.order, 1)

    def test_delete_middle_microcycle_closes_gap(self):
        mic1 = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        mic2 = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        mic3 = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        # mic1=1, mic2=2, mic3=3
        mic2.delete()
        mic1.refresh_from_db()
        mic3.refresh_from_db()
        self.assertEqual(mic1.order, 1)
        self.assertEqual(mic3.order, 2)

    def test_delete_first_microcycle_closes_gap(self):
        mic1 = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        mic2 = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        mic3 = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        mic1.delete()
        mic2.refresh_from_db()
        mic3.refresh_from_db()
        self.assertEqual(mic2.order, 1)
        self.assertEqual(mic3.order, 2)

    def test_delete_does_not_affect_other_parent(self):
        meso2 = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        mic_a1 = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        mic_a2 = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        mic_b1 = Microcycle.objects.create(mesocycle=meso2, duration_days=7)
        mic_b2 = Microcycle.objects.create(mesocycle=meso2, duration_days=7)
        mic_a1.delete()
        mic_a2.refresh_from_db()
        mic_b1.refresh_from_db()
        mic_b2.refresh_from_db()
        self.assertEqual(mic_a2.order, 1)
        self.assertEqual(mic_b1.order, 1)
        self.assertEqual(mic_b2.order, 2)


class ReorderTestMixin:
    """Builds a three-mesocycle plan and provides ordering assertions.

    Layout (durations in days):
        A "base"    a1(7)  a2(7)  a3(5)
        B "build"   b1(7)  b2(7)
        C "peak"    c1(7)
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="reorderuser", email="reorder@example.com", password="testpass"
        )

    def setUp(self):
        super().setUp()
        self.macro = Macrocycle.objects.create(
            user=self.user, name="Season", start_date=date(2026, 1, 5)
        )
        self.meso_a = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        self.meso_b = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        self.meso_c = Mesocycle.objects.create(macrocycle=self.macro, meso_type="peak")
        self.a1 = Microcycle.objects.create(mesocycle=self.meso_a, duration_days=7)
        self.a2 = Microcycle.objects.create(mesocycle=self.meso_a, duration_days=7)
        self.a3 = Microcycle.objects.create(mesocycle=self.meso_a, duration_days=5)
        self.b1 = Microcycle.objects.create(mesocycle=self.meso_b, duration_days=7)
        self.b2 = Microcycle.objects.create(mesocycle=self.meso_b, duration_days=7)
        self.c1 = Microcycle.objects.create(mesocycle=self.meso_c, duration_days=7)

    # -- helpers ---------------------------------------------------------

    def ordering(self, *specs):
        """Build a payload from (mesocycle, [microcycles]) pairs."""
        return [
            {"pk": meso.pk, "micros": [micro.pk for micro in micros]}
            for meso, micros in specs
        ]

    def current(self):
        """Read the stored ordering back as [(meso_pk, [micro_pk, ...]), ...]."""
        return read_ordering(self.macro)

    def expected(self, *specs):
        return [(meso.pk, [micro.pk for micro in micros]) for meso, micros in specs]

    def assertGapFree(self):
        """Every sibling group must be numbered exactly 1..N with no gaps."""
        meso_orders = list(
            Mesocycle.objects.filter(macrocycle=self.macro)
            .order_by("order")
            .values_list("order", flat=True)
        )
        self.assertEqual(meso_orders, list(range(1, len(meso_orders) + 1)))
        for meso in Mesocycle.objects.filter(macrocycle=self.macro):
            micro_orders = list(
                Microcycle.objects.filter(mesocycle=meso)
                .order_by("order")
                .values_list("order", flat=True)
            )
            self.assertEqual(micro_orders, list(range(1, len(micro_orders) + 1)))

    def apply(self, *specs):
        apply_cycle_order(self.macro, self.ordering(*specs))
        self.assertGapFree()


class ApplyCycleOrderMicroTest(ReorderTestMixin, TestCase):
    """Microcycle moves: within a mesocycle and across mesocycles."""

    def test_noop_ordering_changes_nothing(self):
        before = self.current()
        self.apply(
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(self.current(), before)

    def test_move_first_to_last_within_mesocycle(self):
        self.apply(
            (self.meso_a, [self.a2, self.a3, self.a1]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(
            self.current(),
            self.expected(
                (self.meso_a, [self.a2, self.a3, self.a1]),
                (self.meso_b, [self.b1, self.b2]),
                (self.meso_c, [self.c1]),
            ),
        )

    def test_move_last_to_first_within_mesocycle(self):
        self.apply(
            (self.meso_a, [self.a3, self.a1, self.a2]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(
            self.current()[0], (self.meso_a.pk, [self.a3.pk, self.a1.pk, self.a2.pk])
        )

    def test_move_middle_to_first_within_mesocycle(self):
        self.apply(
            (self.meso_a, [self.a2, self.a1, self.a3]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(
            self.current()[0], (self.meso_a.pk, [self.a2.pk, self.a1.pk, self.a3.pk])
        )

    def test_swap_adjacent_microcycles(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, [self.b2, self.b1]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(self.current()[1], (self.meso_b.pk, [self.b2.pk, self.b1.pk]))

    def test_full_reversal_within_mesocycle(self):
        """The case most likely to expose a transient unique-constraint collision."""
        self.apply(
            (self.meso_a, [self.a3, self.a2, self.a1]),
            (self.meso_b, [self.b2, self.b1]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(
            self.current(),
            self.expected(
                (self.meso_a, [self.a3, self.a2, self.a1]),
                (self.meso_b, [self.b2, self.b1]),
                (self.meso_c, [self.c1]),
            ),
        )

    def test_move_microcycle_to_another_mesocycle_at_end(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2]),
            (self.meso_b, [self.b1, self.b2, self.a3]),
            (self.meso_c, [self.c1]),
        )
        self.a3.refresh_from_db()
        self.assertEqual(self.a3.mesocycle_id, self.meso_b.pk)
        self.assertEqual(self.a3.order, 3)

    def test_move_microcycle_to_another_mesocycle_at_front(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2]),
            (self.meso_b, [self.a3, self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.a3.refresh_from_db()
        self.b1.refresh_from_db()
        self.assertEqual(self.a3.mesocycle_id, self.meso_b.pk)
        self.assertEqual(self.a3.order, 1)
        self.assertEqual(self.b1.order, 2)

    def test_move_microcycle_into_middle_of_another_mesocycle(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2]),
            (self.meso_b, [self.b1, self.a3, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(
            self.current()[1], (self.meso_b.pk, [self.b1.pk, self.a3.pk, self.b2.pk])
        )

    def test_emptying_a_mesocycle_is_allowed(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, []),
            (self.meso_c, [self.b1, self.b2, self.c1]),
        )
        self.assertEqual(Microcycle.objects.filter(mesocycle=self.meso_b).count(), 0)
        self.assertTrue(Mesocycle.objects.filter(pk=self.meso_b.pk).exists())

    def test_emptied_mesocycle_hydrates_as_zero_length(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, []),
            (self.meso_c, [self.b1, self.b2, self.c1]),
        )
        macro = Macrocycle.objects.get(pk=self.macro.pk).hydrate()
        empty = macro.hydrated_mesocycles[1]
        self.assertEqual(empty.duration_days, 0)
        self.assertEqual(empty.start_date, empty.end_date)

    def test_refilling_an_emptied_mesocycle(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, []),
            (self.meso_c, [self.b1, self.b2, self.c1]),
        )
        self.apply(
            (self.meso_a, [self.a1]),
            (self.meso_b, [self.a2, self.a3]),
            (self.meso_c, [self.b1, self.b2, self.c1]),
        )
        self.assertEqual(self.current()[1], (self.meso_b.pk, [self.a2.pk, self.a3.pk]))

    def test_swap_entire_microcycle_sets_between_mesocycles(self):
        self.apply(
            (self.meso_a, [self.b1, self.b2]),
            (self.meso_b, [self.a1, self.a2, self.a3]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(
            self.current(),
            self.expected(
                (self.meso_a, [self.b1, self.b2]),
                (self.meso_b, [self.a1, self.a2, self.a3]),
                (self.meso_c, [self.c1]),
            ),
        )

    def test_rotate_microcycles_across_all_mesocycles(self):
        self.apply(
            (self.meso_a, [self.c1, self.a1]),
            (self.meso_b, [self.a2, self.a3]),
            (self.meso_c, [self.b1, self.b2]),
        )
        self.assertEqual(
            self.current(),
            self.expected(
                (self.meso_a, [self.c1, self.a1]),
                (self.meso_b, [self.a2, self.a3]),
                (self.meso_c, [self.b1, self.b2]),
            ),
        )

    def test_move_out_and_back_restores_original(self):
        before = self.current()
        self.apply(
            (self.meso_a, [self.a1, self.a2]),
            (self.meso_b, [self.a3, self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.apply(
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.assertEqual(self.current(), before)

    def test_consolidate_every_microcycle_into_one_mesocycle(self):
        self.apply(
            (self.meso_a, []),
            (self.meso_b, []),
            (
                self.meso_c,
                [self.a1, self.a2, self.a3, self.b1, self.b2, self.c1],
            ),
        )
        self.assertEqual(Microcycle.objects.filter(mesocycle=self.meso_c).count(), 6)
        self.assertEqual(
            Microcycle.objects.filter(mesocycle=self.meso_c)
            .order_by("order")
            .values_list("order", flat=True)[0],
            1,
        )

    def test_applying_twice_is_idempotent(self):
        specs = (
            (self.meso_a, [self.a3, self.a1]),
            (self.meso_b, [self.b2, self.a2]),
            (self.meso_c, [self.c1, self.b1]),
        )
        self.apply(*specs)
        first = self.current()
        self.apply(*specs)
        self.assertEqual(self.current(), first)


class ApplyCycleOrderMesoTest(ReorderTestMixin, TestCase):
    """Mesocycle reordering."""

    def test_swap_adjacent_mesocycles(self):
        self.apply(
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_c, [self.c1]),
        )
        self.meso_a.refresh_from_db()
        self.meso_b.refresh_from_db()
        self.assertEqual(self.meso_b.order, 1)
        self.assertEqual(self.meso_a.order, 2)

    def test_move_first_mesocycle_to_last(self):
        self.apply(
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
            (self.meso_a, [self.a1, self.a2, self.a3]),
        )
        self.assertEqual(
            [meso_pk for meso_pk, _ in self.current()],
            [self.meso_b.pk, self.meso_c.pk, self.meso_a.pk],
        )

    def test_move_last_mesocycle_to_first(self):
        self.apply(
            (self.meso_c, [self.c1]),
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, [self.b1, self.b2]),
        )
        self.assertEqual(
            [meso_pk for meso_pk, _ in self.current()],
            [self.meso_c.pk, self.meso_a.pk, self.meso_b.pk],
        )

    def test_full_mesocycle_reversal(self):
        self.apply(
            (self.meso_c, [self.c1]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_a, [self.a1, self.a2, self.a3]),
        )
        self.assertEqual(
            [meso_pk for meso_pk, _ in self.current()],
            [self.meso_c.pk, self.meso_b.pk, self.meso_a.pk],
        )

    def test_mesocycle_reorder_preserves_microcycle_order(self):
        self.apply(
            (self.meso_c, [self.c1]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_a, [self.a1, self.a2, self.a3]),
        )
        self.assertEqual(
            self.current()[2], (self.meso_a.pk, [self.a1.pk, self.a2.pk, self.a3.pk])
        )

    def test_reorder_mesocycles_and_microcycles_together(self):
        self.apply(
            (self.meso_c, [self.c1, self.a1]),
            (self.meso_a, [self.a3, self.a2]),
            (self.meso_b, [self.b2, self.b1]),
        )
        self.assertEqual(
            self.current(),
            self.expected(
                (self.meso_c, [self.c1, self.a1]),
                (self.meso_a, [self.a3, self.a2]),
                (self.meso_b, [self.b2, self.b1]),
            ),
        )


class ApplyCycleOrderDateTest(ReorderTestMixin, TestCase):
    """Reordering changes internal boundaries but never total plan length."""

    def hydrated(self):
        return Macrocycle.objects.get(pk=self.macro.pk).hydrate()

    def test_baseline_dates(self):
        macro = self.hydrated()
        self.assertEqual(macro.scheduled_duration, 40)
        self.assertEqual(macro.end_date, date(2026, 2, 13))
        # A = 7+7+5 = 19 days, B = 14, C = 7.
        self.assertEqual(macro.hydrated_mesocycles[0].start_date, date(2026, 1, 5))
        self.assertEqual(macro.hydrated_mesocycles[1].start_date, date(2026, 1, 24))
        self.assertEqual(macro.hydrated_mesocycles[2].start_date, date(2026, 2, 7))

    def test_total_duration_unchanged_by_microcycle_move(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2]),
            (self.meso_b, [self.a3, self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        macro = self.hydrated()
        self.assertEqual(macro.scheduled_duration, 40)
        self.assertEqual(macro.end_date, date(2026, 2, 13))

    def test_total_duration_unchanged_by_mesocycle_move(self):
        self.apply(
            (self.meso_c, [self.c1]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_a, [self.a1, self.a2, self.a3]),
        )
        macro = self.hydrated()
        self.assertEqual(macro.scheduled_duration, 40)
        self.assertEqual(macro.end_date, date(2026, 2, 13))

    def test_moving_short_microcycle_earlier_shifts_downstream_starts(self):
        # a3 is 5 days; putting it first makes a1 start 5 days in, not 7.
        self.apply(
            (self.meso_a, [self.a3, self.a1, self.a2]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        macro = self.hydrated()
        micros = macro.hydrated_mesocycles[0].hydrated_microcycles
        self.assertEqual(micros[0].start_date, date(2026, 1, 5))
        self.assertEqual(micros[1].start_date, date(2026, 1, 10))
        self.assertEqual(micros[2].start_date, date(2026, 1, 17))

    def test_mesocycle_durations_follow_their_microcycles(self):
        self.apply(
            (self.meso_a, [self.a1, self.a2]),
            (self.meso_b, [self.a3, self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        macro = self.hydrated()
        self.assertEqual(macro.hydrated_mesocycles[0].duration_days, 14)
        self.assertEqual(macro.hydrated_mesocycles[1].duration_days, 19)
        self.assertEqual(macro.hydrated_mesocycles[2].duration_days, 7)

    def test_mesocycle_reversal_reorders_start_dates(self):
        self.apply(
            (self.meso_c, [self.c1]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_a, [self.a1, self.a2, self.a3]),
        )
        macro = self.hydrated()
        starts = [meso.start_date for meso in macro.hydrated_mesocycles]
        self.assertEqual(
            starts, [date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 26)]
        )


class ApplyCycleOrderValidationTest(ReorderTestMixin, TestCase):
    """Set-equality validation: the guard against stale tabs and foreign pks."""

    def assertRejected(self, ordering):
        before = self.current()
        with self.assertRaises(StaleOrderingError):
            apply_cycle_order(self.macro, ordering)
        self.assertEqual(self.current(), before)

    def test_missing_mesocycle_rejected(self):
        self.assertRejected(
            self.ordering(
                (self.meso_a, [self.a1, self.a2, self.a3]),
                (self.meso_b, [self.b1, self.b2, self.c1]),
            )
        )

    def test_duplicate_mesocycle_rejected(self):
        self.assertRejected(
            self.ordering(
                (self.meso_a, [self.a1, self.a2, self.a3]),
                (self.meso_a, []),
                (self.meso_b, [self.b1, self.b2]),
                (self.meso_c, [self.c1]),
            )
        )

    def test_foreign_mesocycle_rejected(self):
        other_macro = Macrocycle.objects.create(
            user=self.user, name="Other", start_date=date(2026, 6, 1)
        )
        other_meso = Mesocycle.objects.create(macrocycle=other_macro, meso_type="base")
        self.assertRejected(
            self.ordering(
                (self.meso_a, [self.a1, self.a2, self.a3]),
                (self.meso_b, [self.b1, self.b2]),
                (self.meso_c, [self.c1]),
                (other_meso, []),
            )
        )

    def test_missing_microcycle_rejected(self):
        self.assertRejected(
            self.ordering(
                (self.meso_a, [self.a1, self.a2]),
                (self.meso_b, [self.b1, self.b2]),
                (self.meso_c, [self.c1]),
            )
        )

    def test_duplicate_microcycle_rejected(self):
        self.assertRejected(
            self.ordering(
                (self.meso_a, [self.a1, self.a2, self.a3]),
                (self.meso_b, [self.b1, self.b2, self.a1]),
                (self.meso_c, [self.c1]),
            )
        )

    def test_microcycle_from_another_macrocycle_rejected(self):
        other_macro = Macrocycle.objects.create(
            user=self.user, name="Other", start_date=date(2026, 6, 1)
        )
        other_meso = Mesocycle.objects.create(macrocycle=other_macro, meso_type="base")
        foreign_micro = Microcycle.objects.create(mesocycle=other_meso, duration_days=7)
        self.assertRejected(
            self.ordering(
                (self.meso_a, [self.a1, self.a2, self.a3, foreign_micro]),
                (self.meso_b, [self.b1, self.b2]),
                (self.meso_c, [self.c1]),
            )
        )

    def test_microcycle_from_another_user_rejected(self):
        other_user = get_user_model().objects.create_user(
            username="intruder", email="intruder@example.com", password="testpass"
        )
        other_macro = Macrocycle.objects.create(
            user=other_user, name="Theirs", start_date=date(2026, 6, 1)
        )
        other_meso = Mesocycle.objects.create(macrocycle=other_macro, meso_type="base")
        foreign_micro = Microcycle.objects.create(mesocycle=other_meso, duration_days=7)
        self.assertRejected(
            self.ordering(
                (self.meso_a, [self.a1, self.a2, self.a3, foreign_micro]),
                (self.meso_b, [self.b1, self.b2]),
                (self.meso_c, [self.c1]),
            )
        )
        # The other user's plan is untouched.
        foreign_micro.refresh_from_db()
        self.assertEqual(foreign_micro.mesocycle_id, other_meso.pk)
        self.assertEqual(foreign_micro.order, 1)

    def test_microcycle_added_elsewhere_rejects_stale_submission(self):
        stale = self.ordering(
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        Microcycle.objects.create(mesocycle=self.meso_c, duration_days=7)
        self.assertRejected(stale)

    def test_microcycle_deleted_elsewhere_rejects_stale_submission(self):
        stale = self.ordering(
            (self.meso_a, [self.a1, self.a2, self.a3]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_c, [self.c1]),
        )
        self.c1.delete()
        self.assertRejected(stale)

    def test_empty_ordering_rejected_when_plan_has_cycles(self):
        self.assertRejected([])

    def test_other_macrocycle_untouched_by_a_valid_reorder(self):
        other_macro = Macrocycle.objects.create(
            user=self.user, name="Other", start_date=date(2026, 6, 1)
        )
        other_meso = Mesocycle.objects.create(macrocycle=other_macro, meso_type="base")
        other_micro = Microcycle.objects.create(mesocycle=other_meso, duration_days=7)
        self.apply(
            (self.meso_c, [self.c1]),
            (self.meso_b, [self.b1, self.b2]),
            (self.meso_a, [self.a3, self.a2, self.a1]),
        )
        other_meso.refresh_from_db()
        other_micro.refresh_from_db()
        self.assertEqual(other_meso.order, 1)
        self.assertEqual(other_micro.order, 1)


class ParseOrderingTest(SimpleTestCase):
    """Structural validation, kept separate from set-equality checks."""

    def test_valid_payload(self):
        self.assertEqual(
            parse_ordering([{"pk": 1, "micros": [2, 3]}]),
            [{"pk": 1, "micros": [2, 3]}],
        )

    def test_empty_list_is_structurally_valid(self):
        self.assertEqual(parse_ordering([]), [])

    def test_non_list_rejected(self):
        for bad in ({"pk": 1}, "nope", 5, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_ordering(bad)

    def test_entry_must_be_object(self):
        with self.assertRaises(ValueError):
            parse_ordering([[1, 2]])

    def test_missing_pk_rejected(self):
        with self.assertRaises(ValueError):
            parse_ordering([{"micros": []}])

    def test_non_integer_pk_rejected(self):
        for bad in ("1", 1.5, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_ordering([{"pk": bad, "micros": []}])

    def test_boolean_pk_rejected(self):
        with self.assertRaises(ValueError):
            parse_ordering([{"pk": True, "micros": []}])

    def test_missing_micros_rejected(self):
        with self.assertRaises(ValueError):
            parse_ordering([{"pk": 1}])

    def test_non_list_micros_rejected(self):
        with self.assertRaises(ValueError):
            parse_ordering([{"pk": 1, "micros": "12"}])

    def test_non_integer_micro_rejected(self):
        with self.assertRaises(ValueError):
            parse_ordering([{"pk": 1, "micros": [1, "2"]}])

    def test_boolean_micro_rejected(self):
        with self.assertRaises(ValueError):
            parse_ordering([{"pk": 1, "micros": [False]}])

    def test_stale_ordering_error_is_a_value_error(self):
        self.assertTrue(issubclass(StaleOrderingError, ValueError))


class OrderMixinPrimitiveTest(TestCase):
    """The park/renumber primitives underpinning both delete and reorder."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="primuser", email="prim@example.com", password="testpass"
        )

    def setUp(self):
        self.macro = Macrocycle.objects.create(
            user=self.user, name="Season", start_date=date(2026, 1, 1)
        )
        self.meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        self.micros = [
            Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
            for _ in range(4)
        ]

    def test_park_orders_shifts_out_of_live_range(self):
        Microcycle.park_orders(Microcycle.objects.filter(mesocycle=self.meso))
        orders = list(
            Microcycle.objects.filter(mesocycle=self.meso)
            .order_by("order")
            .values_list("order", flat=True)
        )
        offset = Microcycle.ORDER_STAGING_OFFSET
        self.assertEqual(orders, [offset + 1, offset + 2, offset + 3, offset + 4])

    def test_apply_order_renumbers_single_parent(self):
        reversed_pks = [micro.pk for micro in reversed(self.micros)]
        Microcycle.apply_order(self.meso.pk, reversed_pks)
        self.assertEqual(
            list(
                Microcycle.objects.filter(mesocycle=self.meso)
                .order_by("order")
                .values_list("pk", flat=True)
            ),
            reversed_pks,
        )

    def test_apply_order_rejects_more_rows_than_staging_offset(self):
        too_many = list(range(Microcycle.ORDER_STAGING_OFFSET + 1))
        with self.assertRaises(ValueError):
            Microcycle.apply_order(self.meso.pk, too_many)

    def test_repeated_deletes_stay_gap_free(self):
        """Regression net for compact_siblings after the park/renumber rewrite."""
        while self.micros:
            self.micros.pop(len(self.micros) // 2).delete()
            orders = list(
                Microcycle.objects.filter(mesocycle=self.meso)
                .order_by("order")
                .values_list("order", flat=True)
            )
            self.assertEqual(orders, list(range(1, len(orders) + 1)))


class CreateDefaultCyclesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def _macro(self, name: str = "Test") -> Macrocycle:
        return Macrocycle.objects.create(
            user=self.user, name=name, start_date=date(2026, 1, 1)
        )

    def test_exact_division(self):
        """84 days / 28-day mesos = 3 full mesocycles, each with 4x7-day micros."""
        macro = self._macro("Exact")
        create_default_cycles(
            macro, target_duration_days=84, meso_duration_days=28, micro_duration_days=7
        )
        self.assertEqual(macro.mesocycles.count(), 3)
        for meso in macro.mesocycles.all():
            self.assertEqual(meso.microcycles.count(), 4)
            for micro in meso.microcycles.all():
                self.assertEqual(micro.duration_days, 7)

    def test_remainder_meso(self):
        """90 days / 28-day mesos = 3 full + 1 remainder (6 days = 1 short micro)."""
        macro = self._macro("Remainder")
        create_default_cycles(
            macro, target_duration_days=90, meso_duration_days=28, micro_duration_days=7
        )
        self.assertEqual(macro.mesocycles.count(), 4)
        last_meso = macro.mesocycles.order_by("order").last()
        self.assertEqual(last_meso.microcycles.count(), 1)
        self.assertEqual(last_meso.microcycles.first().duration_days, 6)

    def test_remainder_with_full_and_short_micros(self):
        """100 days / 28-day mesos = 3 full + remainder 16 days (2*7 + 2)."""
        macro = self._macro("Mixed")
        create_default_cycles(
            macro,
            target_duration_days=100,
            meso_duration_days=28,
            micro_duration_days=7,
        )
        self.assertEqual(macro.mesocycles.count(), 4)
        last_meso = macro.mesocycles.order_by("order").last()
        micros = list(last_meso.microcycles.order_by("order"))
        self.assertEqual(len(micros), 3)
        self.assertEqual(micros[0].duration_days, 7)
        self.assertEqual(micros[1].duration_days, 7)
        self.assertEqual(micros[2].duration_days, 2)

    def test_non_divisible_meso_duration(self):
        """35-day mesos with 14-day micros → each full meso: 14+14+7 (3 micros)."""
        macro = self._macro("Non-Divisible")
        create_default_cycles(
            macro,
            target_duration_days=70,
            meso_duration_days=35,
            micro_duration_days=14,
        )
        self.assertEqual(macro.mesocycles.count(), 2)
        for meso in macro.mesocycles.all():
            micros = list(meso.microcycles.order_by("order"))
            self.assertEqual(len(micros), 3)
            self.assertEqual(micros[0].duration_days, 14)
            self.assertEqual(micros[1].duration_days, 14)
            self.assertEqual(micros[2].duration_days, 7)

    def test_type_cycling(self):
        """Meso types cycle through BASE, BUILD, SHARPEN, PEAK, TRANSITION, repeat."""
        macro = self._macro("Cycling")
        create_default_cycles(
            macro,
            target_duration_days=210,
            meso_duration_days=28,
            micro_duration_days=7,
        )
        # 210 / 28 = 7.5 → 7 full + 1 remainder = 8 mesos
        types = list(
            macro.mesocycles.order_by("order").values_list("meso_type", flat=True)
        )
        expected = [
            "base",
            "build",
            "sharpen",
            "peak",
            "transition",
            "base",
            "build",
            "sharpen",
        ]
        self.assertEqual(types, expected)

    def test_raises_if_mesocycles_exist(self):
        macro = self._macro("Has Mesos")
        Mesocycle.objects.create(macrocycle=macro, meso_type="base")
        with self.assertRaises(ValueError):
            create_default_cycles(
                macro,
                target_duration_days=84,
                meso_duration_days=28,
                micro_duration_days=7,
            )

    def test_total_duration_matches_target(self):
        macro = self._macro("Total Check")
        create_default_cycles(
            macro,
            target_duration_days=100,
            meso_duration_days=28,
            micro_duration_days=7,
        )
        total = sum(
            micro.duration_days
            for meso in macro.mesocycles.all()
            for micro in meso.microcycles.all()
        )
        self.assertEqual(total, 100)

    def test_micro_types_load_except_last_deload(self):
        """create_default_cycles assigns LOAD to all micros except last per meso (DELOAD)."""
        macro = self._macro("MicroTypes")
        create_default_cycles(
            macro, target_duration_days=28, meso_duration_days=28, micro_duration_days=7
        )
        meso = macro.mesocycles.first()
        micros = list(meso.microcycles.order_by("order"))
        # 28 / 7 = 4 micros, last one should be deload
        self.assertEqual(len(micros), 4)
        for micro in micros[:-1]:
            self.assertEqual(micro.micro_type, "load")
        self.assertEqual(micros[-1].micro_type, "deload")

    def test_micro_types_remainder_micro_is_deload(self):
        """When a meso has a remainder micro, that remainder is the deload."""
        macro = self._macro("Remainder Deload")
        create_default_cycles(
            macro, target_duration_days=25, meso_duration_days=25, micro_duration_days=7
        )
        meso = macro.mesocycles.first()
        micros = list(meso.microcycles.order_by("order"))
        # 25 / 7 = 3 full + 4 days remainder = 4 micros
        self.assertEqual(len(micros), 4)
        for micro in micros[:-1]:
            self.assertEqual(micro.micro_type, "load")
        self.assertEqual(micros[-1].micro_type, "deload")
        self.assertEqual(micros[-1].duration_days, 4)


class CreateCyclesFormTest(TestCase):
    def test_valid_data(self):
        from workouts.forms import CreateCyclesForm

        form = CreateCyclesForm(
            data={
                "target_duration_days": 84,
                "meso_duration_days": 28,
                "micro_duration_days": 7,
            }
        )
        self.assertTrue(form.is_valid())

    def test_meso_less_than_micro_raises(self):
        from workouts.forms import CreateCyclesForm

        form = CreateCyclesForm(
            data={
                "target_duration_days": 84,
                "meso_duration_days": 3,
                "micro_duration_days": 7,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("meso_duration_days", form.errors)

    def test_zero_value_rejected(self):
        from workouts.forms import CreateCyclesForm

        form = CreateCyclesForm(
            data={
                "target_duration_days": 0,
                "meso_duration_days": 28,
                "micro_duration_days": 7,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("target_duration_days", form.errors)


class ActiveMacrocycleTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="runner", email="runner@example.com", password="test"
        )
        self.macro = Macrocycle.objects.create(
            user=self.user, name="Plan A", start_date=date(2026, 1, 1)
        )

    def test_create_active_macrocycle(self):
        active = ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro)
        self.assertEqual(active.user, self.user)
        self.assertEqual(active.macrocycle, self.macro)

    def test_one_per_user(self):
        ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro)
        macro2 = Macrocycle.objects.create(
            user=self.user, name="Plan B", start_date=date(2026, 6, 1)
        )
        with self.assertRaises(IntegrityError):
            ActiveMacrocycle.objects.create(user=self.user, macrocycle=macro2)

    def test_cascade_delete_macrocycle(self):
        ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro)
        self.macro.delete()
        self.assertEqual(ActiveMacrocycle.objects.count(), 0)

    def test_cascade_delete_user(self):
        ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro)
        self.user.delete()
        self.assertEqual(ActiveMacrocycle.objects.count(), 0)

    def test_str(self):
        active = ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro)
        self.assertIn("runner", str(active))
        self.assertIn("Plan A", str(active))
