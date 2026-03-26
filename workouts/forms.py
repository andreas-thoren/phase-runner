"""Forms for workout, periodization, and filter views.

Mixins
------
ReadOnlyFormMixin
    Disables all fields when ``read_only=True``; otherwise sets autofocus
    on the first field. Used by all model forms (detail/delete → read-only,
    create/edit → autofocus).

KmFormMixin
    Auto-converts model fields stored in meters to/from km in the form.
    Used by AerobicDetailsForm and MicrocycleForm for distance inputs.

Form → Detail mapping
---------------------
``DETAIL_FORMS`` maps each WorkoutType to its detail form class.
Views use this dict to instantiate the correct detail form for a workout.
"""

from typing import Any

from django import forms
from .models import (
    Workout,
    WorkoutSubtype,
    AerobicDetails,
    StrengthDetails,
    GenericDetails,
    Macrocycle,
    Mesocycle,
    Microcycle,
)
from .enums import WorkoutStatus, WorkoutType
from .utils import m_to_km, km_to_m


class ReadOnlyFormMixin:
    """Disables all fields when read_only=True, sets autofocus otherwise."""

    fields: dict[str, forms.Field]

    def __init__(self, *args: Any, read_only: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if read_only:
            for field in self.fields.values():
                field.disabled = True
        else:
            first_field = next(iter(self.fields.values()))
            first_field.widget.attrs["autofocus"] = True


class KmFormMixin:
    """Auto-converts model fields stored in meters to/from km in the form.

    Subclasses set ``_km_fields``: a tuple of field names whose model values
    are in meters but should be displayed and accepted as kilometres.
    Each field must be declared as a ``FloatField`` on the form.
    """

    _km_fields: tuple[str, ...] = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for field_name in self._km_fields:
                value = getattr(self.instance, field_name, None)
                km = m_to_km(value)
                if km is not None:
                    self.initial[field_name] = km

    def clean(self) -> dict:
        cleaned = super().clean()
        for field_name in self._km_fields:
            if field_name in cleaned:
                cleaned[field_name] = km_to_m(cleaned[field_name])
        return cleaned


class WorkoutForm(ReadOnlyFormMixin, forms.ModelForm):
    """Core workout fields (name, time, status, description)."""

    class Meta:
        model = Workout
        fields = ("name", "start_time", "workout_status", "description")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2, "cols": 25}),
        }


class AerobicDetailsForm(KmFormMixin, ReadOnlyFormMixin, forms.ModelForm):
    """Aerobic detail form with distance input in km (stored as meters)."""

    _km_fields = ("distance",)
    distance = forms.FloatField(label="Distance (km)", required=False)

    class Meta:
        model = AerobicDetails
        fields = ("duration", "distance", "load")


class StrengthDetailsForm(ReadOnlyFormMixin, forms.ModelForm):
    """Strength detail form (duration, sets, weight, load)."""

    class Meta:
        model = StrengthDetails
        fields = ("duration", "num_sets", "total_weight", "load")


class GenericDetailsForm(ReadOnlyFormMixin, forms.ModelForm):
    """Generic detail form (duration and load only)."""

    class Meta:
        model = GenericDetails
        fields = ("duration", "load")


DETAIL_FORMS: dict[WorkoutType, type[forms.ModelForm]] = {
    WorkoutType.AEROBIC: AerobicDetailsForm,
    WorkoutType.STRENGTH: StrengthDetailsForm,
    WorkoutType.GENERIC: GenericDetailsForm,
}


class MacrocycleForm(ReadOnlyFormMixin, forms.ModelForm):
    """Macrocycle CRUD form (name, start date, description)."""

    class Meta:
        model = Macrocycle
        fields = (
            "name",
            "start_date",
            "description",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2, "cols": 25}),
        }


class CreateCyclesForm(forms.Form):
    """Non-model form for auto-generating mesocycles and microcycles."""

    target_duration_days = forms.IntegerField(
        label="Target duration (days)",
        initial=84,
        min_value=1,
    )
    meso_duration_days = forms.IntegerField(
        label="Mesocycle duration (days)",
        initial=28,
        min_value=1,
    )
    micro_duration_days = forms.IntegerField(
        label="Microcycle duration (days)",
        initial=7,
        min_value=1,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        first_field = next(iter(self.fields.values()))
        first_field.widget.attrs["autofocus"] = True

    def clean(self) -> dict:
        cleaned = super().clean()
        meso = cleaned.get("meso_duration_days")
        micro = cleaned.get("micro_duration_days")
        if meso is not None and micro is not None and meso < micro:
            raise forms.ValidationError(
                {
                    "meso_duration_days": (
                        "Mesocycle duration must be >= microcycle duration "
                        f"({micro} days)."
                    )
                }
            )
        return cleaned


class MesocycleForm(ReadOnlyFormMixin, forms.ModelForm):
    """Mesocycle CRUD form (type and comment)."""

    class Meta:
        model = Mesocycle
        fields = ("meso_type", "comment")
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 2, "cols": 25}),
        }


class MicrocycleForm(KmFormMixin, ReadOnlyFormMixin, forms.ModelForm):
    """Microcycle CRUD form with distance inputs in km (stored as meters)."""

    _km_fields = ("planned_distance", "planned_long_run_distance")
    planned_distance = forms.FloatField(label="Planned distance (km)", required=False)
    planned_long_run_distance = forms.FloatField(
        label="Planned long run (km)", required=False
    )

    class Meta:
        model = Microcycle
        fields = (
            "micro_type",
            "duration_days",
            "comment",
            "planned_num_runs",
            "planned_distance",
            "planned_long_run_distance",
            "planned_strength_sessions",
            "planned_cross_sessions",
        )
        labels = {
            "duration_days": "Duration (days)",
            "planned_num_runs": "Planned runs",
            "planned_strength_sessions": "Planned strength sessions",
            "planned_cross_sessions": "Planned X-sessions",
        }


class WorkoutFilterForm(forms.Form):
    """Filter bar form for workout list views (date range, status, activity)."""

    date_from = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    status = forms.ChoiceField(
        choices=[("", "All statuses")] + WorkoutStatus.choices(),
        required=False,
    )
    activity = forms.ModelChoiceField(
        queryset=WorkoutSubtype.objects.order_by("name"),
        required=False,
        empty_label="All activities",
        to_field_name="slug",
    )
