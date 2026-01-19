from django.contrib import admin, messages
from django.utils import timezone
from dateutil.relativedelta import relativedelta
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


@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'type', 'lokal')
    search_fields = ('user__name', 'user__lastname', 'lokal__unit_number')
    actions = ['generate_annex']

    def get_queryset(self, request):
        # Override default manager to show all agreements (active and inactive)
        # so that filtering in admin works correctly.
        return Agreement.all_objects.all()

    @admin.action(description='Generuj aneks do wybranej umowy (przedłużenie o rok - 1 dzień)')
    def generate_annex(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Proszę wybrać dokładnie jedną umowę do wygenerowania aneksu.", level=messages.ERROR)
            return

        original_agreement = queryset.first()

        if not original_agreement.end_date:
            self.message_user(request, f"Umowa dla lokalu {original_agreement.lokal.unit_number} nie ma daty zakończenia. Nie można wygenerować aneksu.", level=messages.ERROR)
            return

        # Tworzenie aneksu
        new_start_date = original_agreement.end_date + timezone.timedelta(days=1)
        new_end_date = original_agreement.end_date + relativedelta(years=1) - timezone.timedelta(days=1)

        annex = Agreement.objects.create(
            user=original_agreement.user,
            lokal=original_agreement.lokal,
            signing_date=timezone.now().date(),
            start_date=new_start_date,
            end_date=new_end_date,
            rent_amount=original_agreement.rent_amount,
            deposit_amount=original_agreement.deposit_amount,
            type='aneks',
            old_agreement=original_agreement,
            additional_info=f"Aneks do umowy z dnia {original_agreement.signing_date}.\n{original_agreement.additional_info}",
            number_of_occupants=original_agreement.number_of_occupants,
            is_active=True 
        )

        # Deactivate the original agreement
        original_agreement.is_active = False
        original_agreement.save()

        self.message_user(request, f"Pomyślnie wygenerowano aneks dla umowy lokalu {annex.lokal.unit_number}. Nowa umowa obowiązuje od {annex.start_date} do {annex.end_date}. Poprzednia umowa została zarchiwizowana.", level=messages.SUCCESS)


admin.site.register(User)
admin.site.register(Lokal)
admin.site.register(RentSchedule)
admin.site.register(Meter)
admin.site.register(MeterReading)
admin.site.register(FixedCost)
admin.site.register(FinancialTransaction)
admin.site.register(LokalAssignmentRule)
admin.site.register(LocalPhoto)