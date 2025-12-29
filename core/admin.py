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
    LokalAssignmentRule,
    LocalPhoto,
    WaterCostOverride,
)

@admin.register(WaterCostOverride)
class WaterCostOverrideAdmin(admin.ModelAdmin):
    list_display = ('period_start_date', 'overridden_bill_amount', 'overridden_total_consumption', 'updated_at')
    list_editable = ('overridden_bill_amount', 'overridden_total_consumption')
    list_display_links = ('period_start_date',)


admin.site.register(User)
admin.site.register(Lokal)
admin.site.register(Agreement)
admin.site.register(RentSchedule)
admin.site.register(Meter)
admin.site.register(MeterReading)
admin.site.register(FixedCost)
admin.site.register(FinancialTransaction)
admin.site.register(LokalAssignmentRule)
admin.site.register(LocalPhoto)