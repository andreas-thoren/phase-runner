"""Domain enums used across models, views, forms, and templates."""

from enum import StrEnum, unique


class ChoicesEnum(StrEnum):
    """StrEnum with a Django-compatible choices() classmethod."""

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.value.capitalize()) for member in cls]


@unique
class WorkoutType(ChoicesEnum):
    AEROBIC = "aerobic"
    STRENGTH = "strength"
    GENERIC = "generic"


@unique
class MesocycleType(ChoicesEnum):
    BASE = "base"
    PREP = "prep"
    BUILD = "build"
    SHARPEN = "sharpen"
    SPECIFIC = "specific"
    PEAK = "peak"
    TRANSITION = "transition"


@unique
class MicrocycleType(ChoicesEnum):
    INTRO = "intro"
    LOAD = "load"
    OVERLOAD = "overload"
    CONSOLIDATE = "consolidate"
    DELOAD = "deload"
    TAPER = "taper"
    RACE = "race"


@unique
class WorkoutStatus(ChoicesEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"


@unique
class ViewType(StrEnum):
    """Used by templates to render correct elements."""

    CREATE = "create"
    UPDATE = "update"
    DETAIL = "detail"
    DELETE = "delete"
