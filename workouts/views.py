"""Views for the workouts app.

Mixins
------
PaginationMixin
    Adds a sliding page-range window to any paginated ListView, avoiding
    rendering all page numbers when there are many pages.

NoCacheMixin
    Adds ``Cache-Control: no-store`` to prevent browser caching. Used on
    detail views and list views so back-navigation always shows fresh data.

FormContextMixin
    Shared base for all CRUD views using form_base.html. From a single
    ``view_type`` class attribute it auto-resolves: view_type, read_only,
    edit_url, delete_url, detail_url, list_url, and get_success_url.
    Model name and URL kwargs are derived from ``self.model._meta.model_name``
    and ``self.kwargs``. Requires URL names to follow the convention documented
    in workouts/urls.py (``{model}_list``, ``{model}_detail``,
    ``edit_{model}``, ``delete_{model}``). Child models without a list view
    override ``get_parent_url()`` to provide the cancel/fallback URL.

MacrocycleChildMixin
    Resolves the parent macrocycle from ``kwargs["macro_pk"]``, scopes
    ``get_queryset()`` by macrocycle, and provides ``get_parent_url()``
    returning the macrocycle detail URL. Used by Mesocycle CRUD views.

MesocycleChildMixin
    Resolves the parent mesocycle from ``kwargs["macro_pk"]`` +
    ``kwargs["meso_pk"]``, scopes ``get_queryset()`` by mesocycle, and
    provides ``get_parent_url()`` returning the mesocycle detail URL.
    Used by Microcycle CRUD views.

WorkoutMutateMixin
    Shared logic for Create and Update workout views. Handles detail form
    instantiation, GUI field collection, and atomic save of workout + detail.

WorkoutReadonlyFormMixin
    Builds read-only workout_form, detail_form, and gui_fields_display context
    for workout detail and delete views.

LoginView
    Overrides Django's LoginView to use PRG pattern — redirects back with
    a message on invalid credentials instead of re-rendering the form.

GUI schema helpers
------------------
Workout subtypes define a ``gui_schema`` JSONField that describes dynamic
per-subtype form fields (e.g. "cadence" for Running). The private helpers
below handle the view-layer plumbing:

- ``_gui_schemas_json()``: serialises all subtype schemas to JSON for the
  client-side JS that renders the dynamic inputs.
- ``_collect_gui_fields()``: extracts submitted ``gui-*`` POST keys, casts
  numbers per schema, and returns a clean dict for storage.
- ``_gui_fields_from_detail()`` / ``_gui_fields_display()``: read stored
  gui_fields from a detail row for edit pre-population and read-only display.

Adding new CRUD views
---------------------
1. Register URL names following the convention in workouts/urls.py.
2. Create a ``{model}_form.html`` template that extends ``form_base.html``
   and fills the ``form_content`` block.
3. Create view classes inheriting ``(FormContextMixin, DetailView/CreateView/...)``.
   Set ``view_type`` as a class attribute (e.g. ``view_type = ViewType.DETAIL``).
   Everything else (URLs, read_only, success redirect) is handled by the mixin.
4. For child models without a list view, inherit ``MacrocycleChildMixin`` (or
   equivalent) and override ``get_parent_url()`` to return the parent's URL.
5. Add the model to ``FormContextMixinConventionTest`` in ``tests/test_views.py``
   (``models_and_kwargs`` for top-level, ``child_models_and_kwargs`` for children).
"""

import csv
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django import forms
from django.db import transaction
from django.db.models import QuerySet
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView, FormView, UpdateView, DeleteView
from django.urls import reverse

from .constants import APP_NAMESPACE
from .utils import create_default_cycles, m_to_km
from .enums import (
    GUI_SCHEMAS,
    LONG_SESSION_LABELS,
    SESSION_LABELS,
    SPORT_SHORT_LABELS,
    WorkoutStatus,
    WorkoutType,
    WorkoutSubtype,
    ViewType,
)
from .forms import (
    AccountForm,
    CreateCyclesForm,
    SummaryFilterForm,
    WorkoutForm,
    WorkoutFilterForm,
    MacrocycleForm,
    MesocycleForm,
    MicrocycleForm,
    DETAIL_FORMS,
)
from .models import (
    WEEKLY_UPLOAD_CAP,
    Workout,
    DetailBase,
    ActiveMacrocycle,
    Macrocycle,
    Mesocycle,
    Microcycle,
)


def _gui_schemas_json() -> str:
    return json.dumps({st.value: st.gui_schema for st in WorkoutSubtype})


def _gui_fields_from_detail(workout: Workout) -> dict:
    detail = workout.get_detail()
    if detail and isinstance(detail.additional_data, dict):
        return detail.additional_data.get("gui_fields", {})
    return {}


def _gui_fields_display(workout: Workout) -> list[dict]:
    gui_fields = _gui_fields_from_detail(workout)
    if not gui_fields or not workout.subtype:
        return []
    try:
        schema = WorkoutSubtype(workout.subtype).gui_schema
    except ValueError:
        schema = {}
    return [
        {"label": schema.get(key, {}).get("label", key), "value": value}
        for key, value in gui_fields.items()
    ]


def _detail_is_empty(detail_form: forms.ModelForm, gui_fields: dict) -> bool:
    if gui_fields:
        return False
    return all(not v for v in detail_form.cleaned_data.values())


def _collect_gui_fields(post_data: dict, subtype: WorkoutSubtype | None) -> dict:
    gui_fields = {}
    if not subtype or not subtype.gui_schema:
        return gui_fields
    schema = subtype.gui_schema
    for key in post_data:
        if key.startswith("gui-"):
            field_name = key[4:]
            value = post_data[key].strip()
            if not value:
                continue
            schema_entry = schema.get(field_name, {})
            if schema_entry.get("type") == "number":
                try:
                    value = float(value)
                    if value == int(value):
                        value = int(value)
                except (ValueError, TypeError):
                    pass
            gui_fields[field_name] = value
    return gui_fields


class PaginationMixin:
    """Adds a sliding page-range window to paginated list views."""

    pagination_window = 5

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)  # type: ignore[misc]
        page_obj = ctx.get("page_obj")
        if page_obj and page_obj.paginator.num_pages > 1:
            current = page_obj.number
            total = page_obj.paginator.num_pages
            w = self.pagination_window
            ideal_start = max(1, current - w // 2)
            clamped_end = min(total, ideal_start + w - 1)
            final_start = max(1, clamped_end - w + 1)
            ctx["page_range"] = range(final_start, clamped_end + 1)
        return ctx


class NoCacheMixin:
    """Adds Cache-Control: no-store to prevent browser from caching the response."""

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponseBase:
        response = super().dispatch(request, *args, **kwargs)  # type: ignore[misc]
        response["Cache-Control"] = "no-store"
        return response


class FormContextMixin:
    """Auto-resolves view_type, read_only, and CRUD URLs for form_base.html."""

    view_type = None  # set on concrete view classes

    def get_parent_url(self) -> str | None:
        """Return the parent detail URL for child models without a list view."""
        return None

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)  # type: ignore[misc]
        name = self.model._meta.model_name  # type: ignore[attr-defined]
        vt = self.view_type
        kw = self.kwargs  # type: ignore[attr-defined]

        ctx["view_type"] = vt
        ctx["read_only"] = vt in (ViewType.DETAIL, ViewType.DELETE)

        if vt == ViewType.DETAIL:
            ctx["edit_url"] = reverse(f"{APP_NAMESPACE}:edit_{name}", kwargs=kw)
            ctx["delete_url"] = reverse(f"{APP_NAMESPACE}:delete_{name}", kwargs=kw)
        elif vt in (ViewType.UPDATE, ViewType.DELETE):
            ctx["cancel_url"] = self.object.get_absolute_url()  # type: ignore[attr-defined]
        elif vt == ViewType.CREATE:
            parent_url = self.get_parent_url()
            ctx["cancel_url"] = parent_url or reverse(f"{APP_NAMESPACE}:{name}_list")

        return ctx

    def get_success_url(self) -> str:
        if self.view_type in (ViewType.CREATE, ViewType.UPDATE):
            return self.object.get_absolute_url()  # type: ignore[attr-defined]
        parent_url = self.get_parent_url()
        if parent_url:
            return parent_url
        name = self.model._meta.model_name  # type: ignore[attr-defined]
        return reverse(f"{APP_NAMESPACE}:{name}_list")


class BaseWorkoutListView(LoginRequiredMixin, NoCacheMixin, PaginationMixin, ListView):
    """Shared base for workout list views with filtering and pagination."""

    context_object_name = "workouts"
    paginate_by = 15

    def get_base_queryset(self) -> QuerySet:
        related = [
            model.get_related_name() for model in DetailBase._detail_registry.values()
        ]
        return (
            Workout.objects.filter(user=self.request.user)
            .select_related(*related)
            .order_by("-start_time")
        )

    def apply_filters(self, qs: QuerySet) -> QuerySet:
        if self.filter_form.is_valid():
            date_from = self.filter_form.cleaned_data.get("date_from")
            date_to = self.filter_form.cleaned_data.get("date_to")
            status = self.filter_form.cleaned_data.get("status")
            if date_from:
                qs = qs.filter(start_time__date__gte=date_from)
            if date_to:
                qs = qs.filter(start_time__date__lte=date_to)
            if status:
                qs = qs.filter(workout_status=status)
        return qs

    def get_queryset(self) -> QuerySet:
        qs = self.get_base_queryset()
        self.filter_form = WorkoutFilterForm(self.request.GET or None)
        qs = self.apply_filters(qs)
        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form

        context["show_filters"] = "show_filters" in self.request.GET

        params = self.request.GET.copy()
        params.pop("page", None)
        params.pop("show_filters", None)
        qs = params.urlencode()
        context["filter_querystring"] = qs
        context["page_prefix"] = f"{qs}&" if qs else ""
        return context


class PasswordResetView(auth_views.PasswordResetView):
    """Rate-limited password reset — max 3 requests/hour per IP."""

    RATE_LIMIT = 3
    COOLOFF_SECONDS = 3600

    def form_valid(self, form: forms.Form) -> HttpResponse:
        ip = self.request.META.get("REMOTE_ADDR", "")
        cache_key = f"password_reset_{ip}"
        attempts = cache.get(cache_key, 0)
        if attempts >= self.RATE_LIMIT:
            messages.error(
                self.request,
                "Too many password reset requests. Please try again later.",
            )
            return redirect("password_reset")
        cache.set(cache_key, attempts + 1, self.COOLOFF_SECONDS)
        return super().form_valid(form)


# ── Upload API ────────────────────────────────────────────────────────

_UPLOAD_SPORT_LABELS: dict[WorkoutSubtype, str] = {
    WorkoutSubtype.RUNNING: "Run",
    WorkoutSubtype.CYCLING: "Ride",
    WorkoutSubtype.SWIMMING: "Swim",
    WorkoutSubtype.SKIING: "Ski",
    WorkoutSubtype.WALKING: "Walk",
    WorkoutSubtype.STRENGTH: "Strength",
    WorkoutSubtype.MOBILITY: "Mobility",
    WorkoutSubtype.GENERIC: "Workout",
}


def _time_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "Morning"
    if 12 <= hour < 17:
        return "Afternoon"
    if 17 <= hour < 21:
        return "Evening"
    return "Night"


class UploadWorkoutsView(LoginRequiredMixin, TemplateView):
    """Page for uploading .fit files — parsing happens client-side in JS."""

    template_name = "workouts/upload_workouts.html"


class UploadWorkoutsAPIView(LoginRequiredMixin, View):
    """POST-only JSON endpoint for bulk workout upload.

    Accepts an array of workout objects, validates, deduplicates by
    (user, start_time, subtype), and creates Workout + detail records.
    Rate-limited to 20 requests/hour and 5000 workouts/week per user.
    """

    http_method_names = ["post"]
    RATE_LIMIT = 20
    COOLOFF_SECONDS = 3600
    MAX_PER_REQUEST = 500

    def _validate_item(  # pylint: disable=too-many-return-statements
        self, item: dict, i: int, user: Any
    ) -> dict | str:
        """Validate a single upload item. Returns parsed dict or error string."""
        if not isinstance(item, dict):
            return f"Item {i}: not a JSON object."

        subtype_value = item.get("subtype")
        try:
            subtype_enum = WorkoutSubtype(subtype_value)
        except (ValueError, KeyError):
            return f"Item {i}: invalid subtype '{subtype_value}'."

        start_time_str = item.get("start_time")
        if not start_time_str:
            return f"Item {i}: start_time is required."
        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return f"Item {i}: invalid start_time '{start_time_str}'."

        if Workout.objects.filter(
            user=user, start_time=start_time, subtype=subtype_value
        ).exists():
            return {"_duplicate": f"{start_time_str} ({subtype_enum.label}): duplicate"}

        gui_fields = item.get("gui_fields", {})
        if not isinstance(gui_fields, dict):
            return f"Item {i}: gui_fields must be a dict."
        schema = GUI_SCHEMAS.get(subtype_enum, {})
        unknown_keys = set(gui_fields) - set(schema)
        if unknown_keys:
            return f"Item {i}: unknown gui_fields: {', '.join(sorted(unknown_keys))}."

        name = item.get("name")
        if name is not None:
            if not isinstance(name, str):
                return f"Item {i}: name must be a string."
            if len(name) > 255:
                return f"Item {i}: name too long (max 255 chars)."

        return {
            "subtype_value": subtype_value,
            "subtype_enum": subtype_enum,
            "start_time": start_time,
            "gui_fields": gui_fields,
            "name": name,
            "raw": item,
        }

    @staticmethod
    def _create_workout(user: Any, parsed: dict) -> None:
        """Create a Workout + detail row from validated data."""
        subtype_enum = parsed["subtype_enum"]
        subtype_value = parsed["subtype_value"]
        start_time = parsed["start_time"]
        gui_fields = parsed["gui_fields"]
        item = parsed["raw"]
        workout_type = WorkoutType(subtype_enum.workout_type)

        name = parsed.get("name") or (
            f"{_time_of_day(start_time.hour)} "
            f"{_UPLOAD_SPORT_LABELS.get(subtype_enum, 'Workout')}"
        )
        workout = Workout.objects.create(
            user=user,
            name=name,
            start_time=start_time,
            workout_status=WorkoutStatus.COMPLETED,
            subtype=subtype_value,
        )

        detail_model = DetailBase._detail_registry.get(workout_type)
        if not detail_model:
            return
        detail_kwargs: dict[str, Any] = {"workout": workout}

        duration_seconds = item.get("duration_seconds")
        if duration_seconds is not None:
            try:
                detail_kwargs["duration"] = timedelta(seconds=float(duration_seconds))
            except (ValueError, TypeError):
                pass

        if workout_type == WorkoutType.AEROBIC:
            distance_meters = item.get("distance_meters")
            if distance_meters is not None:
                try:
                    detail_kwargs["distance"] = int(float(distance_meters))
                except (ValueError, TypeError):
                    pass

        if gui_fields:
            detail_kwargs["additional_data"] = {"gui_fields": gui_fields}

        detail_model.objects.create(**detail_kwargs)

    def post(
        self, request: HttpRequest
    ) -> JsonResponse:  # pylint: disable=too-many-branches
        # Hourly rate limit (cache-based)
        cache_key = f"fit_upload_{request.user.pk}"
        attempts = cache.get(cache_key, 0)
        if attempts >= self.RATE_LIMIT:
            return JsonResponse(
                {"error": "Rate limit exceeded. Please try again later."}, status=429
            )

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON."}, status=400)

        if not isinstance(data, list):
            return JsonResponse({"error": "Expected a JSON array."}, status=400)

        if len(data) > self.MAX_PER_REQUEST:
            return JsonResponse(
                {"error": f"Maximum {self.MAX_PER_REQUEST} workouts per request."},
                status=400,
            )

        # Weekly upload cap (DB-backed)
        user = request.user
        remaining = user.get_weekly_upload_remaining()
        if remaining <= 0:
            user.save(update_fields=["weekly_upload_count", "weekly_upload_reset"])
            next_monday = user.weekly_upload_reset + timedelta(days=7)
            return JsonResponse(
                {
                    "error": (
                        f"Weekly upload limit of {WEEKLY_UPLOAD_CAP} workouts reached. "
                        f"Resets on {next_monday}."
                    )
                },
                status=429,
            )

        created = 0
        skipped = 0
        skipped_details: list[str] = []
        errors: list[str] = []

        for i, item in enumerate(data):
            result = self._validate_item(item, i, request.user)
            if isinstance(result, str):
                errors.append(result)
                continue
            if "_duplicate" in result:
                skipped += 1
                skipped_details.append(result["_duplicate"])
                continue

            if user.weekly_upload_count + created >= WEEKLY_UPLOAD_CAP:
                errors.append(
                    f"Item {i}: weekly upload limit of {WEEKLY_UPLOAD_CAP} reached."
                )
                continue

            try:
                with transaction.atomic():
                    self._create_workout(request.user, result)
                    created += 1
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(f"Item {i}: {exc}")

        cache.set(cache_key, attempts + 1, self.COOLOFF_SECONDS)

        user.weekly_upload_count += created
        user.save(update_fields=["weekly_upload_count", "weekly_upload_reset"])

        return JsonResponse(
            {
                "created": created,
                "skipped": skipped,
                "skipped_details": skipped_details,
                "errors": errors,
            }
        )


class LoginView(auth_views.LoginView):
    """PRG login — redirects back with a message on invalid credentials."""

    def form_invalid(self, form: forms.Form) -> HttpResponseRedirect:
        if getattr(self.request, "axes_locked_out", False):
            messages.error(
                self.request,
                "Too many failed login attempts. Please try again later.",
            )
        else:
            messages.error(self.request, "Invalid username or password.")
        return redirect("login")


class IndexView(LoginRequiredMixin, View):
    """Landing page — redirects to the active plan summary or the plan list."""

    def get(self, request: HttpRequest) -> HttpResponseRedirect:
        try:
            active = ActiveMacrocycle.objects.get(user=request.user)
            return redirect(
                reverse(
                    f"{APP_NAMESPACE}:macrocycle_summary",
                    kwargs={"macro_pk": active.macrocycle.pk},
                )
            )
        except ActiveMacrocycle.DoesNotExist:
            return redirect(reverse(f"{APP_NAMESPACE}:macrocycle_list"))


SPECIALIZED_SUBTYPES: dict[WorkoutSubtype, str] = {
    WorkoutSubtype.RUNNING: "running",
}


class WorkoutListView(BaseWorkoutListView):
    """Workout list with optional activity filter and specialized column modes."""

    template_name = "workouts/workout_list.html"

    def get_base_queryset(self) -> QuerySet:
        activity = self.request.GET.get("activity", "")
        try:
            subtype = WorkoutSubtype(activity)
            wtype = subtype.workout_type
            detail_model = DetailBase._detail_registry.get(wtype)
            related = [detail_model.get_related_name()] if detail_model else []
        except ValueError:
            related = [
                model.get_related_name()
                for model in DetailBase._detail_registry.values()
            ]
        return (
            Workout.objects.filter(user=self.request.user)
            .select_related(*related)
            .order_by("-start_time")
        )

    def apply_filters(self, qs: QuerySet) -> QuerySet:
        qs = super().apply_filters(qs)
        if self.filter_form.is_valid():
            activity = self.filter_form.cleaned_data.get("activity")
            if activity:
                qs = qs.filter(subtype=activity)
        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        activity = ""
        if self.filter_form.is_valid():
            activity = self.filter_form.cleaned_data.get("activity", "")
        try:
            subtype = WorkoutSubtype(activity)
            view_mode = SPECIALIZED_SUBTYPES.get(subtype, "default")
        except ValueError:
            view_mode = "default"
        context["view_mode"] = view_mode
        context["page_heading"] = (
            WorkoutSubtype(activity).label if view_mode != "default" else "Workouts"
        )
        return context


# ── CSV Export ─────────────────────────────────────────────────────────

_CSV_INJECTION_CHARS = {"=", "+", "-", "@", "\t", "\r"}


def _sanitize_csv(value: str) -> str:
    """Prefix dangerous leading characters to prevent CSV formula injection."""
    if value and value[0] in _CSV_INJECTION_CHARS:
        return f"'{value}"
    return value


def _fmt_duration(detail: Any) -> str:
    if not detail or not detail.duration:
        return ""
    total = int(detail.duration.total_seconds())
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _build_csv_columns(
    workouts: list,
) -> list[tuple[str, Callable]]:
    """Build dynamic CSV columns based on workout types/subtypes present."""
    columns: list[tuple[str, Callable]] = [
        ("Date", lambda w, d, g: w.start_time.strftime("%Y-%m-%d")),
        ("Time", lambda w, d, g: w.start_time.strftime("%H:%M")),
        ("Activity", lambda w, d, g: WorkoutSubtype(w.subtype).label),
        ("Name", lambda w, d, g: w.name),
        ("Status", lambda w, d, g: w.workout_status.capitalize()),
        ("Description", lambda w, d, g: w.description or ""),
        ("Duration", lambda w, d, g: _fmt_duration(d)),
    ]

    present_types: set[WorkoutType] = set()
    present_subtypes: set[str] = set()
    for w in workouts:
        present_types.add(w.workout_type)
        present_subtypes.add(w.subtype)

    if WorkoutType.AEROBIC in present_types:
        columns += [
            (
                "Distance (km)",
                lambda w, d, g: (
                    f"{d.distance_km:.2f}"
                    if d and hasattr(d, "distance_km") and d.distance_km
                    else ""
                ),
            ),
            (
                "Pace (min/km)",
                lambda w, d, g: (
                    d.pace_display if d and hasattr(d, "pace_display") else ""
                ),
            ),
        ]
    if WorkoutType.STRENGTH in present_types:
        columns += [
            (
                "Sets",
                lambda w, d, g: (
                    str(d.num_sets)
                    if d and hasattr(d, "num_sets") and d.num_sets is not None
                    else ""
                ),
            ),
            (
                "Total Weight (kg)",
                lambda w, d, g: (
                    str(d.total_weight)
                    if d and hasattr(d, "total_weight") and d.total_weight is not None
                    else ""
                ),
            ),
        ]

    seen_keys: set[str] = set()
    for st in WorkoutSubtype:
        if st.value not in present_subtypes:
            continue
        for key, schema in GUI_SCHEMAS.get(st, {}).items():
            if key not in seen_keys:
                seen_keys.add(key)
                label = schema["label"]
                columns.append(
                    (
                        label,
                        lambda w, d, g, k=key: (
                            str(g.get(k, "")) if g.get(k) is not None else ""
                        ),
                    )
                )

    return columns


class ExportWorkoutsView(LoginRequiredMixin, View):
    """CSV export of user's workouts, with same filters as the workout list."""

    http_method_names = ["get"]
    RATE_LIMIT = 10
    COOLOFF_SECONDS = 3600
    MAX_ROWS = 5000

    def get(self, request: HttpRequest) -> HttpResponse:
        cache_key = f"workout_export_{request.user.pk}"
        attempts = cache.get(cache_key, 0)
        if attempts >= self.RATE_LIMIT:
            return HttpResponse(
                "Rate limit exceeded. Please try again later.", status=429
            )

        related = [
            model.get_related_name() for model in DetailBase._detail_registry.values()
        ]
        qs = (
            Workout.objects.filter(user=request.user)
            .select_related(*related)
            .order_by("-start_time")
        )

        filter_form = WorkoutFilterForm(request.GET or None)
        if filter_form.is_valid():
            date_from = filter_form.cleaned_data.get("date_from")
            date_to = filter_form.cleaned_data.get("date_to")
            status = filter_form.cleaned_data.get("status")
            activity = filter_form.cleaned_data.get("activity")
            if date_from:
                qs = qs.filter(start_time__date__gte=date_from)
            if date_to:
                qs = qs.filter(start_time__date__lte=date_to)
            if status:
                qs = qs.filter(workout_status=status)
            if activity:
                qs = qs.filter(subtype=activity)

        if qs.count() > self.MAX_ROWS:
            return HttpResponse(
                "Too many workouts to export. Use filters to narrow the selection.",
                status=400,
            )

        cache.set(cache_key, attempts + 1, self.COOLOFF_SECONDS)

        workouts = list(qs)
        columns = _build_csv_columns(workouts)

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="workouts_{date.today()}.csv"'
        )
        response.write("\ufeff")  # UTF-8 BOM for encoding detection
        response.write("sep=,\r\n")  # Excel delimiter hint
        writer = csv.writer(response)
        writer.writerow([header for header, _ in columns])

        for workout in workouts:
            detail = workout.get_detail()
            gui = workout.gui_fields
            writer.writerow(
                [_sanitize_csv(getter(workout, detail, gui)) for _, getter in columns]
            )

        return response


class WorkoutReadonlyFormMixin:
    """Builds read-only workout_form, detail_form, and gui_fields_display context."""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        workout = self.object
        workout_form = WorkoutForm(instance=workout, read_only=True)

        detail = workout.get_detail()
        detail_form = None
        if detail is not None:
            form_class = DETAIL_FORMS.get(workout.workout_type)
            if form_class:
                detail_form = form_class(instance=detail, read_only=True)  # type: ignore[call-arg]

        context.update(
            {
                "workout_form": workout_form,
                "detail_form": detail_form,
                "gui_fields_display": _gui_fields_display(workout),
            }
        )
        return context


class WorkoutDetailView(
    LoginRequiredMixin,
    NoCacheMixin,
    WorkoutReadonlyFormMixin,
    FormContextMixin,
    DetailView,
):
    """Read-only workout detail with type-specific fields and GUI fields."""

    model = Workout
    template_name = "workouts/workout_form.html"
    view_type = ViewType.DETAIL

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(user=self.request.user)


class WorkoutMutateMixin:
    """Shared logic for Create and Update workout views handling detail forms and GUI fields."""

    def get_workout_type(self) -> WorkoutType:
        if getattr(self, "object", None) and self.object.pk:
            return WorkoutType(self.object.workout_type)
        subtype_value = self.kwargs.get("subtype")
        if subtype_value is None:
            return WorkoutType.GENERIC
        try:
            return WorkoutSubtype(subtype_value).workout_type
        except ValueError as exc:
            raise Http404("Invalid subtype") from exc

    def _get_existing_detail(self) -> DetailBase | None:
        workout = getattr(self, "object", None)
        if workout and workout.pk:
            return workout.get_detail()
        return None

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        workout = getattr(self, "object", None)
        detail = self._get_existing_detail()

        if "detail_form" not in context:
            form_class = DETAIL_FORMS.get(self.get_workout_type())
            if form_class:
                if self.request.method == "POST":
                    context["detail_form"] = form_class(
                        self.request.POST, instance=detail, prefix="detail"
                    )
                else:
                    context["detail_form"] = form_class(
                        instance=detail, prefix="detail"
                    )

        context["workout_form"] = context.get("form")
        context["gui_schemas_json"] = _gui_schemas_json()
        if workout and workout.pk:
            context["gui_fields_json"] = json.dumps(_gui_fields_from_detail(workout))
        else:
            context["gui_fields_json"] = json.dumps({})
        return context

    def form_valid(self, form: forms.ModelForm) -> HttpResponse:
        detail = self._get_existing_detail()
        form_class = DETAIL_FORMS.get(self.get_workout_type())

        detail_form = None
        if form_class:
            detail_form = form_class(
                self.request.POST, instance=detail, prefix="detail"
            )
            if not detail_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(form=form, detail_form=detail_form)
                )

        try:
            subtype_enum = WorkoutSubtype(form.instance.subtype)
        except ValueError:
            subtype_enum = None
        gui_fields = _collect_gui_fields(self.request.POST, subtype_enum)

        with transaction.atomic():
            response = super().form_valid(form)
            if detail_form:
                empty = _detail_is_empty(detail_form, gui_fields)
                if detail is not None and empty:
                    detail.delete()
                elif not empty:
                    detail_obj = detail_form.save(commit=False)
                    if detail is None:
                        detail_obj.workout = self.object
                    if gui_fields:
                        detail_obj.additional_data = {
                            **detail_obj.additional_data,
                            "gui_fields": gui_fields,
                        }
                    detail_obj.save()

        return response


class WorkoutCreateView(
    LoginRequiredMixin, WorkoutMutateMixin, FormContextMixin, CreateView
):
    """Create workout with type from URL kwarg and subtype from query param."""

    model = Workout
    form_class = WorkoutForm
    template_name = "workouts/workout_form.html"
    view_type = ViewType.CREATE

    def get_form(
        self, form_class: type[forms.BaseForm] | None = None
    ) -> forms.BaseForm:
        form = super().get_form(form_class)
        subtype_value = self.kwargs["subtype"]
        try:
            WorkoutSubtype(subtype_value)
        except ValueError as exc:
            raise Http404("Invalid subtype") from exc
        form.instance.subtype = subtype_value
        form.instance.user = self.request.user
        return form


class WorkoutEditView(
    LoginRequiredMixin, WorkoutMutateMixin, FormContextMixin, UpdateView
):
    """Edit workout — creates/updates/deletes detail row as needed."""

    model = Workout
    form_class = WorkoutForm
    template_name = "workouts/workout_form.html"
    view_type = ViewType.UPDATE

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(user=self.request.user)


class WorkoutDeleteView(
    LoginRequiredMixin,
    NoCacheMixin,
    WorkoutReadonlyFormMixin,
    FormContextMixin,
    DeleteView,
):
    """Delete confirmation view showing read-only workout data."""

    model = Workout
    template_name = "workouts/workout_form.html"
    view_type = ViewType.DELETE

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(user=self.request.user)


# ==============================================================================
# PLANNING VIEWS
# ==============================================================================


class MacrocycleListView(LoginRequiredMixin, NoCacheMixin, PaginationMixin, ListView):
    """Paginated list of macrocycles ordered by start date (newest first)."""

    model = Macrocycle
    template_name = "workouts/macrocycle_list.html"
    context_object_name = "macrocycles"
    paginate_by = 15
    ordering = ["-start_date"]

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(user=self.request.user)


class MacrocycleDetailView(
    LoginRequiredMixin, NoCacheMixin, FormContextMixin, DetailView
):
    """Macrocycle detail with hydrated mesocycle table and active-plan toggle."""

    model = Macrocycle
    template_name = "workouts/macrocycle_form.html"
    pk_url_kwarg = "macro_pk"
    view_type = ViewType.DETAIL

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(user=self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = MacrocycleForm(instance=self.object, read_only=True)
        self.object.hydrate()
        ctx["mesocycles"] = self.object.hydrated_mesocycles
        ctx["create_meso_url"] = reverse(
            f"{APP_NAMESPACE}:create_mesocycle",
            kwargs={"macro_pk": self.object.pk},
        )
        ctx["create_defaults_url"] = reverse(
            f"{APP_NAMESPACE}:create_default_cycles",
            kwargs={"macro_pk": self.object.pk},
        )
        ctx["can_create_defaults"] = not self.object.hydrated_mesocycles
        if self.object.hydrated_mesocycles:
            ctx["summary_url"] = reverse(
                f"{APP_NAMESPACE}:macrocycle_summary",
                kwargs={"macro_pk": self.object.pk},
            )

        ctx["is_active"] = ActiveMacrocycle.objects.filter(
            user=self.request.user, macrocycle=self.object
        ).exists()
        ctx["toggle_active_url"] = reverse(
            f"{APP_NAMESPACE}:toggle_active",
            kwargs={"macro_pk": self.object.pk},
        )
        return ctx


class MacrocycleCreateDefaultCyclesView(LoginRequiredMixin, FormView):
    """Form view for auto-generating mesocycles and microcycles from duration targets."""

    form_class = CreateCyclesForm
    template_name = "workouts/create_cycles_form.html"

    def get_macrocycle(self) -> Macrocycle:
        if not hasattr(self, "_macrocycle"):
            self._macrocycle = get_object_or_404(
                Macrocycle, pk=self.kwargs["macro_pk"], user=self.request.user
            )
        return self._macrocycle

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        macro = self.get_macrocycle()
        if macro.mesocycles.exists():
            return self.render_to_response(self.get_context_data(has_mesocycles=True))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        macro = self.get_macrocycle()
        ctx["macrocycle"] = macro
        ctx["view_type"] = ViewType.CREATE
        ctx["read_only"] = False
        ctx["cancel_url"] = macro.get_absolute_url()
        ctx["submit_label"] = "Create"
        return ctx

    def form_valid(self, form: CreateCyclesForm) -> HttpResponse:
        macro = self.get_macrocycle()
        if macro.mesocycles.exists():
            return self.render_to_response(
                self.get_context_data(form=form, has_mesocycles=True)
            )
        create_default_cycles(
            macrocycle=macro,
            target_duration_days=form.cleaned_data["target_duration_days"],
            meso_duration_days=form.cleaned_data["meso_duration_days"],
            micro_duration_days=form.cleaned_data["micro_duration_days"],
        )
        return redirect(macro.get_absolute_url())


class ToggleActiveMacrocycleView(LoginRequiredMixin, View):
    """POST-only view that toggles a macrocycle as the user's active plan."""

    http_method_names = ["post"]

    def post(self, request: HttpRequest, macro_pk: int) -> HttpResponseRedirect:
        macro = get_object_or_404(Macrocycle, pk=macro_pk, user=request.user)
        active = ActiveMacrocycle.objects.filter(user=request.user)
        if active.filter(macrocycle=macro).exists():
            active.filter(macrocycle=macro).delete()
        else:
            ActiveMacrocycle.objects.update_or_create(
                user=request.user, defaults={"macrocycle": macro}
            )
        return redirect(macro.get_absolute_url())


def _empty_actuals() -> dict[str, int]:
    return {
        "sessions": 0,
        "sport_distance": 0,
        "long_distance": 0,
        "sport_load": 0,
        "cross_sessions": 0,
        "strength_sessions": 0,
        "total_load": 0,
    }


def _find_bucket(w_date: date, buckets: list[tuple[date, date, int]]) -> int | None:
    for start, end, micro_pk in buckets:
        if start <= w_date <= end:
            return micro_pk
    return None


def _aggregate_workouts(
    overall_start: date,
    overall_end: date,
    micro_entries: list[dict],
    user,
    primary_sport: str,
    statuses: set[str] | None = None,
) -> dict[int, dict[str, int]]:
    result = defaultdict(_empty_actuals)
    if statuses is not None and not statuses:
        return dict(result)
    workouts = Workout.objects.prefetch_related(
        "aerobic_details", "strength_details", "generic_details"
    ).filter(
        user=user,
        start_time__date__gte=overall_start,
        start_time__date__lte=overall_end,
    )
    if statuses is not None:
        workouts = workouts.filter(workout_status__in=statuses)

    buckets = [(e["start"], e["end"], e["pk"]) for e in micro_entries]

    for w in workouts:
        w_date = w.start_time.date()
        micro_pk = _find_bucket(w_date, buckets)
        if micro_pk is None:
            continue

        actuals = result[micro_pk]
        detail = w.get_detail()
        load = 0
        if detail:
            gui = (detail.additional_data or {}).get("gui_fields", {})
            load = gui.get("load_garmin", 0) or 0

        actuals["total_load"] += load

        if w.subtype == primary_sport:
            actuals["sessions"] += 1
            actuals["sport_load"] += load
            distance = 0
            try:
                ad = w.aerobic_details
                distance = ad.distance or 0
            except Workout.aerobic_details.RelatedObjectDoesNotExist:  # type: ignore[attr-defined]
                pass
            actuals["sport_distance"] += distance
            if distance > actuals["long_distance"]:
                actuals["long_distance"] = distance
        elif w.workout_type == WorkoutType.STRENGTH:
            actuals["strength_sessions"] += 1
        else:
            actuals["cross_sessions"] += 1

    return dict(result)


def _build_summary_rows(
    macro: Macrocycle, user, statuses: set[str] | None = None
) -> list[dict]:
    """Build per-microcycle summary rows with planned goals and actual workout stats."""
    rows: list[dict] = []
    micro_entries = []

    for meso in macro.hydrated_mesocycles:
        for micro in meso.hydrated_microcycles:
            micro_entries.append(
                {
                    "pk": micro.pk,
                    "start": micro.start_date,
                    "end": micro.end_date,
                }
            )

    if not micro_entries:
        return rows

    overall_start = micro_entries[0]["start"]
    overall_end = micro_entries[-1]["end"]
    actuals_by_micro = _aggregate_workouts(
        overall_start,
        overall_end,
        micro_entries,
        user,
        macro.primary_sport,
        statuses=statuses,
    )

    workout_list_url = reverse(f"{APP_NAMESPACE}:workout_list")

    for meso in macro.hydrated_mesocycles:
        meso_first = True
        meso_micro_count = len(meso.hydrated_microcycles)
        for micro in meso.hydrated_microcycles:
            actuals = actuals_by_micro.get(micro.pk, _empty_actuals())
            date_from = micro.start_date.isoformat()
            date_to = micro.end_date.isoformat()
            rows.append(
                {
                    "micro_pk": micro.pk,
                    "start_date": micro.start_date,
                    "meso_pk": meso.pk,
                    "meso_display": meso.get_meso_type_display(),
                    "meso_url": meso.get_absolute_url(),
                    "meso_first_row": meso_first,
                    "meso_rowspan": meso_micro_count if meso_first else 0,
                    "micro_type_display": micro.get_micro_type_display(),
                    "micro_url": micro.get_absolute_url(),
                    "workouts_url": (
                        f"{workout_list_url}"
                        f"?date_from={date_from}&date_to={date_to}"
                    ),
                    "comment": micro.comment,
                    "planned_distance_km": micro.planned_distance_km,
                    "planned_long_km": micro.planned_long_distance_km,
                    "planned_sessions": micro.planned_sessions,
                    "planned_cross_sessions": micro.planned_cross_sessions,
                    "planned_strength_sessions": micro.planned_strength_sessions,
                    "sport_distance": m_to_km(actuals["sport_distance"]) or 0,
                    "long_distance": m_to_km(actuals["long_distance"]) or 0,
                    **{
                        k: v
                        for k, v in actuals.items()
                        if k not in ("sport_distance", "long_distance")
                    },
                }
            )
            meso_first = False

    return rows


def _summary_col_labels(sport: WorkoutSubtype) -> dict[str, str]:
    """Return sport-specific column labels for the summary table."""
    short = SPORT_SHORT_LABELS[sport]
    return {
        "col_sessions": SESSION_LABELS[sport],
        "col_distance": f"{short} dst",
        "col_long": LONG_SESSION_LABELS[sport],
        "col_sport_load": f"{short} load",
    }


class MacrocycleSummaryView(LoginRequiredMixin, NoCacheMixin, DetailView):
    """Read-only overview table comparing planned goals vs actual workout stats per microcycle."""

    model = Macrocycle
    pk_url_kwarg = "macro_pk"
    template_name = "workouts/macrocycle_summary.html"

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(user=self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        macro = self.object
        macro.hydrate()
        sport = WorkoutSubtype(macro.primary_sport)
        ctx.update(_summary_col_labels(sport))

        is_filtered = "filtered" in self.request.GET
        form = SummaryFilterForm(self.request.GET if is_filtered else None)
        if is_filtered and form.is_valid():
            visible_cols = set(form.cleaned_data.get("cols") or [])
            statuses_filter = set(form.cleaned_data.get("statuses") or [])
        else:
            visible_cols = set(SummaryFilterForm.ALL_COLS)
            statuses_filter = None

        ctx["rows"] = _build_summary_rows(
            macro, self.request.user, statuses=statuses_filter
        )

        params = self.request.GET.copy()
        params.pop("show_filters", None)

        planned_colspan = 5 + sum(
            1 for k in ("comment", "x", "str") if k in visible_cols
        )
        actual_colspan = (
            3
            + sum(1 for k in ("x", "str") if k in visible_cols)
            + (2 if "load" in visible_cols else 0)
        )

        ctx["filter_form"] = form
        ctx["show_filters"] = "show_filters" in self.request.GET
        ctx["filter_querystring"] = params.urlencode()
        ctx["visible_cols"] = visible_cols
        ctx["planned_colspan"] = planned_colspan
        ctx["actual_colspan"] = actual_colspan
        return ctx


class ExportPlanSummaryView(LoginRequiredMixin, View):
    """CSV export of a macrocycle's summary table."""

    http_method_names = ["get"]
    RATE_LIMIT = 10
    COOLOFF_SECONDS = 3600

    def get(self, request: HttpRequest, macro_pk: int) -> HttpResponse:
        cache_key = f"plan_export_{request.user.pk}"
        attempts = cache.get(cache_key, 0)
        if attempts >= self.RATE_LIMIT:
            return HttpResponse(
                "Rate limit exceeded. Please try again later.", status=429
            )

        macro = get_object_or_404(Macrocycle, pk=macro_pk, user=request.user)
        macro.hydrate()
        sport = WorkoutSubtype(macro.primary_sport)
        labels = _summary_col_labels(sport)
        rows = _build_summary_rows(macro, request.user)

        cache.set(cache_key, attempts + 1, self.COOLOFF_SECONDS)

        col_sessions = labels["col_sessions"]
        col_distance = labels["col_distance"]
        col_long = labels["col_long"]
        col_sport_load = labels["col_sport_load"]

        headers = [
            "Mesocycle",
            "Start date",
            "Type",
            "Comment",
            f"Goal - {col_sessions}",
            f"Goal - {col_distance}",
            f"Goal - {col_long}",
            "Goal - X",
            "Goal - Str",
            col_sessions,
            col_distance,
            col_long,
            col_sport_load,
            "Nr X",
            "Nr str",
            "Tot load",
        ]

        def _fmt(val, decimals=1):
            if not val:
                return ""
            if isinstance(val, float):
                return f"{val:.{decimals}f}".rstrip("0").rstrip(".")
            return str(val)

        safe_name = "".join(
            c if c.isalnum() or c in " _-" else "_" for c in macro.name
        ).strip()

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="plan_{safe_name}_{date.today()}.csv"'
        )
        response.write("\ufeff")
        response.write("sep=,\r\n")
        writer = csv.writer(response)
        writer.writerow(headers)

        for row in rows:
            writer.writerow(
                [
                    _sanitize_csv(v)
                    for v in [
                        row["meso_display"],
                        row["start_date"].strftime("%Y-%m-%d"),
                        row["micro_type_display"],
                        row["comment"],
                        _fmt(row["planned_sessions"]),
                        _fmt(row["planned_distance_km"]),
                        _fmt(row["planned_long_km"]),
                        _fmt(row["planned_cross_sessions"]),
                        _fmt(row["planned_strength_sessions"]),
                        _fmt(row["sessions"]),
                        _fmt(row["sport_distance"]),
                        _fmt(row["long_distance"]),
                        _fmt(row["sport_load"]),
                        _fmt(row["cross_sessions"]),
                        _fmt(row["strength_sessions"]),
                        _fmt(row["total_load"]),
                    ]
                ]
            )

        return response


class MacrocycleCreateView(LoginRequiredMixin, FormContextMixin, CreateView):
    """Create a new macrocycle for the current user."""

    model = Macrocycle
    form_class = MacrocycleForm
    template_name = "workouts/macrocycle_form.html"
    view_type = ViewType.CREATE

    def get_form(
        self, form_class: type[forms.BaseForm] | None = None
    ) -> forms.BaseForm:
        form = super().get_form(form_class)
        form.instance.user = self.request.user
        return form


class MacrocycleEditView(LoginRequiredMixin, FormContextMixin, UpdateView):
    """Edit an existing macrocycle."""

    model = Macrocycle
    form_class = MacrocycleForm
    template_name = "workouts/macrocycle_form.html"
    pk_url_kwarg = "macro_pk"
    view_type = ViewType.UPDATE

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(user=self.request.user)


class MacrocycleDeleteView(
    LoginRequiredMixin, NoCacheMixin, FormContextMixin, DeleteView
):
    """Delete confirmation for a macrocycle (cascades to meso/microcycles)."""

    model = Macrocycle
    template_name = "workouts/macrocycle_form.html"
    pk_url_kwarg = "macro_pk"
    view_type = ViewType.DELETE

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(user=self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = MacrocycleForm(instance=self.object, read_only=True)
        return ctx


class MacrocycleChildMixin:
    """Resolves parent macrocycle from URL kwargs and scopes querysets."""

    def get_macrocycle(self) -> Macrocycle:
        if not hasattr(self, "_macrocycle"):
            self._macrocycle = get_object_or_404(
                Macrocycle, pk=self.kwargs["macro_pk"], user=self.request.user
            )
        return self._macrocycle

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(macrocycle=self.get_macrocycle())

    def get_parent_url(self) -> str:
        return self.get_macrocycle().get_absolute_url()


class MesocycleDetailView(
    LoginRequiredMixin, NoCacheMixin, MacrocycleChildMixin, FormContextMixin, DetailView
):
    """Mesocycle detail with hydrated microcycle table."""

    model = Mesocycle
    template_name = "workouts/mesocycle_form.html"
    pk_url_kwarg = "meso_pk"
    view_type = ViewType.DETAIL

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = MesocycleForm(instance=self.object, read_only=True)

        macro = self.get_macrocycle()
        macro.hydrate()
        hydrated_meso = next(
            (m for m in macro.hydrated_mesocycles if m.pk == self.object.pk), None
        )
        ctx["microcycles"] = hydrated_meso.hydrated_microcycles if hydrated_meso else []
        ctx["create_micro_url"] = reverse(
            f"{APP_NAMESPACE}:create_microcycle",
            kwargs={"macro_pk": macro.pk, "meso_pk": self.object.pk},
        )
        return ctx


class MesocycleCreateView(
    LoginRequiredMixin, MacrocycleChildMixin, FormContextMixin, CreateView
):
    """Create a mesocycle within a macrocycle."""

    model = Mesocycle
    form_class = MesocycleForm
    template_name = "workouts/mesocycle_form.html"
    view_type = ViewType.CREATE

    def get_form(
        self, form_class: type[forms.BaseForm] | None = None
    ) -> forms.BaseForm:
        form = super().get_form(form_class)
        form.instance.macrocycle = self.get_macrocycle()
        return form


class MesocycleEditView(
    LoginRequiredMixin, MacrocycleChildMixin, FormContextMixin, UpdateView
):
    """Edit a mesocycle."""

    model = Mesocycle
    form_class = MesocycleForm
    template_name = "workouts/mesocycle_form.html"
    pk_url_kwarg = "meso_pk"
    view_type = ViewType.UPDATE


class MesocycleDeleteView(
    LoginRequiredMixin, NoCacheMixin, MacrocycleChildMixin, FormContextMixin, DeleteView
):
    """Delete confirmation for a mesocycle (cascades to microcycles, reorders siblings)."""

    model = Mesocycle
    template_name = "workouts/mesocycle_form.html"
    pk_url_kwarg = "meso_pk"
    view_type = ViewType.DELETE

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = MesocycleForm(instance=self.object, read_only=True)
        return ctx


class MesocycleChildMixin:
    """Resolves parent mesocycle from URL kwargs and scopes querysets."""

    def get_mesocycle(self) -> Mesocycle:
        if not hasattr(self, "_mesocycle"):
            self._mesocycle = get_object_or_404(
                Mesocycle,
                macrocycle__pk=self.kwargs["macro_pk"],
                macrocycle__user=self.request.user,
                pk=self.kwargs["meso_pk"],
            )
        return self._mesocycle

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(mesocycle=self.get_mesocycle())

    def get_parent_url(self) -> str:
        return self.get_mesocycle().get_absolute_url()


class MicrocycleDetailView(
    LoginRequiredMixin, NoCacheMixin, MesocycleChildMixin, FormContextMixin, DetailView
):
    """Read-only microcycle detail."""

    model = Microcycle
    template_name = "workouts/microcycle_form.html"
    pk_url_kwarg = "micro_pk"
    view_type = ViewType.DETAIL

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = MicrocycleForm(instance=self.object, read_only=True)
        return ctx


class MicrocycleCreateView(
    LoginRequiredMixin, MesocycleChildMixin, FormContextMixin, CreateView
):
    """Create a microcycle within a mesocycle."""

    model = Microcycle
    form_class = MicrocycleForm
    template_name = "workouts/microcycle_form.html"
    view_type = ViewType.CREATE

    def get_form(
        self, form_class: type[forms.BaseForm] | None = None
    ) -> forms.BaseForm:
        form = super().get_form(form_class)
        form.instance.mesocycle = self.get_mesocycle()
        return form


class MicrocycleEditView(
    LoginRequiredMixin, MesocycleChildMixin, FormContextMixin, UpdateView
):
    """Edit a microcycle."""

    model = Microcycle
    form_class = MicrocycleForm
    template_name = "workouts/microcycle_form.html"
    pk_url_kwarg = "micro_pk"
    view_type = ViewType.UPDATE


class MicrocycleDeleteView(
    LoginRequiredMixin, NoCacheMixin, MesocycleChildMixin, FormContextMixin, DeleteView
):
    """Delete confirmation for a microcycle (reorders siblings)."""

    model = Microcycle
    template_name = "workouts/microcycle_form.html"
    pk_url_kwarg = "micro_pk"
    view_type = ViewType.DELETE

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = MicrocycleForm(instance=self.object, read_only=True)
        return ctx


# ── Account Views ──────────────────────────────────────────────────────

User = get_user_model()


class AccountDetailView(LoginRequiredMixin, NoCacheMixin, DetailView):
    """Read-only account detail showing user profile fields."""

    model = User
    template_name = "workouts/account_form.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = AccountForm(instance=self.request.user, read_only=True)
        ctx["view_type"] = ViewType.DETAIL
        ctx["read_only"] = True
        ctx["edit_url"] = reverse(f"{APP_NAMESPACE}:edit_account")
        ctx["delete_url"] = reverse(f"{APP_NAMESPACE}:delete_account")
        return ctx


class AccountEditView(LoginRequiredMixin, UpdateView):
    """Edit account fields with current password verification."""

    model = User
    form_class = AccountForm
    template_name = "workouts/account_form.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["view_type"] = ViewType.UPDATE
        ctx["read_only"] = False
        ctx["cancel_url"] = reverse(f"{APP_NAMESPACE}:account_detail")
        return ctx

    def form_valid(self, form: AccountForm) -> HttpResponse:
        user = form.save(commit=False)
        new_password = form.cleaned_data.get("new_password")
        if new_password:
            user.set_password(new_password)
        user.save()
        if new_password:
            update_session_auth_hash(self.request, user)
        return redirect(reverse(f"{APP_NAMESPACE}:account_detail"))


class AccountDeleteView(LoginRequiredMixin, NoCacheMixin, DeleteView):
    """Account deletion with modal confirmation dialog."""

    model = User
    template_name = "workouts/account_form.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = AccountForm(instance=self.request.user, read_only=True)
        ctx["view_type"] = ViewType.DELETE
        ctx["read_only"] = True
        ctx["cancel_url"] = reverse(f"{APP_NAMESPACE}:account_detail")
        return ctx

    def form_valid(self, form: forms.Form) -> HttpResponse:
        user = self.request.user
        logout(self.request)
        user.delete()
        return redirect("login")
