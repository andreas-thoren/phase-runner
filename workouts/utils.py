"""Shared utilities: unit converters, validators, hydration descriptor, cycle
generation, and cycle reordering."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

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


# ==============================================================================
# CYCLE REORDERING
# ==============================================================================


class StaleOrderingError(ValueError):
    """The submitted ordering no longer matches what the database holds.

    Raised when a browser tab submits an ordering built from a plan that has
    since gained or lost cycles, or that references rows outside this plan.
    """


def parse_ordering(raw: Any) -> list[dict]:
    """Normalise a submitted ordering payload into ``[{"pk": int, "micros": [int]}]``.

    Purely structural — raises ``ValueError`` on a malformed shape. Whether the
    pks actually belong to the plan is checked by ``apply_cycle_order``.
    """
    if not isinstance(raw, list):
        raise ValueError("Ordering must be a list of mesocycles.")

    parsed: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each mesocycle entry must be an object.")
        pk = entry.get("pk")
        micros = entry.get("micros")
        # bool is a subclass of int — reject it explicitly.
        if not isinstance(pk, int) or isinstance(pk, bool):
            raise ValueError("Each mesocycle entry needs an integer 'pk'.")
        if not isinstance(micros, list) or any(
            not isinstance(micro_pk, int) or isinstance(micro_pk, bool)
            for micro_pk in micros
        ):
            raise ValueError("Each mesocycle entry needs a list of integer 'micros'.")
        parsed.append({"pk": pk, "micros": list(micros)})
    return parsed


def _check_complete(submitted: list[int], existing: set[int], label: str) -> None:
    """Assert that *submitted* is exactly *existing*, with no duplicates.

    This single check is what makes reordering fool-proof: it rejects a stale
    tab, a concurrent create/delete elsewhere, and pks belonging to another
    user's plan, all at once — so there is no separate ownership check to
    forget.
    """
    if len(submitted) != len(set(submitted)):
        raise StaleOrderingError(f"The same {label} was listed more than once.")
    if set(submitted) != existing:
        raise StaleOrderingError(
            f"The {label} list no longer matches this plan. "
            "Reload the page and try again."
        )


def _validate_submission(
    ordering: list[dict],
    existing_mesos: set[int],
    existing_micros: set[int],
    limit: int,
) -> None:
    """Check the submission describes exactly the cycles the plan holds."""
    submitted_mesos = [entry["pk"] for entry in ordering]
    submitted_micros = [pk for entry in ordering for pk in entry["micros"]]

    _check_complete(submitted_mesos, existing_mesos, "mesocycle")
    _check_complete(submitted_micros, existing_micros, "microcycle")

    if len(submitted_mesos) >= limit or len(submitted_micros) >= limit:
        raise StaleOrderingError("This plan has too many cycles to reorder.")


def _assign_positions(ordering: list[dict], mesos: dict, micros: dict) -> None:
    """Set 1..N ``order`` values in memory, re-parenting microcycles as needed."""
    for meso_index, entry in enumerate(ordering, start=1):
        meso = mesos[entry["pk"]]
        meso.order = meso_index
        for micro_index, micro_pk in enumerate(entry["micros"], start=1):
            micro = micros[micro_pk]
            micro.order = micro_index
            micro.mesocycle_id = meso.pk


def apply_cycle_order(macrocycle: Macrocycle, ordering: list[dict]) -> None:
    """Rewrite the meso/micro ordering of *macrocycle* from a full desired state.

    ``ordering`` is the complete resulting order — ``[{"pk": <meso pk>,
    "micros": [<micro pk>, ...]}, ...]`` — not a move instruction. That makes
    the operation idempotent and lets the whole submission be validated by set
    equality against what the database holds.

    Microcycles may move between mesocycles, and a mesocycle may be left with
    none (it then contributes 0 days, which ``Macrocycle.hydrate()`` handles).

    Raises ``StaleOrderingError`` if the submission does not describe exactly
    the cycles this macrocycle currently owns.
    """
    from .models import Macrocycle as MacrocycleModel  # avoid circular import
    from .models import Mesocycle, Microcycle

    with transaction.atomic():
        # One lock on the plan root: a cross-mesocycle move touches two parents,
        # so locking parents individually would need a lock-ordering rule to
        # avoid deadlocking against a concurrent move in the other direction.
        MacrocycleModel.objects.select_for_update().get(pk=macrocycle.pk)

        meso_qs = Mesocycle.objects.filter(macrocycle=macrocycle)
        micro_qs = Microcycle.objects.filter(mesocycle__macrocycle=macrocycle)

        # Re-read inside the lock: validate against what is there now, not
        # against anything fetched before the lock was taken.
        _validate_submission(
            ordering,
            set(meso_qs.values_list("pk", flat=True)),
            set(micro_qs.values_list("pk", flat=True)),
            Mesocycle.ORDER_STAGING_OFFSET,
        )

        # Phase 1 — park every row above the live range. Must cover the whole
        # tree, not one parent at a time, because microcycles change parent.
        Mesocycle.park_orders(meso_qs)
        Microcycle.park_orders(micro_qs)

        # Phase 2 — write final positions. Every live row now sits at
        # ORDER_STAGING_OFFSET+, so writing 1..N cannot collide with a parked
        # row, and each written (parent, order) pair is unique among the writes.
        mesos = {meso.pk: meso for meso in meso_qs}
        micros = {micro.pk: micro for micro in micro_qs}

        _assign_positions(ordering, mesos, micros)

        Mesocycle.objects.bulk_update(mesos.values(), ["order"])
        Microcycle.objects.bulk_update(micros.values(), ["order", "mesocycle"])
