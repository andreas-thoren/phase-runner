"""Shared helpers for the workouts test suite."""

from workouts.models import Macrocycle, Mesocycle, Microcycle


def read_ordering(macrocycle: Macrocycle) -> list[tuple[int, list[int]]]:
    """Read a macrocycle's stored ordering as ``[(meso_pk, [micro_pk, ...]), ...]``.

    Ordered by the persisted ``order`` columns, so it reflects what a reorder
    actually wrote rather than the order rows were created in.
    """
    return [
        (
            meso.pk,
            list(
                Microcycle.objects.filter(mesocycle=meso)
                .order_by("order")
                .values_list("pk", flat=True)
            ),
        )
        for meso in Mesocycle.objects.filter(macrocycle=macrocycle).order_by("order")
    ]
