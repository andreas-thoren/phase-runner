import json
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from workouts.enums import WorkoutStatus, WorkoutSubtype
from workouts.models import (
    Workout,
    AerobicDetails,
    GenericDetails,
    StrengthDetails,
    ActiveMacrocycle,
    Macrocycle,
    Mesocycle,
    Microcycle,
)


class AuthenticatedTestMixin:
    """Logs in the test user before each test."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)


class WorkoutListViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )
        cls.workouts = [
            Workout.objects.create(
                user=cls.user,
                name=f"Workout {i}",
                workout_status=WorkoutStatus.COMPLETED,
                subtype=WorkoutSubtype.MOBILITY,
            )
            for i in range(3)
        ]
        cls.url = reverse("workouts:workout_list")

    def test_status_code(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_template_used(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "workouts/workout_list.html")

    def test_context_contains_workouts(self):
        response = self.client.get(self.url)
        self.assertIn("workouts", response.context)
        self.assertEqual(len(response.context["workouts"]), 3)

    def test_ordering_newest_first(self):
        response = self.client.get(self.url)
        workouts = list(response.context["workouts"])
        times = [w.start_time for w in workouts]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_pagination(self):
        for i in range(25):
            Workout.objects.create(
                user=self.user,
                name=f"Extra {i}",
                subtype=WorkoutSubtype.MOBILITY,
            )
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["workouts"]), 15)

        response_p2 = self.client.get(self.url, {"page": 2})
        self.assertEqual(response_p2.status_code, 200)
        self.assertEqual(len(response_p2.context["workouts"]), 13)


class WorkoutListFilterTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="filteruser", email="filter@example.com", password="testpassword"
        )
        cls.url = reverse("workouts:workout_list")

        cls.w1 = Workout.objects.create(
            user=cls.user,
            name="Morning Run",
            subtype=WorkoutSubtype.RUNNING,
            workout_status=WorkoutStatus.COMPLETED,
            start_time=timezone.make_aware(timezone.datetime(2026, 1, 10, 8, 0)),
        )
        cls.w2 = Workout.objects.create(
            user=cls.user,
            name="Evening Ride",
            subtype=WorkoutSubtype.CYCLING,
            workout_status=WorkoutStatus.PLANNED,
            start_time=timezone.make_aware(timezone.datetime(2026, 2, 15, 18, 0)),
        )
        cls.w3 = Workout.objects.create(
            user=cls.user,
            name="Long Run",
            subtype=WorkoutSubtype.RUNNING,
            workout_status=WorkoutStatus.COMPLETED,
            start_time=timezone.make_aware(timezone.datetime(2026, 3, 5, 7, 0)),
        )

    def test_filter_form_in_context(self):
        response = self.client.get(self.url)
        self.assertIn("filter_form", response.context)

    def test_no_filters_returns_all(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["workouts"]), 3)

    def test_filter_by_date_from(self):
        response = self.client.get(self.url, {"date_from": "2026-02-01"})
        names = {w.name for w in response.context["workouts"]}
        self.assertEqual(names, {"Evening Ride", "Long Run"})

    def test_filter_by_date_to(self):
        response = self.client.get(self.url, {"date_to": "2026-02-01"})
        names = {w.name for w in response.context["workouts"]}
        self.assertEqual(names, {"Morning Run"})

    def test_filter_by_date_range(self):
        response = self.client.get(
            self.url, {"date_from": "2026-01-15", "date_to": "2026-03-01"}
        )
        names = {w.name for w in response.context["workouts"]}
        self.assertEqual(names, {"Evening Ride"})

    def test_filter_by_status(self):
        response = self.client.get(self.url, {"status": WorkoutStatus.COMPLETED})
        names = {w.name for w in response.context["workouts"]}
        self.assertEqual(names, {"Morning Run", "Long Run"})

    def test_filter_by_activity(self):
        response = self.client.get(self.url, {"activity": WorkoutSubtype.CYCLING.value})
        names = {w.name for w in response.context["workouts"]}
        self.assertEqual(names, {"Evening Ride"})

    def test_filter_combined(self):
        response = self.client.get(
            self.url,
            {
                "date_from": "2026-01-01",
                "status": WorkoutStatus.COMPLETED,
                "activity": WorkoutSubtype.RUNNING.value,
            },
        )
        names = {w.name for w in response.context["workouts"]}
        self.assertEqual(names, {"Morning Run", "Long Run"})

    def test_clear_link_shown_when_filtered(self):
        response = self.client.get(self.url, {"activity": WorkoutSubtype.RUNNING.value})
        self.assertContains(response, "Clear")

    def test_clear_button_disabled_when_no_filters(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="filter-clear" disabled')

    def test_no_results_message(self):
        response = self.client.get(self.url, {"date_from": "2099-01-01"})
        self.assertContains(response, "No workouts match your filters.")


class WorkoutDetailViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )
        cls.workout = Workout.objects.create(
            user=cls.user,
            name="Test Run",
            subtype=WorkoutSubtype.RUNNING,
        )
        cls.aerobic = AerobicDetails.objects.create(
            workout=cls.workout, duration=timedelta(minutes=30), distance=5000
        )

    def test_status_code(self):
        url = reverse("workouts:workout_detail", kwargs={"pk": self.workout.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_context_has_forms(self):
        url = reverse("workouts:workout_detail", kwargs={"pk": self.workout.pk})
        response = self.client.get(url)
        self.assertIn("workout_form", response.context)
        self.assertIn("detail_form", response.context)
        self.assertTrue(response.context["read_only"])

    def test_generic_workout_has_no_detail_form(self):
        generic = Workout.objects.create(
            user=self.user,
            name="Generic",
            subtype=WorkoutSubtype.MOBILITY,
        )
        url = reverse("workouts:workout_detail", kwargs={"pk": generic.pk})
        response = self.client.get(url)
        self.assertIsNone(response.context["detail_form"])

    def test_404_for_nonexistent(self):
        url = reverse("workouts:workout_detail", kwargs={"pk": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class WorkoutCreateViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )

    def test_create_page_loads(self):
        url = reverse("workouts:create_workout", kwargs={"subtype": "running"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("detail_form"))

    def test_invalid_subtype_returns_404(self):
        url = reverse("workouts:create_workout", kwargs={"subtype": "bogus"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_create_workout_with_subtype(self):
        url = reverse("workouts:create_workout", kwargs={"subtype": "mobility"})
        data = {
            "name": "New Workout",
            "start_time": "2026-03-07 10:00:00",
            "workout_status": "planned",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        workout = Workout.objects.get(name="New Workout")
        self.assertEqual(workout.subtype, WorkoutSubtype.MOBILITY)

    def test_create_strength_workout_with_detail(self):
        url = reverse("workouts:create_workout", kwargs={"subtype": "strength"})
        data = {
            "name": "Leg Day",
            "start_time": "2026-03-07 10:00:00",
            "workout_status": "planned",
            "detail-num_sets": "5",
            "detail-total_weight": "200",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        workout = Workout.objects.get(name="Leg Day")
        self.assertEqual(workout.workout_type, "strength")
        self.assertEqual(workout.subtype, WorkoutSubtype.STRENGTH)
        detail = workout.get_detail()
        self.assertIsNotNone(detail)
        self.assertEqual(detail.num_sets, 5)

    def test_create_with_empty_detail_skips_detail_row(self):
        url = reverse("workouts:create_workout", kwargs={"subtype": "running"})
        data = {
            "name": "Empty Aerobic",
            "start_time": "2026-03-07 10:00:00",
            "workout_status": "planned",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        workout = Workout.objects.get(name="Empty Aerobic")
        self.assertIsNone(workout.get_detail())
        self.assertFalse(AerobicDetails.objects.filter(workout=workout).exists())


class WorkoutEditViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )

    def setUp(self):
        super().setUp()
        self.workout = Workout.objects.create(
            user=self.user,
            name="Original",
            subtype=WorkoutSubtype.RUNNING,
        )
        self.aerobic = AerobicDetails.objects.create(
            workout=self.workout, duration=timedelta(minutes=30)
        )

    def test_edit_page_loads(self):
        url = reverse("workouts:edit_workout", kwargs={"pk": self.workout.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("detail_form", response.context)

    def test_edit_workout(self):
        url = reverse("workouts:edit_workout", kwargs={"pk": self.workout.pk})
        data = {
            "name": "Updated",
            "start_time": "2026-03-07 10:00:00",
            "workout_status": "planned",
            "detail-duration": "01:00:00",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.name, "Updated")

    def test_edit_preserves_subtype(self):
        url = reverse("workouts:edit_workout", kwargs={"pk": self.workout.pk})
        data = {
            "name": "Renamed",
            "start_time": "2026-03-07 10:00:00",
            "workout_status": "planned",
            "detail-duration": "01:00:00",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.name, "Renamed")
        self.assertEqual(self.workout.subtype, WorkoutSubtype.RUNNING)

    def test_edit_clear_all_detail_fields_deletes_detail(self):
        url = reverse("workouts:edit_workout", kwargs={"pk": self.workout.pk})
        data = {
            "name": "Cleared",
            "start_time": "2026-03-07 10:00:00",
            "workout_status": "planned",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.workout.refresh_from_db()
        self.assertIsNone(self.workout.get_detail())
        self.assertFalse(AerobicDetails.objects.filter(workout=self.workout).exists())

    def test_edit_add_detail_to_workout_without_one(self):
        workout = Workout.objects.create(
            user=self.user,
            name="No Detail",
            subtype=WorkoutSubtype.MOBILITY,
        )
        url = reverse("workouts:edit_workout", kwargs={"pk": workout.pk})
        data = {
            "name": "No Detail",
            "start_time": "2026-03-07 10:00:00",
            "workout_status": "planned",
            "detail-duration": "00:45:00",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        workout.refresh_from_db()
        detail = workout.get_detail()
        self.assertIsNotNone(detail)
        self.assertEqual(detail.duration, timedelta(minutes=45))

    def test_edit_no_detail_stays_empty_when_no_data(self):
        workout = Workout.objects.create(
            user=self.user,
            name="Still Empty",
            subtype=WorkoutSubtype.MOBILITY,
        )
        url = reverse("workouts:edit_workout", kwargs={"pk": workout.pk})
        data = {
            "name": "Still Empty",
            "start_time": "2026-03-07 10:00:00",
            "workout_status": "planned",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(workout.get_detail())
        self.assertFalse(GenericDetails.objects.filter(workout=workout).exists())


class WorkoutDeleteViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )

    def setUp(self):
        super().setUp()
        self.workout = Workout.objects.create(
            user=self.user,
            name="To Delete",
            subtype=WorkoutSubtype.MOBILITY,
        )

    def test_delete_page_loads(self):
        url = reverse("workouts:delete_workout", kwargs={"pk": self.workout.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["read_only"])

    def test_delete_workout(self):
        url = reverse("workouts:delete_workout", kwargs={"pk": self.workout.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Workout.objects.filter(pk=self.workout.pk).exists())


class MacrocycleDetailMesocycleListTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        cls.macro = Macrocycle.objects.create(
            user=cls.user, name="Test Plan", start_date=date(2026, 1, 1)
        )
        cls.meso1 = Mesocycle.objects.create(macrocycle=cls.macro, meso_type="base")
        cls.meso2 = Mesocycle.objects.create(macrocycle=cls.macro, meso_type="build")

    def test_detail_contains_mesocycles(self):
        url = reverse(
            "workouts:macrocycle_detail",
            kwargs={"macro_pk": self.macro.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["mesocycles"]), [self.meso1, self.meso2])

    def test_detail_has_create_meso_url(self):
        url = reverse(
            "workouts:macrocycle_detail",
            kwargs={"macro_pk": self.macro.pk},
        )
        response = self.client.get(url)
        expected = reverse(
            "workouts:create_mesocycle",
            kwargs={"macro_pk": self.macro.pk},
        )
        self.assertEqual(response.context["create_meso_url"], expected)

    def test_empty_macrocycle_has_no_mesocycles(self):
        empty = Macrocycle.objects.create(
            user=self.user, name="Empty", start_date=date(2026, 6, 1)
        )
        url = reverse(
            "workouts:macrocycle_detail",
            kwargs={"macro_pk": empty.pk},
        )
        response = self.client.get(url)
        self.assertEqual(list(response.context["mesocycles"]), [])


class MacrocycleCreateDefaultCyclesViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        cls.macro = Macrocycle.objects.create(
            user=cls.user,
            name="Default Test",
            start_date=date(2026, 1, 1),
        )

    def _url(self):
        return reverse(
            "workouts:create_default_cycles",
            kwargs={"macro_pk": self.macro.pk},
        )

    def _form_data(self, **overrides):
        data = {
            "target_duration_days": 84,
            "meso_duration_days": 28,
            "micro_duration_days": 7,
        }
        data.update(overrides)
        return data

    def test_get_renders_form(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertContains(response, "Target duration")

    def test_get_with_existing_mesocycles_shows_error(self):
        macro = Macrocycle.objects.create(
            user=self.user, name="Has Mesos GET", start_date=date(2026, 6, 1)
        )
        Mesocycle.objects.create(macrocycle=macro, meso_type="base")
        url = reverse("workouts:create_default_cycles", kwargs={"macro_pk": macro.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_mesocycles"])
        self.assertContains(response, "already has mesocycles")

    def test_post_creates_cycles(self):
        response = self.client.post(self._url(), self._form_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.macro.mesocycles.count(), 3)
        for meso in self.macro.mesocycles.all():
            self.assertEqual(meso.microcycles.count(), 4)

    def test_post_validation_meso_less_than_micro(self):
        response = self.client.post(
            self._url(), self._form_data(meso_duration_days=3, micro_duration_days=7)
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "meso_duration_days",
            ["Mesocycle duration must be >= microcycle duration (7 days)."],
        )

    def test_post_guard_existing_mesocycles(self):
        Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        response = self.client.post(self._url(), self._form_data())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_mesocycles"])
        # Should not have created additional mesocycles
        self.assertEqual(self.macro.mesocycles.count(), 1)

    def test_redirects_to_macro_detail(self):
        response = self.client.post(self._url(), self._form_data())
        self.assertRedirects(response, self.macro.get_absolute_url())

    def test_cancel_url_points_to_macro_detail(self):
        response = self.client.get(self._url())
        self.assertEqual(response.context["cancel_url"], self.macro.get_absolute_url())

    def test_submit_label_is_create(self):
        response = self.client.get(self._url())
        self.assertEqual(response.context["submit_label"], "Create")

    def test_link_shown_when_empty(self):
        empty = Macrocycle.objects.create(
            user=self.user,
            name="Empty Plan",
            start_date=date(2026, 6, 1),
        )
        url = reverse(
            "workouts:macrocycle_detail",
            kwargs={"macro_pk": empty.pk},
        )
        response = self.client.get(url)
        self.assertTrue(response.context["can_create_defaults"])
        self.assertContains(response, "Generate cycles")

    def test_link_hidden_when_mesos_exist(self):
        macro = Macrocycle.objects.create(
            user=self.user,
            name="Has Mesos View",
            start_date=date(2026, 6, 1),
        )
        Mesocycle.objects.create(macrocycle=macro, meso_type="base")
        url = reverse(
            "workouts:macrocycle_detail",
            kwargs={"macro_pk": macro.pk},
        )
        response = self.client.get(url)
        self.assertFalse(response.context["can_create_defaults"])
        self.assertNotContains(response, "Generate cycles")


class MesocycleDetailMicrocycleListTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        cls.macro = Macrocycle.objects.create(
            user=cls.user, name="Test Plan", start_date=date(2026, 1, 1)
        )
        cls.meso = Mesocycle.objects.create(macrocycle=cls.macro, meso_type="base")
        cls.micro1 = Microcycle.objects.create(mesocycle=cls.meso)
        cls.micro2 = Microcycle.objects.create(mesocycle=cls.meso)

    def _detail_url(self):
        return reverse(
            "workouts:mesocycle_detail",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": self.meso.pk},
        )

    def test_detail_contains_microcycles(self):
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["microcycles"]), [self.micro1, self.micro2]
        )

    def test_detail_has_create_micro_url(self):
        response = self.client.get(self._detail_url())
        expected = reverse(
            "workouts:create_microcycle",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": self.meso.pk},
        )
        self.assertEqual(response.context["create_micro_url"], expected)

    def test_empty_mesocycle_has_no_microcycles(self):
        empty_meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="build")
        url = reverse(
            "workouts:mesocycle_detail",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": empty_meso.pk},
        )
        response = self.client.get(url)
        self.assertEqual(list(response.context["microcycles"]), [])


class MesocycleViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        cls.macro = Macrocycle.objects.create(
            user=cls.user, name="Test Plan", start_date=date(2026, 1, 1)
        )

    def test_detail_status_code(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:mesocycle_detail",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": meso.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["read_only"])

    def test_detail_404_wrong_macro(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:mesocycle_detail",
            kwargs={"macro_pk": 99999, "meso_pk": meso.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_detail_404_wrong_meso(self):
        url = reverse(
            "workouts:mesocycle_detail",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": 99999},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_create_page_loads(self):
        url = reverse(
            "workouts:create_mesocycle",
            kwargs={"macro_pk": self.macro.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_create_mesocycle(self):
        url = reverse(
            "workouts:create_mesocycle",
            kwargs={"macro_pk": self.macro.pk},
        )
        response = self.client.post(url, {"meso_type": "base", "comment": "First"})
        self.assertEqual(response.status_code, 302)
        meso = Mesocycle.objects.get(macrocycle=self.macro)
        self.assertEqual(meso.meso_type, "base")
        self.assertEqual(meso.order, 1)

    def test_create_auto_increments_order(self):
        Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:create_mesocycle",
            kwargs={"macro_pk": self.macro.pk},
        )
        self.client.post(url, {"meso_type": "build"})
        meso2 = Mesocycle.objects.filter(macrocycle=self.macro).order_by("order").last()
        self.assertEqual(meso2.order, 2)

    def test_create_redirects_to_own_detail(self):
        url = reverse(
            "workouts:create_mesocycle",
            kwargs={"macro_pk": self.macro.pk},
        )
        response = self.client.post(url, {"meso_type": "base"})
        meso = Mesocycle.objects.filter(macrocycle=self.macro).latest("pk")
        self.assertRedirects(response, meso.get_absolute_url())

    def test_create_404_invalid_macro(self):
        url = reverse(
            "workouts:create_mesocycle",
            kwargs={"macro_pk": 99999},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_edit_page_loads(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:edit_mesocycle",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": meso.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_mesocycle(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:edit_mesocycle",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": meso.pk},
        )
        response = self.client.post(url, {"meso_type": "build", "comment": "Changed"})
        self.assertEqual(response.status_code, 302)
        meso.refresh_from_db()
        self.assertEqual(meso.meso_type, "build")
        self.assertEqual(meso.comment, "Changed")

    def test_edit_redirects_to_own_detail(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:edit_mesocycle",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": meso.pk},
        )
        response = self.client.post(url, {"meso_type": "base", "comment": "Updated"})
        self.assertRedirects(response, meso.get_absolute_url())

    def test_delete_page_loads(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:delete_mesocycle",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": meso.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["read_only"])

    def test_delete_mesocycle(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:delete_mesocycle",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": meso.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Mesocycle.objects.filter(pk=meso.pk).exists())

    def test_delete_redirects_to_macro_detail(self):
        meso = Mesocycle.objects.create(macrocycle=self.macro, meso_type="base")
        url = reverse(
            "workouts:delete_mesocycle",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": meso.pk},
        )
        response = self.client.post(url)
        self.assertRedirects(response, self.macro.get_absolute_url())


class MicrocycleViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        cls.macro = Macrocycle.objects.create(
            user=cls.user, name="Test Plan", start_date=date(2026, 1, 1)
        )
        cls.meso = Mesocycle.objects.create(macrocycle=cls.macro, meso_type="base")

    def _url(self, name, **extra_kwargs):
        kwargs = {"macro_pk": self.macro.pk, "meso_pk": self.meso.pk}
        kwargs.update(extra_kwargs)
        return reverse(f"workouts:{name}", kwargs=kwargs)

    def test_detail_status_code(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        url = self._url("microcycle_detail", micro_pk=micro.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["read_only"])

    def test_detail_404_wrong_macro(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        url = reverse(
            "workouts:microcycle_detail",
            kwargs={
                "macro_pk": 99999,
                "meso_pk": self.meso.pk,
                "micro_pk": micro.pk,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_detail_404_wrong_meso(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        url = reverse(
            "workouts:microcycle_detail",
            kwargs={
                "macro_pk": self.macro.pk,
                "meso_pk": 99999,
                "micro_pk": micro.pk,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_detail_404_wrong_order(self):
        url = self._url("microcycle_detail", micro_pk=99999)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_create_page_loads(self):
        url = self._url("create_microcycle")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_create_microcycle(self):
        url = self._url("create_microcycle")
        response = self.client.post(url, {"duration_days": 7, "micro_type": "load"})
        self.assertEqual(response.status_code, 302)
        micro = Microcycle.objects.get(mesocycle=self.meso)
        self.assertEqual(micro.duration_days, 7)
        self.assertEqual(micro.order, 1)

    def test_create_auto_increments_order(self):
        Microcycle.objects.create(mesocycle=self.meso)
        url = self._url("create_microcycle")
        self.client.post(url, {"duration_days": 5, "micro_type": "load"})
        micro2 = Microcycle.objects.filter(mesocycle=self.meso).order_by("order").last()
        self.assertEqual(micro2.order, 2)

    def test_create_redirects_to_own_detail(self):
        url = self._url("create_microcycle")
        response = self.client.post(url, {"duration_days": 7, "micro_type": "load"})
        micro = Microcycle.objects.filter(mesocycle=self.meso).latest("pk")
        self.assertRedirects(response, micro.get_absolute_url())

    def test_create_404_invalid_meso(self):
        url = reverse(
            "workouts:create_microcycle",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": 99999},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_edit_page_loads(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        url = self._url("edit_microcycle", micro_pk=micro.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_microcycle(self):
        micro = Microcycle.objects.create(mesocycle=self.meso, duration_days=7)
        url = self._url("edit_microcycle", micro_pk=micro.pk)
        response = self.client.post(
            url, {"duration_days": 10, "micro_type": "load", "comment": "Updated"}
        )
        self.assertEqual(response.status_code, 302)
        micro.refresh_from_db()
        self.assertEqual(micro.duration_days, 10)
        self.assertEqual(micro.comment, "Updated")

    def test_edit_redirects_to_own_detail(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        url = self._url("edit_microcycle", micro_pk=micro.pk)
        response = self.client.post(url, {"duration_days": 7, "micro_type": "load"})
        self.assertRedirects(response, micro.get_absolute_url())

    def test_delete_page_loads(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        url = self._url("delete_microcycle", micro_pk=micro.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["read_only"])

    def test_delete_microcycle(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        url = self._url("delete_microcycle", micro_pk=micro.pk)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Microcycle.objects.filter(pk=micro.pk).exists())

    def test_delete_redirects_to_parent_meso(self):
        micro = Microcycle.objects.create(mesocycle=self.meso)
        url = self._url("delete_microcycle", micro_pk=micro.pk)
        response = self.client.post(url)
        self.assertRedirects(response, self.meso.get_absolute_url())

    def test_create_with_distance_km_conversion(self):
        url = self._url("create_microcycle")
        response = self.client.post(
            url, {"duration_days": 7, "micro_type": "load", "planned_distance": "50.0"}
        )
        self.assertEqual(response.status_code, 302)
        micro = Microcycle.objects.get(mesocycle=self.meso)
        self.assertEqual(micro.planned_distance, 50000)

    def test_edit_distance_display_in_km(self):
        micro = Microcycle.objects.create(mesocycle=self.meso, planned_distance=42195)
        url = self._url("edit_microcycle", micro_pk=micro.pk)
        response = self.client.get(url)
        form = response.context["form"]
        self.assertAlmostEqual(form.initial["planned_distance"], 42.195)


class FormContextMixinConventionTest(SimpleTestCase):
    """Verify that all models using FormContextMixin have the required URL names.

    FormContextMixin auto-resolves URLs using the convention:
        {model}_list, {model}_detail, edit_{model}, delete_{model}
    Child models (without a dedicated list view) use get_parent_url() instead,
    so only {model}_detail, edit_{model}, delete_{model} are required.
    If a URL name doesn't follow this convention, the mixin will raise
    NoReverseMatch at runtime. This test catches that at CI time.
    """

    # Models with a dedicated list view.
    models_and_kwargs = {
        "workout": {"pk": 1},
        "macrocycle": {"macro_pk": 1},
    }

    # Child models without a dedicated list view.
    child_models_and_kwargs = {
        "mesocycle": {"macro_pk": 1, "meso_pk": 1},
        "microcycle": {"macro_pk": 1, "meso_pk": 1, "micro_pk": 1},
    }

    def test_crud_url_names_resolve(self):
        for model_name, kw in self.models_and_kwargs.items():
            for pattern in [
                f"workouts:{model_name}_list",
                f"workouts:{model_name}_detail",
                f"workouts:edit_{model_name}",
                f"workouts:delete_{model_name}",
            ]:
                with self.subTest(pattern=pattern):
                    try:
                        reverse(pattern, kwargs=kw if "list" not in pattern else None)
                    except NoReverseMatch:
                        self.fail(
                            f"URL name '{pattern}' not found. "
                            f"FormContextMixin requires this convention — "
                            f"see workouts/urls.py docstring."
                        )

    def test_child_crud_url_names_resolve(self):
        for model_name, kw in self.child_models_and_kwargs.items():
            for pattern in [
                f"workouts:{model_name}_detail",
                f"workouts:edit_{model_name}",
                f"workouts:delete_{model_name}",
            ]:
                with self.subTest(pattern=pattern):
                    try:
                        reverse(pattern, kwargs=kw)
                    except NoReverseMatch:
                        self.fail(
                            f"URL name '{pattern}' not found. "
                            f"FormContextMixin requires this convention — "
                            f"see workouts/urls.py docstring."
                        )


class MacrocycleSummaryViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="summaryuser", email="s@example.com", password="testpassword"
        )
        # Macro starting on Monday 2026-01-05 (ISO week 2)
        cls.macro = Macrocycle.objects.create(
            user=cls.user, name="Summary Plan", start_date=date(2026, 1, 5)
        )
        cls.meso1 = Mesocycle.objects.create(macrocycle=cls.macro, meso_type="base")
        cls.meso2 = Mesocycle.objects.create(macrocycle=cls.macro, meso_type="build")
        # meso1: 2 microcycles
        cls.micro1 = Microcycle.objects.create(
            mesocycle=cls.meso1,
            duration_days=7,
            planned_distance=50000,
            planned_long_distance=20000,
        )
        cls.micro2 = Microcycle.objects.create(mesocycle=cls.meso1, duration_days=7)
        # meso2: 1 microcycle
        cls.micro3 = Microcycle.objects.create(mesocycle=cls.meso2, duration_days=7)

        # Workouts in micro1's date range (2026-01-05 to 2026-01-11)
        cls.run1 = Workout.objects.create(
            user=cls.user,
            name="Run 1",
            subtype=WorkoutSubtype.RUNNING,
            start_time=timezone.make_aware(timezone.datetime(2026, 1, 6, 8, 0)),
        )
        AerobicDetails.objects.create(
            workout=cls.run1,
            distance=10000,
            additional_data={"gui_fields": {"load_garmin": 100}},
        )

        cls.run2 = Workout.objects.create(
            user=cls.user,
            name="Run 2",
            subtype=WorkoutSubtype.RUNNING,
            start_time=timezone.make_aware(timezone.datetime(2026, 1, 8, 8, 0)),
        )
        AerobicDetails.objects.create(
            workout=cls.run2,
            distance=20000,
            additional_data={"gui_fields": {"load_garmin": 130}},
        )

        cls.cross = Workout.objects.create(
            user=cls.user,
            name="Bike",
            subtype=WorkoutSubtype.CYCLING,
            start_time=timezone.make_aware(timezone.datetime(2026, 1, 7, 8, 0)),
        )

        cls.strength = Workout.objects.create(
            user=cls.user,
            name="Gym",
            subtype=WorkoutSubtype.STRENGTH,
            start_time=timezone.make_aware(timezone.datetime(2026, 1, 9, 8, 0)),
        )

        cls.url = reverse(
            "workouts:macrocycle_summary",
            kwargs={"macro_pk": cls.macro.pk},
        )

    def test_status_code(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_template_used(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "workouts/macrocycle_summary.html")

    def test_row_count(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["rows"]), 3)

    def test_planned_data(self):
        response = self.client.get(self.url)
        row = response.context["rows"][0]
        self.assertEqual(row["planned_distance_km"], 50.0)
        self.assertEqual(row["planned_long_km"], 20.0)

    def test_meso_display(self):
        response = self.client.get(self.url)
        rows = response.context["rows"]
        self.assertEqual(rows[0]["meso_display"], "Base")
        self.assertEqual(rows[2]["meso_display"], "Build")

    def test_meso_first_row_flag_and_rowspan(self):
        response = self.client.get(self.url)
        rows = response.context["rows"]
        self.assertTrue(rows[0]["meso_first_row"])
        self.assertEqual(rows[0]["meso_rowspan"], 2)
        self.assertFalse(rows[1]["meso_first_row"])
        self.assertEqual(rows[1]["meso_rowspan"], 0)
        self.assertTrue(rows[2]["meso_first_row"])
        self.assertEqual(rows[2]["meso_rowspan"], 1)

    def test_rowspan_in_rendered_html(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'rowspan="2"')
        self.assertContains(response, 'rowspan="1"')

    def test_actual_aggregation(self):
        response = self.client.get(self.url)
        row = response.context["rows"][0]
        self.assertEqual(row["sessions"], 2)
        self.assertEqual(row["sport_distance"], 30.0)
        self.assertEqual(row["long_distance"], 20.0)
        self.assertEqual(row["sport_load"], 230)
        self.assertEqual(row["cross_sessions"], 1)
        self.assertEqual(row["strength_sessions"], 1)
        self.assertEqual(row["total_load"], 230)

    def test_empty_micro_has_zero_actuals(self):
        response = self.client.get(self.url)
        rows = response.context["rows"]
        for idx in [1, 2]:
            row = rows[idx]
            self.assertEqual(row["sessions"], 0)
            self.assertEqual(row["sport_distance"], 0)
            self.assertEqual(row["total_load"], 0)

    def test_404_nonexistent_macro(self):
        url = reverse(
            "workouts:macrocycle_summary",
            kwargs={"macro_pk": 99999},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_empty_macro_message(self):
        empty = Macrocycle.objects.create(
            user=self.user, name="Empty Summary", start_date=date(2026, 6, 1)
        )
        url = reverse(
            "workouts:macrocycle_summary",
            kwargs={"macro_pk": empty.pk},
        )
        response = self.client.get(url)
        self.assertContains(response, "No microcycles in this plan yet.")

    def test_row_has_micro_url(self):
        response = self.client.get(self.url)
        row = response.context["rows"][0]
        expected = reverse(
            "workouts:microcycle_detail",
            kwargs={
                "macro_pk": self.macro.pk,
                "meso_pk": self.meso1.pk,
                "micro_pk": self.micro1.pk,
            },
        )
        self.assertEqual(row["micro_url"], expected)

    def test_row_has_workouts_url_with_date_filter(self):
        response = self.client.get(self.url)
        row = response.context["rows"][0]
        self.assertIn("date_from=2026-01-05", row["workouts_url"])
        self.assertIn("date_to=2026-01-11", row["workouts_url"])

    def test_clickable_zones_in_html(self):
        response = self.client.get(self.url)
        self.assertContains(response, "zone-planned")
        self.assertContains(response, "zone-actual")

    def test_dynamic_column_labels_running(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["col_sessions"], "Runs")
        self.assertEqual(response.context["col_long"], "Long run")

    def test_non_running_primary_sport_aggregation(self):
        """Cycling macrocycle counts cycling as sessions, running as cross."""
        macro = Macrocycle.objects.create(
            user=self.user,
            name="Cycling Plan",
            start_date=date(2026, 3, 2),
            primary_sport=WorkoutSubtype.CYCLING,
        )
        meso = Mesocycle.objects.create(macrocycle=macro, meso_type="base")
        Microcycle.objects.create(mesocycle=meso, duration_days=7)

        # Cycling workout (primary sport)
        ride = Workout.objects.create(
            user=self.user,
            name="Ride",
            subtype=WorkoutSubtype.CYCLING,
            start_time=timezone.make_aware(timezone.datetime(2026, 3, 3, 8, 0)),
        )
        AerobicDetails.objects.create(workout=ride, distance=40000)

        # Running workout (cross-training for this plan)
        Workout.objects.create(
            user=self.user,
            name="Jog",
            subtype=WorkoutSubtype.RUNNING,
            start_time=timezone.make_aware(timezone.datetime(2026, 3, 4, 8, 0)),
        )

        url = reverse("workouts:macrocycle_summary", kwargs={"macro_pk": macro.pk})
        response = self.client.get(url)
        row = response.context["rows"][0]
        self.assertEqual(row["sessions"], 1)
        self.assertEqual(row["sport_distance"], 40.0)
        self.assertEqual(row["cross_sessions"], 1)
        self.assertEqual(response.context["col_sessions"], "Rides")
        self.assertEqual(response.context["col_long"], "Long ride")

    def test_summary_link_on_detail_page(self):
        url = reverse(
            "workouts:macrocycle_detail",
            kwargs={"macro_pk": self.macro.pk},
        )
        response = self.client.get(url)
        expected = reverse(
            "workouts:macrocycle_summary",
            kwargs={"macro_pk": self.macro.pk},
        )
        self.assertContains(response, expected)


class ToggleActiveMacrocycleViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )
        cls.macro1 = Macrocycle.objects.create(
            user=cls.user, name="Plan A", start_date=date(2026, 1, 1)
        )
        cls.macro2 = Macrocycle.objects.create(
            user=cls.user, name="Plan B", start_date=date(2026, 6, 1)
        )
        cls.url1 = reverse("workouts:toggle_active", kwargs={"macro_pk": cls.macro1.pk})
        cls.url2 = reverse("workouts:toggle_active", kwargs={"macro_pk": cls.macro2.pk})

    def test_activate_macrocycle(self):
        response = self.client.post(self.url1)
        self.assertRedirects(response, self.macro1.get_absolute_url())
        self.assertTrue(
            ActiveMacrocycle.objects.filter(
                user=self.user, macrocycle=self.macro1
            ).exists()
        )

    def test_deactivate_macrocycle(self):
        ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro1)
        response = self.client.post(self.url1)
        self.assertRedirects(response, self.macro1.get_absolute_url())
        self.assertFalse(ActiveMacrocycle.objects.filter(user=self.user).exists())

    def test_switch_active_macrocycle(self):
        ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro1)
        response = self.client.post(self.url2)
        self.assertRedirects(response, self.macro2.get_absolute_url())
        active = ActiveMacrocycle.objects.get(user=self.user)
        self.assertEqual(active.macrocycle, self.macro2)

    def test_get_not_allowed(self):
        response = self.client.get(self.url1)
        self.assertEqual(response.status_code, 405)

    def test_detail_shows_inactive_badge(self):
        url = reverse("workouts:macrocycle_detail", kwargs={"macro_pk": self.macro1.pk})
        response = self.client.get(url)
        self.assertContains(response, "Set as active")
        self.assertNotContains(response, "Active plan")

    def test_detail_shows_active_badge(self):
        ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro1)
        url = reverse("workouts:macrocycle_detail", kwargs={"macro_pk": self.macro1.pk})
        response = self.client.get(url)
        self.assertContains(response, "Active plan")


class IndexViewTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )
        cls.macro = Macrocycle.objects.create(
            user=cls.user, name="Plan A", start_date=date(2026, 1, 1)
        )
        cls.url = reverse("workouts:index")

    def test_redirects_to_plans_list_when_no_active(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("workouts:macrocycle_list"))

    def test_redirects_to_active_macrocycle_summary(self):
        ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro)
        response = self.client.get(self.url)
        expected = reverse(
            "workouts:macrocycle_summary", kwargs={"macro_pk": self.macro.pk}
        )
        self.assertRedirects(response, expected)

    def test_redirects_to_plans_list_after_deactivation(self):
        ActiveMacrocycle.objects.create(user=self.user, macrocycle=self.macro)
        ActiveMacrocycle.objects.filter(user=self.user).delete()
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("workouts:macrocycle_list"))


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class UploadWorkoutsAPITest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="upload@example.com", password="testpassword"
        )
        cls.url = reverse("workouts:upload_workouts_api")

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()

    def _post(self, data):
        return self.client.post(
            self.url,
            json.dumps(data),
            content_type="application/json",
        )

    def test_login_required(self):
        self.client.logout()
        response = self._post([])
        self.assertEqual(response.status_code, 302)

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_empty_array(self):
        response = self._post([])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["created"], 0)
        self.assertEqual(body["skipped"], 0)

    def test_create_aerobic_workout(self):
        data = [
            {
                "subtype": "running",
                "start_time": "2026-04-10T08:30:00Z",
                "duration_seconds": 3600,
                "distance_meters": 12500,
                "gui_fields": {"avg_hr": 145, "max_hr": 172},
            }
        ]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 1)
        self.assertEqual(body["errors"], [])

        workout = Workout.objects.get(user=self.user, subtype="running")
        self.assertEqual(workout.workout_status, WorkoutStatus.COMPLETED)
        self.assertEqual(workout.name, "Morning Run")

        detail = AerobicDetails.objects.get(workout=workout)
        self.assertEqual(detail.duration, timedelta(seconds=3600))
        self.assertEqual(detail.distance, 12500)
        self.assertEqual(detail.additional_data["gui_fields"]["avg_hr"], 145)
        self.assertEqual(detail.additional_data["gui_fields"]["max_hr"], 172)

    def test_create_strength_workout(self):
        data = [
            {
                "subtype": "strength",
                "start_time": "2026-04-10T14:00:00Z",
                "duration_seconds": 2700,
                "gui_fields": {"avg_hr": 120},
            }
        ]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 1)

        workout = Workout.objects.get(user=self.user, subtype="strength")
        self.assertEqual(workout.name, "Afternoon Strength")
        detail = StrengthDetails.objects.get(workout=workout)
        self.assertEqual(detail.duration, timedelta(seconds=2700))

    def test_auto_name_time_of_day(self):
        times_and_names = [
            ("2026-04-10T06:00:00Z", "Morning Run"),
            ("2026-04-10T13:00:00Z", "Afternoon Run"),
            ("2026-04-10T19:00:00Z", "Evening Run"),
            ("2026-04-10T23:00:00Z", "Night Run"),
        ]
        data = [{"subtype": "running", "start_time": t} for t, _ in times_and_names]
        self._post(data)
        for time_str, expected_name in times_and_names:
            workout = Workout.objects.get(
                user=self.user, start_time=time_str.replace("Z", "+00:00")
            )
            self.assertEqual(workout.name, expected_name)

    def test_deduplication(self):
        data = [
            {"subtype": "running", "start_time": "2026-04-10T08:30:00Z"},
        ]
        self._post(data)
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 0)
        self.assertEqual(body["skipped"], 1)
        self.assertEqual(len(body["skipped_details"]), 1)
        self.assertEqual(Workout.objects.filter(user=self.user).count(), 1)

    def test_cross_user_no_dedup(self):
        User = get_user_model()
        other = User.objects.create_user(
            username="other", email="other@example.com", password="testpassword"
        )
        Workout.objects.create(
            user=other,
            name="Other Run",
            start_time="2026-04-10T08:30:00+00:00",
            subtype="running",
        )
        data = [{"subtype": "running", "start_time": "2026-04-10T08:30:00Z"}]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 1)
        self.assertEqual(body["skipped"], 0)

    def test_invalid_subtype(self):
        data = [{"subtype": "basketball", "start_time": "2026-04-10T08:00:00Z"}]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 0)
        self.assertEqual(len(body["errors"]), 1)
        self.assertIn("invalid subtype", body["errors"][0])

    def test_missing_start_time(self):
        data = [{"subtype": "running"}]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 0)
        self.assertEqual(len(body["errors"]), 1)
        self.assertIn("start_time is required", body["errors"][0])

    def test_invalid_json(self):
        response = self.client.post(
            self.url, "not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid JSON", response.json()["error"])

    def test_not_array(self):
        response = self._post({"subtype": "running"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("array", response.json()["error"])

    def test_max_per_request(self):
        data = [
            {"subtype": "running", "start_time": f"2026-04-10T{i:02d}:00:00Z"}
            for i in range(51)
        ]
        response = self._post(data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Maximum", response.json()["error"])

    def test_rate_limiting(self):
        data = [{"subtype": "running", "start_time": "2026-04-10T08:00:00Z"}]
        for i in range(10):
            # Each request needs a unique workout to avoid dedup
            unique_data = [
                {"subtype": "running", "start_time": f"2026-05-{i + 1:02d}T08:00:00Z"}
            ]
            self._post(unique_data)
        response = self._post(data)
        self.assertEqual(response.status_code, 429)

    def test_missing_optional_fields(self):
        data = [{"subtype": "running", "start_time": "2026-04-10T08:00:00Z"}]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 1)
        workout = Workout.objects.get(user=self.user)
        detail = AerobicDetails.objects.get(workout=workout)
        self.assertIsNone(detail.duration)
        self.assertIsNone(detail.distance)

    def test_invalid_gui_field_keys(self):
        data = [
            {
                "subtype": "running",
                "start_time": "2026-04-10T08:00:00Z",
                "gui_fields": {"fake_field": 42},
            }
        ]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 0)
        self.assertEqual(len(body["errors"]), 1)
        self.assertIn("unknown gui_fields", body["errors"][0])

    def test_multiple_workouts_mixed(self):
        data = [
            {"subtype": "running", "start_time": "2026-04-10T08:00:00Z"},
            {"subtype": "invalid", "start_time": "2026-04-10T09:00:00Z"},
            {"subtype": "cycling", "start_time": "2026-04-10T14:00:00Z"},
        ]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 2)
        self.assertEqual(len(body["errors"]), 1)

    def test_custom_name_accepted(self):
        data = [
            {
                "subtype": "running",
                "start_time": "2026-04-10T08:00:00Z",
                "name": "Tempo Run",
            },
        ]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 1)
        workout = Workout.objects.get(user=self.user)
        self.assertEqual(workout.name, "Tempo Run")

    def test_name_fallback_when_empty(self):
        data = [
            {"subtype": "running", "start_time": "2026-04-10T08:00:00Z", "name": ""},
        ]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 1)
        workout = Workout.objects.get(user=self.user)
        self.assertEqual(workout.name, "Morning Run")

    def test_name_too_long(self):
        data = [
            {
                "subtype": "running",
                "start_time": "2026-04-10T08:00:00Z",
                "name": "x" * 256,
            },
        ]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 0)
        self.assertEqual(len(body["errors"]), 1)
        self.assertIn("name too long", body["errors"][0])

    def test_name_non_string(self):
        data = [
            {"subtype": "running", "start_time": "2026-04-10T08:00:00Z", "name": 42},
        ]
        response = self._post(data)
        body = response.json()
        self.assertEqual(body["created"], 0)
        self.assertEqual(len(body["errors"]), 1)
        self.assertIn("name must be a string", body["errors"][0])


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class ExportWorkoutsTest(AuthenticatedTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="export@example.com", password="testpassword"
        )
        cls.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpassword"
        )
        cls.url = reverse("workouts:export_workouts")

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()

    def _create_workout(self, user=None, **kwargs):
        defaults = {
            "user": user or self.user,
            "name": "Test workout",
            "start_time": timezone.now(),
            "workout_status": WorkoutStatus.COMPLETED,
            "subtype": WorkoutSubtype.RUNNING,
        }
        defaults.update(kwargs)
        return Workout.objects.create(**defaults)

    def _parse_csv(self, response):
        import csv
        import io

        content = response.content.decode("utf-8-sig")  # strip BOM
        lines = content.splitlines(keepends=True)
        if lines and lines[0].startswith("sep="):
            lines = lines[1:]  # skip Excel delimiter hint
        reader = csv.reader(io.StringIO("".join(lines)))
        return list(reader)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_post_not_allowed(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)

    def test_empty_export(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        rows = self._parse_csv(response)
        self.assertEqual(len(rows), 1)  # headers only
        self.assertIn("Date", rows[0])

    def test_export_with_workouts(self):
        w = self._create_workout(name="Morning Run")
        AerobicDetails.objects.create(
            workout=w,
            duration=timedelta(hours=1),
            distance=10000,
        )
        response = self.client.get(self.url)
        rows = self._parse_csv(response)
        self.assertEqual(len(rows), 2)  # header + 1 data row
        headers = rows[0]
        data = rows[1]
        self.assertEqual(data[headers.index("Name")], "Morning Run")
        self.assertEqual(data[headers.index("Distance (km)")], "10.00")
        self.assertEqual(data[headers.index("Activity")], "Running")

    def test_filter_by_activity(self):
        self._create_workout(subtype=WorkoutSubtype.RUNNING, name="Run")
        self._create_workout(subtype=WorkoutSubtype.STRENGTH, name="Strength")
        response = self.client.get(self.url, {"activity": "running"})
        rows = self._parse_csv(response)
        self.assertEqual(len(rows), 2)  # header + 1 running
        self.assertEqual(rows[1][rows[0].index("Name")], "Run")

    def test_filter_by_date_range(self):
        self._create_workout(
            start_time=timezone.make_aware(timezone.datetime(2026, 1, 1, 10, 0)),
            name="Old",
        )
        self._create_workout(
            start_time=timezone.make_aware(timezone.datetime(2026, 6, 1, 10, 0)),
            name="New",
        )
        response = self.client.get(
            self.url, {"date_from": "2026-05-01", "date_to": "2026-07-01"}
        )
        rows = self._parse_csv(response)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][rows[0].index("Name")], "New")

    def test_filter_by_status(self):
        self._create_workout(workout_status=WorkoutStatus.COMPLETED, name="Done")
        self._create_workout(workout_status=WorkoutStatus.PLANNED, name="Planned")
        response = self.client.get(self.url, {"status": "completed"})
        rows = self._parse_csv(response)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][rows[0].index("Name")], "Done")

    def test_user_isolation(self):
        self._create_workout(user=self.user, name="My workout")
        self._create_workout(user=self.other_user, name="Other workout")
        response = self.client.get(self.url)
        rows = self._parse_csv(response)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][rows[0].index("Name")], "My workout")

    def test_rate_limiting(self):
        for _ in range(10):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 429)

    def test_csv_filename_contains_date(self):
        response = self.client.get(self.url)
        today = date.today().isoformat()
        self.assertIn(today, response["Content-Disposition"])

    def test_aerobic_columns_present(self):
        w = self._create_workout(subtype=WorkoutSubtype.RUNNING)
        AerobicDetails.objects.create(workout=w, duration=timedelta(minutes=30))
        response = self.client.get(self.url)
        rows = self._parse_csv(response)
        headers = rows[0]
        self.assertIn("Distance (km)", headers)
        self.assertIn("Pace (min/km)", headers)

    def test_strength_columns_present(self):
        w = self._create_workout(subtype=WorkoutSubtype.STRENGTH)
        StrengthDetails.objects.create(workout=w, num_sets=5, total_weight=200)
        response = self.client.get(self.url)
        rows = self._parse_csv(response)
        headers = rows[0]
        self.assertIn("Sets", headers)
        self.assertIn("Total Weight (kg)", headers)
        data = rows[1]
        self.assertEqual(data[headers.index("Sets")], "5")
        self.assertEqual(data[headers.index("Total Weight (kg)")], "200")

    def test_gui_fields_in_columns(self):
        w = self._create_workout(subtype=WorkoutSubtype.RUNNING)
        AerobicDetails.objects.create(
            workout=w,
            additional_data={"gui_fields": {"avg_hr": 150, "load_garmin": 350}},
        )
        response = self.client.get(self.url)
        rows = self._parse_csv(response)
        headers = rows[0]
        self.assertIn("Avg HR", headers)
        self.assertIn("Load (Garmin)", headers)
        data = rows[1]
        self.assertEqual(data[headers.index("Avg HR")], "150")
        self.assertEqual(data[headers.index("Load (Garmin)")], "350")

    def test_dynamic_columns_running_only(self):
        """When only running workouts, cycling-specific columns should not appear."""
        w = self._create_workout(subtype=WorkoutSubtype.RUNNING)
        AerobicDetails.objects.create(workout=w)
        response = self.client.get(self.url)
        rows = self._parse_csv(response)
        headers = rows[0]
        self.assertNotIn("Avg Power (W)", headers)
        self.assertNotIn("Sets", headers)

    def test_dynamic_columns_mixed_subtypes(self):
        """Mixed subtypes include columns from all present subtypes."""
        w1 = self._create_workout(subtype=WorkoutSubtype.RUNNING, name="Run")
        AerobicDetails.objects.create(workout=w1)
        w2 = self._create_workout(subtype=WorkoutSubtype.STRENGTH, name="Lift")
        StrengthDetails.objects.create(workout=w2)
        response = self.client.get(self.url)
        rows = self._parse_csv(response)
        headers = rows[0]
        # Should have both aerobic and strength columns
        self.assertIn("Distance (km)", headers)
        self.assertIn("Sets", headers)
        # Should have gui fields from both subtypes
        self.assertIn("Cadence", headers)
        self.assertIn("Exercises", headers)

    def test_csv_injection_sanitized(self):
        """Values starting with formula characters are prefixed with a quote."""
        self._create_workout(name='=CMD("calc")')
        response = self.client.get(self.url)
        rows = self._parse_csv(response)
        name_val = rows[1][rows[0].index("Name")]
        self.assertEqual(name_val, '\'=CMD("calc")')


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class PasswordResetRateLimitTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="reset@example.com", password="testpassword"
        )
        cls.url = reverse("password_reset")

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_requests_within_limit_succeed(self):
        for _ in range(3):
            response = self.client.post(self.url, {"email": "reset@example.com"})
            self.assertRedirects(response, reverse("password_reset_done"))

    def test_request_over_limit_blocked(self):
        for _ in range(3):
            self.client.post(self.url, {"email": "reset@example.com"})
        response = self.client.post(
            self.url, {"email": "reset@example.com"}, follow=True
        )
        msgs = list(response.context["messages"])
        self.assertTrue(any("Too many password reset requests" in str(m) for m in msgs))


@override_settings(AXES_FAILURE_LIMIT=3, AXES_COOLOFF_TIME=1)
class LoginRateLimitTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )
        cls.url = reverse("login")

    def setUp(self):
        from axes.utils import reset

        reset()

    def test_login_succeeds_with_correct_credentials(self):
        response = self.client.post(
            self.url, {"username": "testuser", "password": "testpassword"}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_invalid_login_shows_error_message(self):
        response = self.client.post(
            self.url, {"username": "testuser", "password": "wrong"}, follow=True
        )
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Invalid username or password.")

    def test_lockout_after_max_failed_attempts(self):
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.client.post(
                self.url, {"username": "testuser", "password": "wrong"}, follow=True
            )
        response = self.client.post(
            self.url, {"username": "testuser", "password": "wrong"}, follow=True
        )
        messages = list(response.context["messages"])
        self.assertTrue(
            any("Too many failed login attempts" in str(m) for m in messages)
        )

    def test_lockout_prevents_valid_login(self):
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.client.post(
                self.url, {"username": "testuser", "password": "wrong"}, follow=True
            )
        response = self.client.post(
            self.url,
            {"username": "testuser", "password": "testpassword"},
            follow=True,
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)
