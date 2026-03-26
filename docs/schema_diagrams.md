# Database diagrams

## Workout & Detail Models

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 80, 'rankSpacing': 100}} }%%
flowchart LR
  U[auth_user]
  WS[WorkoutStatus]
  W[Workout]

  AD[AerobicDetails]
  RD[RunningDetails]
  SD[StrengthDetails]
  GD[GenericDetails]

  W --> U
  W --> WS

  AD -->|OneToOne PK| W
  RD -->|OneToOne PK| W
  SD -->|OneToOne PK| W
  GD -->|OneToOne PK| W
```

**Workout**: user, name, start_time, description, workout_type (aerobic / running / strength / generic), workout_status

**Detail models** (all share: duration, avg_hr, max_hr, additional_data):
- **AerobicDetails**: distance, cadence, speed (computed)
- **RunningDetails**: distance, cadence, speed, z1–z5 seconds
- **StrengthDetails**: num_sets, total_weight
- **GenericDetails**: no extra fields

*Detail models are optional — a workout without a detail record has no recorded data yet.*

---

## Periodization Models

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 80, 'rankSpacing': 100}} }%%
flowchart LR
  MA[Macrocycle]
  ME[Mesocycle]
  MI[Microcycle]

  ME --> MA
  MI --> ME
```

**Macrocycle**: name, start_date, end_date, description

**Mesocycle**: macrocycle FK, meso_type (base / prep / build / sharpen / specific / peak / transition), start_date, end_date, description

**Microcycle**: mesocycle FK, micro_type (intro / load / overload / consolidate / deload / taper / race), start_date, end_date, description, goal_run_sessions, goal_dst_m, goal_long_run_dst_m, goal_strength_sessions, goal_cross_sessions

*Cascade delete: removing a Macrocycle removes all its Mesocycles and their Microcycles.*
