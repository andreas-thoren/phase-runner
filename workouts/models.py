"""
Models for the workouts app.

Workout is the core model with a mandatory subtype (WorkoutSubtype enum).
Optional detail models (OneToOne) add type-specific fields. The detail
type is identified by a WorkoutType enum on a simple base class that
auto-registers subclasses. The workout_type is derived from the subtype
via SUBTYPE_TYPE_MAP.

Periodization models (Macrocycle → Mesocycle → Microcycle) represent
training plan structure. Dates are computed bottom-up from Microcycle
duration_days — use Macrocycle.hydrate() before accessing start/end dates.

Mixins:
    OrderMixin          — abstract mixin ensuring gap-free ordering on delete

Models:
    Workout             — user, name, start_time, description, status, subtype
    DetailBase          — abstract base with auto-registration + shared fields (duration)
    AerobicDetails      — concrete, OneToOne → Workout, adds distance + speed/pace
    StrengthDetails     — concrete, OneToOne → Workout
    GenericDetails      — concrete, OneToOne → Workout (duration only)
    Macrocycle          — top-level training block (start_date + computed end_date)
    Mesocycle           — ordered phase within a macrocycle (base, build, peak, …)
    Microcycle          — ordered cycle within a mesocycle (duration_days is source of truth)
    ActiveMacrocycle    — one-per-user mapping to the currently active macrocycle
"""

from datetime import timedelta
from datetime import date
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Max, Prefetch
from django.urls import reverse
from django.utils import timezone

from .enums import (
    AEROBIC_CHOICES,
    SUBTYPE_TYPE_MAP,
    MesocycleType,
    MicrocycleType,
    WorkoutStatus,
    WorkoutSubtype,
    WorkoutType,
)
from .utils import GreaterThanDurationValidator, HydratedProperty, m_to_km

# ==============================================================================
# USER
# ==============================================================================


WEEKLY_UPLOAD_CAP = 5000


class User(AbstractUser):
    """Custom user with unique, required email."""

    email = models.EmailField(unique=True, blank=False)
    weekly_upload_count = models.PositiveIntegerField(default=0)
    weekly_upload_reset = models.DateField(null=True, blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(email=""),
                name="user_email_required",
            ),
        ]

    def get_weekly_upload_remaining(self) -> int:
        """Return remaining upload capacity for this calendar week.

        Resets the counter when a new week (Monday 00:00) has started.
        Does NOT save — caller must persist changes.
        """
        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        if self.weekly_upload_reset is None or self.weekly_upload_reset < this_monday:
            self.weekly_upload_count = 0
            self.weekly_upload_reset = this_monday
        return WEEKLY_UPLOAD_CAP - self.weekly_upload_count


# ==============================================================================
# MIXINS
# ==============================================================================


class OrderMixin(models.Model):
    """Mixin that ensures gap-free ordering among siblings on delete.

    Subclasses must set ``_order_parent_field`` to the FK field name that
    scopes the ordering (e.g. ``"macrocycle"`` for Mesocycle).
    """

    _order_parent_field: str

    def _lock_parent(self) -> None:
        """Lock the parent row with SELECT … FOR UPDATE to serialise sibling operations."""
        parent = getattr(self, self._order_parent_field)
        type(parent).objects.select_for_update().get(pk=parent.pk)

    def compact_siblings(self, from_order: int) -> models.QuerySet:
        """Close the ordering gap by decrementing siblings above ``from_order``.

        Returns a lazy queryset of the affected siblings (those now at
        ``from_order`` and above). Subclasses may override to perform
        additional cleanup (e.g. slug refresh) using the returned queryset
        — call ``super().compact_siblings(from_order)`` first.
        """
        parent_id = getattr(self, f"{self._order_parent_field}_id")
        type(self).objects.filter(
            **{self._order_parent_field: parent_id, "order__gt": from_order}
        ).update(order=models.F("order") - 1)
        return type(self).objects.filter(
            **{self._order_parent_field: parent_id, "order__gte": from_order}
        )

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        with transaction.atomic():
            self._lock_parent()
            from_order = self.order
            result = super().delete(*args, **kwargs)
            self.compact_siblings(from_order)
        return result

    class Meta:
        abstract = True


# ==============================================================================
# WORKOUT
# ==============================================================================


class Workout(models.Model):
    """Core workout record. Subtype determines workout_type and is immutable after creation."""

    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    start_time = models.DateTimeField(default=timezone.now)
    description = models.CharField(max_length=255, default="", blank=True)
    workout_status = models.CharField(
        max_length=20,
        choices=WorkoutStatus.choices(),
        default=WorkoutStatus.PLANNED,
    )
    subtype = models.CharField(max_length=30, choices=WorkoutSubtype.choices())

    @property
    def workout_type(self) -> str:
        return SUBTYPE_TYPE_MAP[WorkoutSubtype(self.subtype)].value

    def get_absolute_url(self) -> str:
        return reverse("workouts:workout_detail", kwargs={"pk": self.pk})

    def get_detail(self) -> "DetailBase | None":
        """Return the type-specific detail row, or None if it doesn't exist."""
        model = DetailBase._detail_registry.get(self.workout_type)
        if model is None:
            return None
        try:
            return getattr(self, model.get_related_name())
        except model.DoesNotExist:
            return None

    @property
    def gui_fields(self) -> dict:
        detail = self.get_detail()
        if detail and isinstance(detail.additional_data, dict):
            return detail.additional_data.get("gui_fields", {})
        return {}

    def __str__(self) -> str:
        return f"{self.name} - {self.start_time}"

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "-start_time"],
                name="wrk_user_time_idx",
            ),
        ]


# ==============================================================================
# DETAIL MODELS
# ==============================================================================


class DetailBase(models.Model):
    """Abstract base for type-specific workout details (duration, load, additional_data).

    Concrete subclasses auto-register via ``__init_subclass__`` into
    ``_detail_registry``, keyed by their ``_workout_type``. Always calls
    ``full_clean()`` on save to enforce model validation.
    """

    _detail_registry: dict[WorkoutType, type["DetailBase"]] = {}
    _workout_type: WorkoutType
    # Declared on each concrete subclass as a OneToOneField; annotated here for type checkers.
    workout: "Workout"
    workout_id: int

    duration = models.DurationField(
        null=True,
        blank=True,
        validators=[GreaterThanDurationValidator(timedelta(seconds=0))],
    )
    additional_data = models.JSONField(default=dict, blank=True)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_workout_type") and not getattr(
            getattr(cls, "Meta", None), "abstract", False
        ):
            DetailBase._detail_registry[cls._workout_type] = cls

    @classmethod
    def get_related_name(cls) -> str:
        """Return the reverse accessor name for this detail's OneToOne to Workout."""
        return cls._meta.get_field("workout").remote_field.related_name  # type: ignore[union-attr,return-value]

    def _validate_gui_fields(self) -> None:
        subtype_value = getattr(self.workout, "subtype", None)
        if not subtype_value:
            return
        try:
            subtype_enum = WorkoutSubtype(subtype_value)
        except ValueError:
            return
        schema = subtype_enum.gui_schema
        if not schema:
            return
        gui_fields = self.additional_data.get("gui_fields", {})
        if not isinstance(gui_fields, dict):
            raise ValidationError({"additional_data": "gui_fields must be a dict."})
        unknown = set(gui_fields) - set(schema)
        if unknown:
            raise ValidationError(
                {
                    "additional_data": (
                        f"gui_fields contains keys not in subtype "
                        f"'{subtype_enum.label}' schema: {', '.join(sorted(unknown))}"
                    )
                }
            )

    def clean(self) -> None:
        super().clean()
        if not self.workout_id:
            return
        if self.workout.workout_type != self._workout_type:
            raise ValidationError(
                f"Workout type '{self.workout.workout_type}' does not match "
                f"detail type '{self._workout_type}'."
            )
        self._validate_gui_fields()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.__class__.__name__} for workout {self.pk}"

    class Meta:
        abstract = True


class AerobicDetails(DetailBase):
    """Aerobic workout details with distance (meters) and computed speed/pace."""

    _workout_type = WorkoutType.AEROBIC

    workout = models.OneToOneField(
        Workout,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="aerobic_details",
    )
    distance = models.PositiveIntegerField(
        null=True, blank=True, help_text="Distance in meters."
    )

    @property
    def distance_km(self) -> float | None:
        return m_to_km(self.distance)

    @property
    def speed(self) -> float | None:
        """Speed in km/h, computed from distance and duration."""
        km = self.distance_km
        if not (self.duration and km):
            return None
        secs = self.duration.total_seconds()  # pylint: disable=no-member
        return 3600 * km / secs if secs else None

    @property
    def pace(self) -> float | None:
        """Pace in seconds per km."""
        km = self.distance_km
        if not (self.duration and km and km > 0):
            return None
        return self.duration.total_seconds() / km

    @property
    def pace_display(self) -> str:
        """Formatted pace as M:SS min/km."""
        p = self.pace
        if p is None:
            return ""
        total_seconds = round(p)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d} min/km"

    class Meta:
        verbose_name_plural = "Aerobic details"


class StrengthDetails(DetailBase):
    """Strength workout details (sets, total weight)."""

    _workout_type = WorkoutType.STRENGTH

    workout = models.OneToOneField(
        Workout,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="strength_details",
    )
    num_sets = models.PositiveIntegerField(null=True, blank=True)
    total_weight = models.PositiveIntegerField(
        null=True, blank=True, help_text="Total weight in kg."
    )

    class Meta:
        verbose_name_plural = "Strength details"


class GenericDetails(DetailBase):
    """Generic workout details (duration and load only, no extra fields)."""

    _workout_type = WorkoutType.GENERIC

    workout = models.OneToOneField(
        Workout,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="generic_details",
    )

    class Meta:
        verbose_name_plural = "Generic details"


# ==============================================================================
# PERIODIZATION
# ==============================================================================


class Macrocycle(models.Model):
    """Top-level training block. Owns mesocycles → microcycles.

    Call hydrate() to compute dates bottom-up from Microcycle.duration_days.
    HydratedProperty fields (end_date, scheduled_duration) raise
    AttributeError until hydrated.
    """

    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    description = models.CharField(max_length=255, default="", blank=True)
    primary_sport = models.CharField(
        max_length=30,
        choices=AEROBIC_CHOICES,
        default=WorkoutSubtype.RUNNING,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="uq_macro_user_name"),
        ]

    scheduled_duration = HydratedProperty()
    end_date = HydratedProperty()

    @staticmethod
    def _calc_end_date(start_date: date, days_duration: int) -> date:
        if days_duration > 0:
            return start_date + timedelta(days=days_duration - 1)
        return start_date

    def hydrate(self: "Macrocycle") -> "Macrocycle":
        """Fetch the full tree in two queries, compute dates in Python, cache on instances.

        Usage:
            macro = macro.hydrate()
            for meso in macro.hydrated_mesocycles:
                print(meso.start_date, meso.end_date)
                for micro in meso.hydrated_microcycles:
                    print(micro.start_date, micro.end_date)
        """
        mesocycles = list(
            self.mesocycles.prefetch_related(
                Prefetch(
                    "microcycles",
                    queryset=Microcycle.objects.order_by("order"),
                )
            ).order_by("order")
        )

        current_date = self.start_date
        total_macro_duration = 0

        for meso in mesocycles:
            meso._cached_start_date = current_date

            micros = list(meso.microcycles.all())
            meso_duration = 0

            for micro in micros:
                micro._cached_start_date = current_date
                micro.mesocycle = meso
                days = micro.duration_days
                micro._cached_end_date = self._calc_end_date(current_date, days)

                current_date += timedelta(days=days)
                meso_duration += days

            meso._cached_duration_days = meso_duration
            meso._cached_end_date = self._calc_end_date(
                meso._cached_start_date, meso_duration
            )
            meso.hydrated_microcycles = micros
            total_macro_duration += meso_duration

        self._cached_scheduled_duration = total_macro_duration
        self._cached_end_date = self._calc_end_date(
            self.start_date, total_macro_duration
        )
        self.hydrated_mesocycles = mesocycles
        return self

    def get_absolute_url(self) -> str:
        return reverse("workouts:macrocycle_detail", kwargs={"macro_pk": self.pk})

    def __str__(self) -> str:
        return self.name


class Mesocycle(OrderMixin, models.Model):
    """Ordered phase within a macrocycle (base, build, peak, …).

    HydratedProperty fields (start_date, end_date, duration_days) are
    populated by Macrocycle.hydrate().
    """

    _order_parent_field = "macrocycle"

    macrocycle = models.ForeignKey(
        Macrocycle, on_delete=models.CASCADE, related_name="mesocycles"
    )
    order = models.PositiveSmallIntegerField(editable=False)
    meso_type = models.CharField(max_length=20, choices=MesocycleType.choices())
    comment = models.CharField(max_length=255, default="", blank=True)

    duration_days = HydratedProperty()
    start_date = HydratedProperty()
    end_date = HydratedProperty()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding and self.order is None:
            with transaction.atomic():
                self._lock_parent()
                last = Mesocycle.objects.filter(macrocycle=self.macrocycle).aggregate(
                    largest=Max("order")
                )["largest"]
                self.order = (last or 0) + 1
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse(
            "workouts:mesocycle_detail",
            kwargs={
                "macro_pk": self.macrocycle.pk,
                "meso_pk": self.pk,
            },
        )

    def __str__(self) -> str:
        return f"{self.get_meso_type_display()} (Meso {self.order})"  # type: ignore[attr-defined]

    class Meta:
        ordering = ["macrocycle", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["macrocycle", "order"], name="uq_meso_order"
            ),
        ]


class Microcycle(OrderMixin, models.Model):
    """Ordered cycle within a mesocycle. duration_days is the source of truth for all date computation.

    HydratedProperty fields (start_date, end_date) are populated by
    Macrocycle.hydrate().
    """

    _order_parent_field = "mesocycle"

    mesocycle = models.ForeignKey(
        Mesocycle, on_delete=models.CASCADE, related_name="microcycles"
    )
    order = models.PositiveSmallIntegerField(editable=False)
    duration_days = models.PositiveSmallIntegerField(default=7)
    micro_type = models.CharField(
        max_length=20, choices=MicrocycleType.choices(), default=MicrocycleType.LOAD
    )

    comment = models.CharField(max_length=255, default="", blank=True)
    planned_sessions = models.PositiveIntegerField(null=True, blank=True)
    planned_distance = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total planned distance in meters.",
    )
    planned_long_distance = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Planned long session distance in meters.",
    )
    planned_strength_sessions = models.PositiveIntegerField(null=True, blank=True)
    planned_cross_sessions = models.PositiveIntegerField(null=True, blank=True)

    @property
    def macrocycle(self) -> Macrocycle:
        return self.mesocycle.macrocycle

    start_date = HydratedProperty()
    end_date = HydratedProperty()

    @property
    def planned_distance_km(self) -> float | None:
        return m_to_km(self.planned_distance)

    @property
    def planned_long_distance_km(self) -> float | None:
        return m_to_km(self.planned_long_distance)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding and self.order is None:
            with transaction.atomic():
                self._lock_parent()
                last = Microcycle.objects.filter(mesocycle=self.mesocycle).aggregate(
                    largest=Max("order")
                )["largest"]
                self.order = (last or 0) + 1
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse(
            "workouts:microcycle_detail",
            kwargs={
                "macro_pk": self.mesocycle.macrocycle.pk,
                "meso_pk": self.mesocycle.pk,
                "micro_pk": self.pk,
            },
        )

    def __str__(self) -> str:
        return f"{self.get_micro_type_display()} (Micro {self.order}, {self.duration_days} days)"

    class Meta:
        ordering = ["mesocycle", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["mesocycle", "order"], name="uq_micro_order"
            ),
        ]


class ActiveMacrocycle(models.Model):
    """Maps a user to their currently active macrocycle (one per user)."""

    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.CASCADE,
        primary_key=True,
    )
    macrocycle = models.ForeignKey(Macrocycle, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.user} → {self.macrocycle}"
