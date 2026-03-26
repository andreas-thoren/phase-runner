"""Django admin registrations for all workout and periodization models."""

from django.contrib import admin
from .models import (
    Workout,
    AerobicDetails,
    StrengthDetails,
    GenericDetails,
    Macrocycle,
    Mesocycle,
    Microcycle,
)

admin.site.register(Workout)
admin.site.register(AerobicDetails)
admin.site.register(StrengthDetails)
admin.site.register(GenericDetails)
admin.site.register(Macrocycle)
admin.site.register(Mesocycle)
admin.site.register(Microcycle)
