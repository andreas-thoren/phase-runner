"""Shared utilities: unit converters, validators, hydration descriptor, and cycle generation."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

if TYPE_CHECKING:
    from .models import Macrocycle, Mesocycle


def m_to_km(meters: int | float | None) -> float | None:
    """Convert meters to kilometers. Returns None for non-numeric input."""
    if not isinstance(meters, (int, float)):
        return None
    return meters / 1000


def km_to_m(km: int | float | None) -> int | None:
    """Convert kilometers to meters (int). Returns None for non-numeric input."""
    if not isinstance(km, (int, float)):
        return None
    return int(km * 1000)


class HydratedProperty:
    """Descriptor for periodization properties computed by Macrocycle.hydrate()."""

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self.cache_attr = f"_cached_{name}"
        self.owner_name = owner.__name__

    def __get__(self, obj: object | None, objtype: type | None = None):
        if obj is None:
            return self
        try:
            return getattr(obj, self.cache_attr)
        except AttributeError:
            raise AttributeError(
                f"{self.owner_name}.{self.name} requires hydration. "
                "Call macrocycle.hydrate() first."
            ) from None


class GreaterThanDurationValidator:
    """Validates that a timedelta is strictly greater than a threshold."""

    def __init__(self, threshold: timedelta, message: str | None = None) -> None:
        self.threshold = threshold
        self.message = message or f"Duration must be greater than {self.threshold}."

    def __call__(self, value: timedelta) -> None:
        if value <= self.threshold:
            raise ValidationError(self.message)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, GreaterThanDurationValidator)
            and self.threshold == other.threshold
        )

    def deconstruct(self) -> tuple[str, list, dict]:
        return (
            f"{self.__class__.__module__}.{self.__class__.__name__}",
            [self.threshold],
            {"message": self.message},
        )


# ==============================================================================
# CYCLE GENERATION
# ==============================================================================


def _fill_microcycles(meso: Mesocycle, total_days: int, micro_days: int) -> None:
    """Populate a mesocycle with microcycles of ``micro_days`` length.

    The last microcycle in each mesocycle is assigned ``DELOAD``; all others
    get ``LOAD``. If ``total_days`` is not evenly divisible by ``micro_days``,
    the remainder becomes a shorter ``DELOAD`` microcycle.
    """
    from .enums import MicrocycleType
    from .models import Microcycle

    full_micros = total_days // micro_days
    leftover = total_days % micro_days
    total_micros = full_micros + (1 if leftover > 0 else 0)
    for i in range(full_micros):
        is_last = i == total_micros - 1 and leftover == 0
        Microcycle.objects.create(
            mesocycle=meso,
            duration_days=micro_days,
            micro_type=MicrocycleType.DELOAD if is_last else MicrocycleType.LOAD,
        )
    if leftover > 0:
        Microcycle.objects.create(
            mesocycle=meso,
            duration_days=leftover,
            micro_type=MicrocycleType.DELOAD,
        )


def create_default_cycles(
    macrocycle: Macrocycle,
    target_duration_days: int,
    meso_duration_days: int,
    micro_duration_days: int,
) -> None:
    """Auto-generate mesocycles and microcycles for *macrocycle*.

    Raises ``ValueError`` if the macrocycle already has mesocycles.
    """
    from .enums import MesocycleType
    from .models import Mesocycle

    if macrocycle.mesocycles.exists():
        raise ValueError("Macrocycle already has mesocycles.")

    num_full_mesos = target_duration_days // meso_duration_days
    remainder = target_duration_days % meso_duration_days

    meso_types = [
        MesocycleType.BASE,
        MesocycleType.BUILD,
        MesocycleType.SHARPEN,
        MesocycleType.PEAK,
        MesocycleType.TRANSITION,
    ]

    with transaction.atomic():
        for i in range(num_full_mesos):
            meso = Mesocycle.objects.create(
                macrocycle=macrocycle,
                meso_type=meso_types[i % len(meso_types)],
            )
            _fill_microcycles(meso, meso_duration_days, micro_duration_days)

        if remainder > 0:
            meso = Mesocycle.objects.create(
                macrocycle=macrocycle,
                meso_type=meso_types[num_full_mesos % len(meso_types)],
            )
            _fill_microcycles(meso, remainder, micro_duration_days)
