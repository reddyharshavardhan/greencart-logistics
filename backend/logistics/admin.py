from django.contrib import admin
from .models import Driver, Route, Order, SimulationResult, UserProfile

admin.site.register(Driver)
admin.site.register(Route)
admin.site.register(Order)
admin.site.register(SimulationResult)
admin.site.register(UserProfile)