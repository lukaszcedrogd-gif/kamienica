# twoja_aplikacja/admin.py

from django.contrib import admin
from kamienica.models import (
    User, Lokal, Agreement, RentSchedule, Meter, 
    MeterReading, FixedCost, FinancialTransaction, LocalPhoto
)

## --- Administracja Umowami (Inline) ---
# Umożliwia edycję Harmonogramu Czynszu bezpośrednio w widoku Umowy
class RentScheduleInline(admin.TabularInline):
    model = RentSchedule
    extra = 1 # ile pustych formularzy ma się pojawić
    # Fields to display in the inline form
    fields = ('year_month', 'due_amount', 'description')

## --- Administracja Użytkownikami ---
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('name', 'lastname', 'email', 'phone', 'role')
    list_filter = ('role',)
    search_fields = ('name', 'lastname', 'pesel', 'email')
    fieldsets = (
        ('Dane Osobowe', {'fields': ('name', 'lastname', 'role')}),
        ('Dane Kontaktowe', {'fields': ('email', 'phone')}),
        ('Dokumenty Tożsamości', {'fields': ('pesel', 'passport_number')}),
    )

## --- Administracja Lokalami ---
@admin.register(Lokal)
class LokalAdmin(admin.ModelAdmin):
    list_display = ('unit_number', 'size_sqm', 'meter_count_quantity')
    search_fields = ('unit_number',)

## --- Administracja Umowami ---
@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = (
        'lokal', 'user', 'start_date', 'end_date', 'rent_amount', 'type'
    )
    list_filter = ('type', 'start_date')
    search_fields = ('user__lastname', 'lokal__unit_number')
    raw_id_fields = ('user', 'lokal', 'old_agreement') # Użycie surowego ID dla dużych zbiorów danych
    inlines = [RentScheduleInline] # Dodajemy RentSchedule jako inline

## --- Administracja Licznikami ---
class MeterReadingInline(admin.TabularInline):
    model = MeterReading
    extra = 1
    fields = ('reading_date', 'value')
    ordering = ('-reading_date',)

@admin.register(Meter)
class MeterAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'type', 'lokal', 'status')
    list_filter = ('type', 'status', 'lokal')
    inlines = [MeterReadingInline]
    search_fields = ('serial_number',)

## --- Administracja Transakcjami ---
@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):
    list_display = ('posting_date', 'type', 'amount', 'user', 'lokal')
    list_filter = ('type', 'posting_date')
    search_fields = ('description', 'user__lastname', 'lokal__unit_number')
    date_hierarchy = 'posting_date' # Umożliwia nawigację po datach
    raw_id_fields = ('user', 'lokal')

# Rejestracja pozostałych, prostszych modeli
admin.site.register(FixedCost)
admin.site.register(LocalPhoto)