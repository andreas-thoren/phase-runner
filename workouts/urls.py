"""URL configuration for the workouts app.

URL naming convention:
    {model}_list          — list view
    {model}_detail        — detail view
    create_{model}        — create view (not used by FormContextMixin)
    edit_{model}          — edit view
    delete_{model}        — delete view

Where {model} is the lowercase model name (e.g. "macrocycle", "workout").
FormContextMixin auto-resolves _list, _detail, edit_, and delete_ URLs in templates.
"""

from django.urls import path

from . import views
from .constants import APP_NAMESPACE

app_name = APP_NAMESPACE

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    # --- Workout URLs ---
    path("workouts/", views.WorkoutListView.as_view(), name="workout_list"),
    path("running/", views.RunningListView.as_view(), name="running_list"),
    path(
        "workouts/add/<str:subtype>/",
        views.WorkoutCreateView.as_view(),
        name="create_workout",
    ),
    path(
        "workouts/<int:pk>/",
        views.WorkoutDetailView.as_view(),
        name="workout_detail",
    ),
    path(
        "workouts/<int:pk>/edit/",
        views.WorkoutEditView.as_view(),
        name="edit_workout",
    ),
    path(
        "workouts/<int:pk>/delete/",
        views.WorkoutDeleteView.as_view(),
        name="delete_workout",
    ),
    # --- Upload ---
    path(
        "workouts/upload/",
        views.UploadWorkoutsView.as_view(),
        name="upload_workouts",
    ),
    path(
        "workouts/upload/api/",
        views.UploadWorkoutsAPIView.as_view(),
        name="upload_workouts_api",
    ),
    # --- Macrocycle URLs ---
    path("plans/", views.MacrocycleListView.as_view(), name="macrocycle_list"),
    path(
        "plans/add/",
        views.MacrocycleCreateView.as_view(),
        name="create_macrocycle",
    ),
    path(
        "plan-<int:macro_pk>/",
        views.MacrocycleDetailView.as_view(),
        name="macrocycle_detail",
    ),
    path(
        "plan-<int:macro_pk>/create-defaults/",
        views.MacrocycleCreateDefaultCyclesView.as_view(),
        name="create_default_cycles",
    ),
    path(
        "plan-<int:macro_pk>/toggle-active/",
        views.ToggleActiveMacrocycleView.as_view(),
        name="toggle_active",
    ),
    path(
        "plan-<int:macro_pk>/edit/",
        views.MacrocycleEditView.as_view(),
        name="edit_macrocycle",
    ),
    path(
        "plan-<int:macro_pk>/delete/",
        views.MacrocycleDeleteView.as_view(),
        name="delete_macrocycle",
    ),
    path(
        "plan-<int:macro_pk>/summary/",
        views.MacrocycleSummaryView.as_view(),
        name="macrocycle_summary",
    ),
    # --- Mesocycle URLs ---
    path(
        "plan-<int:macro_pk>/add-meso/",
        views.MesocycleCreateView.as_view(),
        name="create_mesocycle",
    ),
    path(
        "plan-<int:macro_pk>/meso-<int:meso_pk>/",
        views.MesocycleDetailView.as_view(),
        name="mesocycle_detail",
    ),
    path(
        "plan-<int:macro_pk>/meso-<int:meso_pk>/edit/",
        views.MesocycleEditView.as_view(),
        name="edit_mesocycle",
    ),
    path(
        "plan-<int:macro_pk>/meso-<int:meso_pk>/delete/",
        views.MesocycleDeleteView.as_view(),
        name="delete_mesocycle",
    ),
    # --- Microcycle URLs ---
    path(
        "plan-<int:macro_pk>/meso-<int:meso_pk>/add-micro/",
        views.MicrocycleCreateView.as_view(),
        name="create_microcycle",
    ),
    path(
        "plan-<int:macro_pk>/meso-<int:meso_pk>/micro-<int:micro_pk>/",
        views.MicrocycleDetailView.as_view(),
        name="microcycle_detail",
    ),
    path(
        "plan-<int:macro_pk>/meso-<int:meso_pk>/micro-<int:micro_pk>/edit/",
        views.MicrocycleEditView.as_view(),
        name="edit_microcycle",
    ),
    path(
        "plan-<int:macro_pk>/meso-<int:meso_pk>/micro-<int:micro_pk>/delete/",
        views.MicrocycleDeleteView.as_view(),
        name="delete_microcycle",
    ),
]
