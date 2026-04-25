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
class WorkoutSubtype(ChoicesEnum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
    SKIING = "skiing"
    WALKING = "walking"
    STRENGTH = "strength"
    MOBILITY = "mobility"
    GENERIC = "generic"

    @property
    def workout_type(self) -> WorkoutType:
        return SUBTYPE_TYPE_MAP[self]

    @property
    def gui_schema(self) -> dict:
        return GUI_SCHEMAS.get(self, {})

    @property
    def label(self) -> str:
        return self.value.capitalize()


SUBTYPE_TYPE_MAP: dict[WorkoutSubtype, WorkoutType] = {
    WorkoutSubtype.RUNNING: WorkoutType.AEROBIC,
    WorkoutSubtype.CYCLING: WorkoutType.AEROBIC,
    WorkoutSubtype.SWIMMING: WorkoutType.AEROBIC,
    WorkoutSubtype.SKIING: WorkoutType.AEROBIC,
    WorkoutSubtype.WALKING: WorkoutType.AEROBIC,
    WorkoutSubtype.STRENGTH: WorkoutType.STRENGTH,
    WorkoutSubtype.MOBILITY: WorkoutType.GENERIC,
    WorkoutSubtype.GENERIC: WorkoutType.GENERIC,
}

AEROBIC_SUBTYPES: list[WorkoutSubtype] = [
    st for st in WorkoutSubtype if SUBTYPE_TYPE_MAP[st] == WorkoutType.AEROBIC
]

AEROBIC_CHOICES: list[tuple[str, str]] = [
    (st.value, st.label) for st in AEROBIC_SUBTYPES
]

SESSION_LABELS: dict[WorkoutSubtype, str] = {
    WorkoutSubtype.RUNNING: "Runs",
    WorkoutSubtype.CYCLING: "Rides",
    WorkoutSubtype.SWIMMING: "Swims",
    WorkoutSubtype.SKIING: "Ski sessions",
    WorkoutSubtype.WALKING: "Walks",
}

LONG_SESSION_LABELS: dict[WorkoutSubtype, str] = {
    WorkoutSubtype.RUNNING: "Long run",
    WorkoutSubtype.CYCLING: "Long ride",
    WorkoutSubtype.SWIMMING: "Long swim",
    WorkoutSubtype.SKIING: "Long ski",
    WorkoutSubtype.WALKING: "Long walk",
}

SPORT_SHORT_LABELS: dict[WorkoutSubtype, str] = {
    WorkoutSubtype.RUNNING: "Run",
    WorkoutSubtype.CYCLING: "Ride",
    WorkoutSubtype.SWIMMING: "Swim",
    WorkoutSubtype.SKIING: "Ski",
    WorkoutSubtype.WALKING: "Walk",
}

# Sport-specific summary-view columns. Universal cols (comment/x/str/load) live in
# SummaryFilterForm.UNIVERSAL_COL_CHOICES. Add an entry here when a column only
# makes sense for certain primary sports.
EXTRA_SUMMARY_COLS: dict[WorkoutSubtype, list[tuple[str, str]]] = {
    WorkoutSubtype.RUNNING: [("zones", "Zone distribution")],
}

GUI_SCHEMAS: dict[WorkoutSubtype, dict] = {
    WorkoutSubtype.RUNNING: {
        "load_garmin": {"type": "number", "label": "Load (Garmin)"},
        "avg_hr": {"type": "number", "label": "Avg HR"},
        "max_hr": {"type": "number", "label": "Max HR"},
        "cadence": {"type": "number", "label": "Cadence"},
        "elevation_m": {"type": "number", "label": "Elevation (m)"},
        "z1_pct": {"type": "number", "label": "Zone 1 %"},
        "z2_pct": {"type": "number", "label": "Zone 2 %"},
        "z3_pct": {"type": "number", "label": "Zone 3 %"},
        "z4_pct": {"type": "number", "label": "Zone 4 %"},
        "z5_pct": {"type": "number", "label": "Zone 5 %"},
        "rpe": {"type": "number", "label": "RPE"},
    },
    WorkoutSubtype.CYCLING: {
        "load_garmin": {"type": "number", "label": "Load (Garmin)"},
        "avg_hr": {"type": "number", "label": "Avg HR"},
        "max_hr": {"type": "number", "label": "Max HR"},
        "cadence": {"type": "number", "label": "Cadence"},
        "avg_power": {"type": "number", "label": "Avg Power (W)"},
        "elevation_m": {"type": "number", "label": "Elevation (m)"},
        "rpe": {"type": "number", "label": "RPE"},
    },
    WorkoutSubtype.SWIMMING: {
        "load_garmin": {"type": "number", "label": "Load (Garmin)"},
        "avg_hr": {"type": "number", "label": "Avg HR"},
        "max_hr": {"type": "number", "label": "Max HR"},
        "stroke_rate": {"type": "number", "label": "Stroke Rate"},
        "laps": {"type": "number", "label": "Laps"},
        "pool_length_m": {"type": "number", "label": "Pool Length (m)"},
        "rpe": {"type": "number", "label": "RPE"},
    },
    WorkoutSubtype.SKIING: {
        "load_garmin": {"type": "number", "label": "Load (Garmin)"},
        "avg_hr": {"type": "number", "label": "Avg HR"},
        "max_hr": {"type": "number", "label": "Max HR"},
        "elevation_m": {"type": "number", "label": "Elevation (m)"},
        "rpe": {"type": "number", "label": "RPE"},
    },
    WorkoutSubtype.STRENGTH: {
        "load_garmin": {"type": "number", "label": "Load (Garmin)"},
        "avg_hr": {"type": "number", "label": "Avg HR"},
        "max_hr": {"type": "number", "label": "Max HR"},
        "exercises": {"type": "number", "label": "Exercises"},
        "rpe": {"type": "number", "label": "RPE"},
    },
    WorkoutSubtype.WALKING: {
        "load_garmin": {"type": "number", "label": "Load (Garmin)"},
        "avg_hr": {"type": "number", "label": "Avg HR"},
        "max_hr": {"type": "number", "label": "Max HR"},
        "cadence": {"type": "number", "label": "Cadence"},
        "elevation_m": {"type": "number", "label": "Elevation (m)"},
        "rpe": {"type": "number", "label": "RPE"},
    },
    WorkoutSubtype.MOBILITY: {
        "load_garmin": {"type": "number", "label": "Load (Garmin)"},
        "avg_hr": {"type": "number", "label": "Avg HR"},
        "max_hr": {"type": "number", "label": "Max HR"},
        "rpe": {"type": "number", "label": "RPE"},
    },
    WorkoutSubtype.GENERIC: {
        "load_garmin": {"type": "number", "label": "Load (Garmin)"},
        "avg_hr": {"type": "number", "label": "Avg HR"},
        "max_hr": {"type": "number", "label": "Max HR"},
        "rpe": {"type": "number", "label": "RPE"},
    },
}

# Keys are camelCase strings returned by the Garmin FIT JS SDK
# with convertTypesToStrings: true.
FIT_SPORT_MAP: dict[str, WorkoutSubtype] = {
    "running": WorkoutSubtype.RUNNING,
    "trailRunning": WorkoutSubtype.RUNNING,
    "cycling": WorkoutSubtype.CYCLING,
    "eBiking": WorkoutSubtype.CYCLING,
    "swimming": WorkoutSubtype.SWIMMING,
    "openWaterSwimming": WorkoutSubtype.SWIMMING,
    "crossCountrySkiing": WorkoutSubtype.SKIING,
    "alpineSkiing": WorkoutSubtype.SKIING,
    "walking": WorkoutSubtype.WALKING,
    "hiking": WorkoutSubtype.WALKING,
    "training": WorkoutSubtype.STRENGTH,
    "fitnessEquipment": WorkoutSubtype.STRENGTH,
    "flexibilityTraining": WorkoutSubtype.MOBILITY,
    "generic": WorkoutSubtype.GENERIC,
}


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
