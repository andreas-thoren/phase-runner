from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from workouts.context_processors import BreadcrumbItem, _build_breadcrumbs
from workouts.enums import WorkoutSubtype
from workouts.models import Macrocycle, Mesocycle, Microcycle, Workout


class BuildBreadcrumbsTestMixin:
    """Shared test data for breadcrumb tests."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="breadcrumb_user", email="bc@example.com", password="testpassword"
        )
        cls.macro = Macrocycle.objects.create(
            user=cls.user, name="My Plan", start_date=date(2026, 1, 1)
        )
        cls.meso = Mesocycle.objects.create(
            macrocycle=cls.macro, meso_type="build", order=1
        )
        cls.micro = Microcycle.objects.create(
            mesocycle=cls.meso, micro_type="load", order=1
        )
        cls.workout = Workout.objects.create(
            user=cls.user,
            name="Morning Run",
            subtype=WorkoutSubtype.RUNNING,
        )


class BuildBreadcrumbsDirectTest(BuildBreadcrumbsTestMixin, TestCase):
    """Test _build_breadcrumbs() directly with url_name and kwargs."""

    # ── Plan list ───────────────────────────────────────────────

    def test_macrocycle_list(self):
        crumbs = _build_breadcrumbs("macrocycle_list", {}, None)
        self.assertEqual(len(crumbs), 1)
        self.assertEqual(crumbs[0].label, "Plans")
        self.assertEqual(crumbs[0].url, "")

    def test_create_macrocycle(self):
        crumbs = _build_breadcrumbs("create_macrocycle", {}, None)
        self.assertEqual(len(crumbs), 2)
        self.assertEqual(crumbs[0].label, "Plans")
        self.assertIn("/plans/", crumbs[0].url)
        self.assertEqual(crumbs[1].label, "New Plan")
        self.assertEqual(crumbs[1].url, "")

    # ── Macrocycle pages ────────────────────────────────────────

    def test_macrocycle_detail(self):
        crumbs = _build_breadcrumbs(
            "macrocycle_detail", {"macro_pk": self.macro.pk}, None
        )
        self.assertEqual(len(crumbs), 2)
        self.assertEqual(crumbs[0].label, "Plans")
        self.assertEqual(crumbs[1].label, "My Plan")
        self.assertEqual(crumbs[1].url, "")

    def test_macrocycle_summary(self):
        crumbs = _build_breadcrumbs(
            "macrocycle_summary", {"macro_pk": self.macro.pk}, None
        )
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[1].label, "My Plan")
        self.assertNotEqual(crumbs[1].url, "")
        self.assertEqual(crumbs[2].label, "Summary")
        self.assertEqual(crumbs[2].url, "")

    def test_edit_macrocycle(self):
        crumbs = _build_breadcrumbs(
            "edit_macrocycle", {"macro_pk": self.macro.pk}, None
        )
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[2].label, "Edit")

    def test_delete_macrocycle(self):
        crumbs = _build_breadcrumbs(
            "delete_macrocycle", {"macro_pk": self.macro.pk}, None
        )
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[2].label, "Delete")

    # ── Mesocycle pages ─────────────────────────────────────────

    def test_mesocycle_detail(self):
        crumbs = _build_breadcrumbs(
            "mesocycle_detail",
            {"macro_pk": self.macro.pk, "meso_pk": self.meso.pk},
            None,
        )
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[1].label, "My Plan")
        self.assertNotEqual(crumbs[1].url, "")
        self.assertEqual(crumbs[2].label, "Build")
        self.assertEqual(crumbs[2].url, "")

    def test_create_mesocycle(self):
        crumbs = _build_breadcrumbs(
            "create_mesocycle", {"macro_pk": self.macro.pk}, None
        )
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[2].label, "New Mesocycle")

    def test_edit_mesocycle(self):
        crumbs = _build_breadcrumbs(
            "edit_mesocycle",
            {"macro_pk": self.macro.pk, "meso_pk": self.meso.pk},
            None,
        )
        self.assertEqual(len(crumbs), 4)
        self.assertEqual(crumbs[2].label, "Build")
        self.assertNotEqual(crumbs[2].url, "")
        self.assertEqual(crumbs[3].label, "Edit")

    # ── Microcycle pages ────────────────────────────────────────

    def test_microcycle_detail(self):
        crumbs = _build_breadcrumbs(
            "microcycle_detail",
            {
                "macro_pk": self.macro.pk,
                "meso_pk": self.meso.pk,
                "micro_pk": self.micro.pk,
            },
            None,
        )
        self.assertEqual(len(crumbs), 4)
        self.assertEqual(crumbs[1].label, "My Plan")
        self.assertEqual(crumbs[2].label, "Build")
        self.assertEqual(crumbs[3].label, "Load")
        self.assertEqual(crumbs[3].url, "")

    def test_edit_microcycle_deep_trail(self):
        crumbs = _build_breadcrumbs(
            "edit_microcycle",
            {
                "macro_pk": self.macro.pk,
                "meso_pk": self.meso.pk,
                "micro_pk": self.micro.pk,
            },
            None,
        )
        self.assertEqual(len(crumbs), 5)
        self.assertEqual(crumbs[0].label, "Plans")
        self.assertEqual(crumbs[1].label, "My Plan")
        self.assertEqual(crumbs[2].label, "Build")
        self.assertEqual(crumbs[3].label, "Load")
        self.assertEqual(crumbs[4].label, "Edit")
        # All ancestors are linked except the last
        for crumb in crumbs[:-1]:
            self.assertNotEqual(crumb.url, "", f"{crumb.label} should have a URL")
        self.assertEqual(crumbs[4].url, "")

    def test_delete_microcycle(self):
        crumbs = _build_breadcrumbs(
            "delete_microcycle",
            {
                "macro_pk": self.macro.pk,
                "meso_pk": self.meso.pk,
                "micro_pk": self.micro.pk,
            },
            None,
        )
        self.assertEqual(len(crumbs), 5)
        self.assertEqual(crumbs[4].label, "Delete")

    # ── Workout pages ───────────────────────────────────────────

    def test_workout_list(self):
        crumbs = _build_breadcrumbs("workout_list", {}, None)
        self.assertEqual(len(crumbs), 1)
        self.assertEqual(crumbs[0].label, "Workouts")

    def test_workout_list_filtered_running(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/workouts/", {"activity": "running"})
        crumbs = _build_breadcrumbs("workout_list", {}, request)
        self.assertEqual(len(crumbs), 1)
        self.assertEqual(crumbs[0].label, "Running")

    def test_workout_detail(self):
        crumbs = _build_breadcrumbs("workout_detail", {"pk": self.workout.pk}, None)
        self.assertEqual(len(crumbs), 2)
        self.assertEqual(crumbs[0].label, "Workouts")
        self.assertNotEqual(crumbs[0].url, "")
        self.assertEqual(crumbs[1].label, "Morning Run")
        self.assertEqual(crumbs[1].url, "")

    def test_edit_workout(self):
        crumbs = _build_breadcrumbs("edit_workout", {"pk": self.workout.pk}, None)
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[1].label, "Morning Run")
        self.assertNotEqual(crumbs[1].url, "")
        self.assertEqual(crumbs[2].label, "Edit")

    def test_delete_workout(self):
        crumbs = _build_breadcrumbs("delete_workout", {"pk": self.workout.pk}, None)
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[2].label, "Delete")

    # ── Fallbacks ───────────────────────────────────────────────

    def test_nonexistent_macro_pk(self):
        crumbs = _build_breadcrumbs("macrocycle_detail", {"macro_pk": 99999}, None)
        self.assertEqual(crumbs[1].label, "Plan")

    def test_nonexistent_meso_pk(self):
        crumbs = _build_breadcrumbs(
            "mesocycle_detail",
            {"macro_pk": self.macro.pk, "meso_pk": 99999},
            None,
        )
        self.assertEqual(crumbs[2].label, "Mesocycle")

    def test_nonexistent_micro_pk(self):
        crumbs = _build_breadcrumbs(
            "microcycle_detail",
            {
                "macro_pk": self.macro.pk,
                "meso_pk": self.meso.pk,
                "micro_pk": 99999,
            },
            None,
        )
        self.assertEqual(crumbs[3].label, "Microcycle")

    def test_nonexistent_workout_pk(self):
        crumbs = _build_breadcrumbs("workout_detail", {"pk": 99999}, None)
        self.assertEqual(crumbs[1].label, "Workout")

    def test_unknown_url_name(self):
        crumbs = _build_breadcrumbs("nonexistent_view", {}, None)
        self.assertEqual(crumbs, [])


class BreadcrumbContextTest(BuildBreadcrumbsTestMixin, TestCase):
    """Test breadcrumbs via response.context on actual HTTP requests."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def _get_breadcrumbs(self, url: str) -> list[BreadcrumbItem]:
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.context["breadcrumbs"]

    def test_macrocycle_list_context(self):
        crumbs = self._get_breadcrumbs(reverse("workouts:macrocycle_list"))
        self.assertEqual(len(crumbs), 1)
        self.assertEqual(crumbs[0].label, "Plans")

    def test_macrocycle_detail_context(self):
        url = reverse("workouts:macrocycle_detail", kwargs={"macro_pk": self.macro.pk})
        crumbs = self._get_breadcrumbs(url)
        self.assertEqual(len(crumbs), 2)
        self.assertEqual(crumbs[1].label, "My Plan")

    def test_mesocycle_detail_context(self):
        url = reverse(
            "workouts:mesocycle_detail",
            kwargs={"macro_pk": self.macro.pk, "meso_pk": self.meso.pk},
        )
        crumbs = self._get_breadcrumbs(url)
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[2].label, "Build")

    def test_microcycle_detail_context(self):
        url = reverse(
            "workouts:microcycle_detail",
            kwargs={
                "macro_pk": self.macro.pk,
                "meso_pk": self.meso.pk,
                "micro_pk": self.micro.pk,
            },
        )
        crumbs = self._get_breadcrumbs(url)
        self.assertEqual(len(crumbs), 4)
        self.assertEqual(crumbs[3].label, "Load")

    def test_workout_detail_context(self):
        url = reverse("workouts:workout_detail", kwargs={"pk": self.workout.pk})
        crumbs = self._get_breadcrumbs(url)
        self.assertEqual(len(crumbs), 2)
        self.assertEqual(crumbs[1].label, "Morning Run")

    def test_summary_context(self):
        url = reverse("workouts:macrocycle_summary", kwargs={"macro_pk": self.macro.pk})
        crumbs = self._get_breadcrumbs(url)
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[2].label, "Summary")

    def test_create_workout_with_subtype(self):
        url = reverse("workouts:create_workout", kwargs={"subtype": "running"})
        crumbs = self._get_breadcrumbs(url)
        self.assertEqual(len(crumbs), 2)
        self.assertEqual(crumbs[1].label, "New Running")
