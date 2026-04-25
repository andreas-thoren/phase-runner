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
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import (
    Workout,
    AerobicDetails,
    StrengthDetails,
    GenericDetails,
    Macrocycle,
    Mesocycle,
    Microcycle,
)

User = get_user_model()
from .enums import (
    EXTRA_SUMMARY_COLS,
    SPORT_SHORT_LABELS,
    WorkoutStatus,
    WorkoutSubtype,
    WorkoutType,
)
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
        fields = ("duration", "distance")


class StrengthDetailsForm(ReadOnlyFormMixin, forms.ModelForm):
    """Strength detail form (duration, sets, weight)."""

    class Meta:
        model = StrengthDetails
        fields = ("duration", "num_sets", "total_weight")


class GenericDetailsForm(ReadOnlyFormMixin, forms.ModelForm):
    """Generic detail form (duration only)."""

    class Meta:
        model = GenericDetails
        fields = ("duration",)


DETAIL_FORMS: dict[WorkoutType, type[forms.ModelForm]] = {
    WorkoutType.AEROBIC: AerobicDetailsForm,
    WorkoutType.STRENGTH: StrengthDetailsForm,
    WorkoutType.GENERIC: GenericDetailsForm,
}


class MacrocycleForm(ReadOnlyFormMixin, forms.ModelForm):
    """Macrocycle CRUD form (name, primary sport, start date, description)."""

    class Meta:
        model = Macrocycle
        fields = (
            "name",
            "primary_sport",
            "start_date",
            "description",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2, "cols": 25}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["primary_sport"].disabled = True


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

    _km_fields = ("planned_distance", "planned_long_distance")
    planned_distance = forms.FloatField(label="Planned distance (km)", required=False)
    planned_long_distance = forms.FloatField(
        label="Planned long session (km)", required=False
    )

    class Meta:
        model = Microcycle
        fields = (
            "micro_type",
            "duration_days",
            "comment",
            "planned_sessions",
            "planned_distance",
            "planned_long_distance",
            "planned_strength_sessions",
            "planned_cross_sessions",
        )
        labels = {
            "duration_days": "Duration (days)",
            "planned_sessions": "Planned sessions",
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
    activity = forms.ChoiceField(
        choices=[("", "All activities")] + WorkoutSubtype.choices(),
        required=False,
    )


class SummaryFilterForm(forms.Form):
    """Column-visibility and status filter for the macrocycle summary view.

    `cols` choices are sport-aware: universal columns are extended with any
    sport-specific extras from `EXTRA_SUMMARY_COLS` based on the macrocycle's
    primary_sport (passed in as a kwarg).
    """

    # Filter checkboxes render in choice order. Sport extras slot between the
    # sport-specific load checkbox and the cross/strength/total-load group:
    # comment → sport load → sport extras (e.g. zones) → x → str → total load.
    UNIVERSAL_COL_CHOICES_POST = [
        ("x", "X"),
        ("str", "Str"),
        ("totload", "Total load"),
    ]
    ALL_STATUSES = {value for value, _ in WorkoutStatus.choices()}

    statuses = forms.MultipleChoiceField(
        choices=WorkoutStatus.choices(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        initial=[value for value, _ in WorkoutStatus.choices()],
    )

    def __init__(
        self, *args: Any, primary_sport: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        sport_load_label = "Sport load"
        extras: list[tuple[str, str]] = []
        if primary_sport:
            subtype = WorkoutSubtype(primary_sport)
            sport_load_label = f"{SPORT_SHORT_LABELS[subtype]} load"
            extras = EXTRA_SUMMARY_COLS.get(subtype, [])
        pre = [
            ("comment", "Comment"),
            ("sportload", sport_load_label),
        ]
        col_choices = pre + extras + self.UNIVERSAL_COL_CHOICES_POST
        self.fields["cols"] = forms.MultipleChoiceField(
            choices=col_choices,
            required=False,
            widget=forms.CheckboxSelectMultiple,
            initial=[k for k, _ in col_choices],
        )
        self.all_cols: set[str] = {k for k, _ in col_choices}


class AccountForm(ReadOnlyFormMixin, forms.ModelForm):
    """Account settings form with optional password change."""

    current_password = forms.CharField(widget=forms.PasswordInput, required=False)
    new_password = forms.CharField(widget=forms.PasswordInput, required=False)
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args: Any, read_only: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, read_only=read_only, **kwargs)
        if read_only:
            del self.fields["current_password"]
            del self.fields["new_password"]
            del self.fields["confirm_password"]

    def clean_current_password(self) -> str:
        password = self.cleaned_data.get("current_password", "")
        if not password:
            raise forms.ValidationError("Current password is required to save changes.")
        if not self.instance.check_password(password):
            raise forms.ValidationError("Current password is incorrect.")
        return password

    def clean_email(self) -> str:
        email = self.cleaned_data.get("email", "")
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self) -> dict:
        cleaned = super().clean()
        new_pw = cleaned.get("new_password", "")
        confirm_pw = cleaned.get("confirm_password", "")
        if new_pw or confirm_pw:
            if new_pw != confirm_pw:
                raise forms.ValidationError(
                    {"confirm_password": "Passwords do not match."}
                )
            try:
                validate_password(new_pw, self.instance)
            except forms.ValidationError as e:
                self.add_error("new_password", e)
        return cleaned
