"""Context processors for sidebar navigation and breadcrumbs.

Provides two processors registered in settings:

``grouped_subtypes``
    Groups WorkoutSubtype objects by parent type for the "New Workout"
    dropdown in the sidebar.

``sidebar_navigation``
    Resolves the current URL to determine active sidebar section/item,
    builds the breadcrumb trail, and finds the active macrocycle URL.
    Breadcrumb hierarchy is built from lightweight PK-indexed queries
    (max 3 queries for the deepest pages).
"""

from dataclasses import dataclass

from django.http import HttpRequest
from django.urls import resolve, reverse, Resolver404

from .enums import SUBTYPE_TYPE_MAP, WorkoutSubtype, WorkoutType
from .models import (
    ActiveMacrocycle,
    Macrocycle,
    Mesocycle,
    Microcycle,
    Workout,
)

_TYPE_LABELS = {
    WorkoutType.AEROBIC: "Aerobic",
    WorkoutType.STRENGTH: "Strength",
    WorkoutType.GENERIC: "Other",
}

_URL_SIDEBAR_MAP: dict[str, tuple[str, str]] = {
    # url_name: (section, item)
    "macrocycle_list": ("plans", "all_plans"),
    "create_macrocycle": ("plans", "new_plan"),
    "macrocycle_detail": ("plans", "all_plans"),
    "edit_macrocycle": ("plans", "all_plans"),
    "delete_macrocycle": ("plans", "all_plans"),
    "macrocycle_summary": ("plans", "all_plans"),
    "create_default_cycles": ("plans", "all_plans"),
    "toggle_active": ("plans", "all_plans"),
    "mesocycle_detail": ("plans", "all_plans"),
    "create_mesocycle": ("plans", "all_plans"),
    "edit_mesocycle": ("plans", "all_plans"),
    "delete_mesocycle": ("plans", "all_plans"),
    "microcycle_detail": ("plans", "all_plans"),
    "create_microcycle": ("plans", "all_plans"),
    "edit_microcycle": ("plans", "all_plans"),
    "delete_microcycle": ("plans", "all_plans"),
    "workout_list": ("workouts", "all_workouts"),
    "running_list": ("workouts", "running"),
    "workout_detail": ("workouts", "all_workouts"),
    "edit_workout": ("workouts", "all_workouts"),
    "delete_workout": ("workouts", "all_workouts"),
    "create_workout": ("create", ""),
}


@dataclass(frozen=True)
class BreadcrumbItem:
    """Single breadcrumb entry. Empty url means current page (rendered as text, not a link)."""

    label: str
    url: str = ""


# ── DB lookup helpers (lightweight PK-indexed queries) ──────────────


def _get_macro_name(pk: int) -> str:
    try:
        return Macrocycle.objects.values_list("name", flat=True).get(pk=pk)
    except Macrocycle.DoesNotExist:
        return "Plan"


def _get_meso_display(pk: int) -> str:
    try:
        return (
            Mesocycle.objects.values_list("meso_type", flat=True)
            .get(pk=pk)
            .capitalize()
        )
    except Mesocycle.DoesNotExist:
        return "Mesocycle"


def _get_micro_display(pk: int) -> str:
    try:
        return (
            Microcycle.objects.values_list("micro_type", flat=True)
            .get(pk=pk)
            .capitalize()
        )
    except Microcycle.DoesNotExist:
        return "Microcycle"


def _get_workout_name(pk: int) -> str:
    try:
        return Workout.objects.values_list("name", flat=True).get(pk=pk)
    except Workout.DoesNotExist:
        return "Workout"


# ── Breadcrumb builder ──────────────────────────────────────────────


def _plan_crumbs(
    url_name: str, kwargs: dict
) -> list[BreadcrumbItem]:  # pylint: disable=too-many-return-statements
    """Build breadcrumb trail for plan hierarchy pages (macro/meso/micro)."""
    plans_url = reverse("workouts:macrocycle_list")
    macro_pk = kwargs["macro_pk"]
    macro_name = _get_macro_name(macro_pk)
    macro_url = reverse("workouts:macrocycle_detail", kwargs={"macro_pk": macro_pk})
    trail = [BreadcrumbItem("Plans", plans_url), BreadcrumbItem(macro_name, macro_url)]

    if url_name == "macrocycle_detail":
        trail[-1] = BreadcrumbItem(macro_name)  # current page, no link
        return trail

    if url_name == "macrocycle_summary":
        return trail + [BreadcrumbItem("Summary")]

    if url_name in ("edit_macrocycle", "delete_macrocycle"):
        action = "Edit" if "edit" in url_name else "Delete"
        return trail + [BreadcrumbItem(action)]

    if url_name == "create_mesocycle":
        return trail + [BreadcrumbItem("New Mesocycle")]

    if url_name == "create_default_cycles":
        return trail + [BreadcrumbItem("Generate Cycles")]

    # Meso-level and below require meso_pk
    meso_pk = kwargs.get("meso_pk")
    if not meso_pk:
        return trail

    meso_display = _get_meso_display(meso_pk)
    meso_url = reverse(
        "workouts:mesocycle_detail",
        kwargs={"macro_pk": macro_pk, "meso_pk": meso_pk},
    )
    trail.append(BreadcrumbItem(meso_display, meso_url))

    if url_name == "mesocycle_detail":
        trail[-1] = BreadcrumbItem(meso_display)
        return trail

    if url_name in ("edit_mesocycle", "delete_mesocycle"):
        action = "Edit" if "edit" in url_name else "Delete"
        return trail + [BreadcrumbItem(action)]

    if url_name == "create_microcycle":
        return trail + [BreadcrumbItem("New Microcycle")]

    # Micro-level requires micro_pk
    micro_pk = kwargs.get("micro_pk")
    if not micro_pk:
        return trail

    micro_display = _get_micro_display(micro_pk)

    if url_name == "microcycle_detail":
        return trail + [BreadcrumbItem(micro_display)]

    if url_name in ("edit_microcycle", "delete_microcycle"):
        micro_url = reverse(
            "workouts:microcycle_detail",
            kwargs={"macro_pk": macro_pk, "meso_pk": meso_pk, "micro_pk": micro_pk},
        )
        action = "Edit" if "edit" in url_name else "Delete"
        return trail + [
            BreadcrumbItem(micro_display, micro_url),
            BreadcrumbItem(action),
        ]

    return trail


def _workout_crumbs(
    url_name: str, kwargs: dict, request: HttpRequest
) -> list[BreadcrumbItem]:
    """Build breadcrumb trail for workout pages."""
    workouts_url = reverse("workouts:workout_list")

    if url_name == "workout_list":
        return [BreadcrumbItem("Workouts")]

    if url_name == "running_list":
        return [BreadcrumbItem("Running")]

    pk = kwargs.get("pk")
    if pk and url_name in ("workout_detail", "edit_workout", "delete_workout"):
        workout_name = _get_workout_name(pk)
        if url_name == "workout_detail":
            return [
                BreadcrumbItem("Workouts", workouts_url),
                BreadcrumbItem(workout_name),
            ]
        workout_url = reverse("workouts:workout_detail", kwargs={"pk": pk})
        action = "Edit" if "edit" in url_name else "Delete"
        return [
            BreadcrumbItem("Workouts", workouts_url),
            BreadcrumbItem(workout_name, workout_url),
            BreadcrumbItem(action),
        ]

    if url_name == "create_workout":
        subtype_value = kwargs.get("subtype", "")
        label = "New Workout"
        if subtype_value:
            try:
                label = f"New {WorkoutSubtype(subtype_value).label}"
            except ValueError:
                pass
        return [BreadcrumbItem("Workouts", workouts_url), BreadcrumbItem(label)]

    return []


def _build_breadcrumbs(
    url_name: str, kwargs: dict, request: HttpRequest
) -> list[BreadcrumbItem]:
    if url_name == "macrocycle_list":
        return [BreadcrumbItem("Plans")]

    if url_name == "create_macrocycle":
        plans_url = reverse("workouts:macrocycle_list")
        return [BreadcrumbItem("Plans", plans_url), BreadcrumbItem("New Plan")]

    if kwargs.get("macro_pk"):
        return _plan_crumbs(url_name, kwargs)

    return _workout_crumbs(url_name, kwargs, request)


def grouped_subtypes(request: HttpRequest) -> dict:
    """Return workout subtypes grouped by parent type for the sidebar dropdown."""
    if not request.user.is_authenticated:
        return {"grouped_subtypes": []}
    subtypes_by_type: dict[WorkoutType, list[WorkoutSubtype]] = {}
    for st in WorkoutSubtype:
        subtypes_by_type.setdefault(SUBTYPE_TYPE_MAP[st], []).append(st)

    groups = [
        (_TYPE_LABELS.get(wt), wt.value, subtypes_by_type[wt])
        for wt in WorkoutType
        if wt in subtypes_by_type
    ]

    return {"grouped_subtypes": groups}


def sidebar_navigation(request: HttpRequest) -> dict:
    """Resolve sidebar state, breadcrumbs, and active plan URL for the current request."""
    if not request.user.is_authenticated:
        return {
            "active_plan_detail_url": None,
            "nav_section": "",
            "nav_item": "",
            "breadcrumbs": [],
        }

    # Active plan URL
    active_plan_detail_url = None
    active_macro_pk = None
    try:
        active = ActiveMacrocycle.objects.select_related("macrocycle").get(
            user=request.user
        )
        active_macro_pk = active.macrocycle.pk
        active_plan_detail_url = reverse(
            "workouts:macrocycle_detail",
            kwargs={"macro_pk": active_macro_pk},
        )
    except ActiveMacrocycle.DoesNotExist:
        pass

    # Resolve current URL to determine nav state and breadcrumbs
    breadcrumbs: list[BreadcrumbItem] = []
    nav_section = ""
    nav_item = ""

    try:
        match = resolve(request.path)
        url_name = match.url_name

        breadcrumbs = _build_breadcrumbs(url_name, match.kwargs, request)

        if url_name in _URL_SIDEBAR_MAP:
            nav_section, nav_item = _URL_SIDEBAR_MAP[url_name]

            # For create workout, detect the subtype from URL kwargs
            if url_name == "create_workout":
                subtype_value = match.kwargs.get("subtype", "")
                if subtype_value:
                    nav_item = subtype_value

            # Highlight "Active Plan Details" when viewing the active macrocycle
            if (
                active_macro_pk
                and url_name != "macrocycle_summary"
                and match.kwargs.get("macro_pk") == active_macro_pk
            ):
                nav_item = "active_plan"
    except Resolver404:
        pass

    return {
        "active_plan_detail_url": active_plan_detail_url,
        "nav_section": nav_section,
        "nav_item": nav_item,
        "breadcrumbs": breadcrumbs,
    }
