from django.contrib import admin
from .models import (
    User,
    Lokal,
    Agreement,
    RentSchedule,
    Meter,
    MeterReading,
    FixedCost,
    FinancialTransaction,
    LocalPhoto,
)

admin.site.register(User)
admin.site.register(Lokal)
admin.site.register(Agreement)
admin.site.register(RentSchedule)
admin.site.register(Meter)
admin.site.register(MeterReading)
admin.site.register(FixedCost)
admin.site.register(FinancialTransaction)
admin.site.register(LocalPhoto)