import datetime
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from dateutil.relativedelta import relativedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

from ..models import (
    BUILDING_LOKAL_NUMBER,
    Agreement,
    FinancialTransaction,
    FixedCost,
    Lokal,
    Meter,
    WaterCostOverride,
)
from ..services.reporting import get_bimonthly_report_context, get_annual_report_context
from ..services.pdf_generation import build_annual_report_pdf


@login_required
def fixed_costs_view(request):
    """
    Oblicza i wyświetla narastające koszty stałe (wywóz śmieci) dla wszystkich
    aktywnych umów od początku ich trwania do bieżącego dnia.
    """
    waste_rules = FixedCost.objects.filter(
        category="waste",
        calculation_method='per_person'
    ).order_by('-effective_date')

    if not waste_rules.exists():
        messages.error(request, "Brak zdefiniowanych reguł dla kosztów wywozu śmieci.")
        return render(request, 'core/fixed_costs_list.html', {'waste_rule': None, 'title': 'Błąd: Brak reguł kosztów'})

    calculated_costs = []
    grand_total_cost = Decimal('0.00')
    today = date.today()

    agreements = Agreement.objects.filter(is_active=True).select_related('lokal', 'user')

    for agreement in agreements:
        agreement_total_cost = Decimal('0.00')

        current_month_start = agreement.start_date.replace(day=1)
        months_counted = 0

        while current_month_start <= today:
            active_rule_for_month = None
            for rule in waste_rules:
                if rule.effective_date <= current_month_start:
                    active_rule_for_month = rule
                    break

            if active_rule_for_month:
                monthly_cost = agreement.number_of_occupants * active_rule_for_month.amount
                agreement_total_cost += monthly_cost
                months_counted += 1

            current_month_start += relativedelta(months=1)

        if agreement_total_cost > 0:
            calculated_costs.append({
                'agreement': agreement,
                'total_cost': agreement_total_cost,
                'start_date': agreement.start_date,
                'months_counted': months_counted,
            })
            grand_total_cost += agreement_total_cost

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

    calculated_costs.sort(key=lambda x: natural_sort_key(x['agreement'].lokal.unit_number))

    context = {
        'waste_rule': waste_rules.first(),
        'calculated_costs': calculated_costs,
        'total_cost': grand_total_cost,
        'title': 'Koszty stałe - Wywóz śmieci (narastająco)'
    }
    return render(request, 'core/fixed_costs_list.html', context)


@login_required
def bimonthly_report_view(request, pk):
    """
    Generuje i wyświetla raport dwumiesięczny dla wybranego lokalu i roku.
    Zapewnia, że lokator widzi tylko swój raport.
    """
    lokal = get_object_or_404(Lokal, pk=pk)

    if not request.user.is_superuser:
        try:
            agreement = Agreement.objects.get(user__email=request.user.email, is_active=True)
            if lokal.pk != agreement.lokal.pk:
                return HttpResponseForbidden("Nie masz uprawnień do przeglądania raportów dla tego lokalu.")
        except Agreement.DoesNotExist:
            return HttpResponseForbidden("Nie masz przypisanej żadnej aktywnej umowy.")

    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year

    current_year = date.today().year
    available_years = list(range(current_year, current_year - 5, -1))

    context = get_bimonthly_report_context(lokal, selected_year)
    context.update({
        'title': f"Raport dwumiesięczny dla lokalu {lokal.unit_number} ({selected_year})",
        'available_years': available_years,
    })

    return render(request, 'core/bimonthly_report.html', context)


@login_required
def water_cost_summary_view(request):
    """
    Panel do zarządzania kosztami wody. Dostępny tylko dla superużytkownika.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden("Nie masz uprawnień do zarządzania kosztami wody.")

    if request.method == 'POST':
        num_periods = int(request.POST.get('num_periods', 0))
        for i in range(num_periods):
            try:
                period_start_str = request.POST.get(f'period_start_date_{i}')
                bill_amount_str = request.POST.get(f'bill_amount_{i}', '').replace(',', '.')
                total_consumption_str = request.POST.get(f'total_consumption_{i}', '').replace(',', '.')

                if not period_start_str:
                    continue

                period_start_date = datetime.datetime.strptime(period_start_str, '%Y-%m-%d').date()

                bill_amount = Decimal(bill_amount_str) if bill_amount_str else None
                total_consumption = Decimal(total_consumption_str) if total_consumption_str else None

                override, created = WaterCostOverride.objects.get_or_create(
                    period_start_date=period_start_date
                )

                override.overridden_bill_amount = bill_amount
                override.overridden_total_consumption = total_consumption
                override.save()

            except (ValueError, InvalidOperation) as e:
                messages.error(request, f"Błąd podczas przetwarzania danych dla okresu {period_start_str}: {e}")
                continue

        messages.success(request, "Pomyślnie zaktualizowano ręczne ustawienia kosztów wody.")
        return redirect('water_cost_summary')

    report_data = []
    today = date.today()

    current_period_start_month = today.month if today.month % 2 != 0 else today.month - 1
    period_start = date(today.year, current_period_start_month, 1)

    all_lokals_with_water = Lokal.objects.filter(
        is_active=True,
        meters__type__in=['hot_water', 'cold_water'],
        meters__status='aktywny'
    ).exclude(unit_number__iexact=BUILDING_LOKAL_NUMBER).distinct().prefetch_related('meters__readings')

    for _ in range(12):
        period_end = period_start + relativedelta(months=2, days=-1)

        override_obj = WaterCostOverride.objects.filter(period_start_date=period_start).first()

        unit_price = Decimal('0.00')
        if override_obj and override_obj.overridden_bill_amount and override_obj.overridden_total_consumption and override_obj.overridden_total_consumption > 0:
            unit_price = override_obj.overridden_bill_amount / override_obj.overridden_total_consumption

        total_lokal_water_costs = Decimal('0.00')
        total_calculated_consumption = Decimal('0.00')

        for lokal in all_lokals_with_water:
            lokal_consumption_for_period = Decimal('0.00')
            for meter in lokal.meters.all():
                if meter.type not in ['hot_water', 'cold_water']:
                    continue

                all_readings = sorted(meter.readings.all(), key=lambda r: r.reading_date)

                start_reading = next((r for r in reversed(all_readings) if r.reading_date <= period_start), None)
                end_reading = next((r for r in all_readings if r.reading_date >= period_end), None)

                if start_reading and end_reading and start_reading.id != end_reading.id:
                    consumption = end_reading.value - start_reading.value
                    lokal_consumption_for_period += consumption

            total_calculated_consumption += lokal_consumption_for_period
            if unit_price > 0:
                total_lokal_water_costs += lokal_consumption_for_period * unit_price

        invoice_search_end_date = period_end + relativedelta(months=2)
        water_invoice = FinancialTransaction.objects.filter(
            title='oplata_za_wode',
            posting_date__lte=invoice_search_end_date,
            posting_date__gte=period_end
        ).order_by('posting_date').first()
        calculated_bill = abs(water_invoice.amount) if water_invoice else None

        report_data.append({
            'period_start_date': period_start,
            'period_end_date': period_end,
            'override_obj': override_obj,
            'calculated_consumption': total_calculated_consumption,
            'calculated_bill': calculated_bill,
            'invoice_date': water_invoice.posting_date if water_invoice else None,
            'total_water_payments': total_lokal_water_costs,
        })

        period_start -= relativedelta(months=2)

    context = {
        'title': "Panel Zarządzania Kosztami Wody",
        'report_data': report_data
    }
    return render(request, 'core/water_cost_summary.html', context)


@login_required
def water_cost_table(request):
    """
    Generuje i wyświetla tabelę kosztów wody.
    Superużytkownik widzi wszystko. Lokator widzi tylko dane dla swojego lokalu.
    """
    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year

    current_year = date.today().year
    available_years = list(range(current_year, current_year - 6, -1))

    if request.user.is_superuser:
        lokals = Lokal.objects.filter(is_active=True).exclude(unit_number__iexact=BUILDING_LOKAL_NUMBER).order_by('unit_number')
    else:
        try:
            agreement = Agreement.objects.get(user__email=request.user.email, is_active=True)
            lokals = Lokal.objects.filter(pk=agreement.lokal.pk) if agreement.lokal else Lokal.objects.none()
        except Agreement.DoesNotExist:
            lokals = Lokal.objects.none()

    consumptions = defaultdict(lambda: defaultdict(Decimal))
    all_water_meters = Meter.objects.filter(
        lokal__in=lokals,
        type__in=['hot_water', 'cold_water'],
        status='aktywny'
    ).select_related('lokal').prefetch_related('readings')

    for meter in all_water_meters:
        readings = list(meter.readings.all().order_by('reading_date'))
        for i in range(1, len(readings)):
            start_reading, end_reading = readings[i-1], readings[i]
            consumption = end_reading.value - start_reading.value

            end_date = end_reading.reading_date
            period_start_month = ((end_date.month - 1) // 2) * 2 + 1
            if end_date.day < 15 and end_date.month % 2 != 0:
                effective_date = end_date - relativedelta(months=2)
                period_start_month = ((effective_date.month - 1) // 2) * 2 + 1
                period_key = date(effective_date.year, period_start_month, 1)
            else:
                period_key = date(end_date.year, period_start_month, 1)
            consumptions[period_key][meter.lokal_id] += consumption

    period_names = [
        "styczeń-luty", "marzec-kwiecień", "maj-czerwiec",
        "lipiec-sierpień", "wrzesień-październik", "listopad-grudzień"
    ]

    table_data = []
    month_start_num = 1
    for name in period_names:
        period_start_date = date(selected_year, month_start_num, 1)

        override_obj = WaterCostOverride.objects.filter(period_start_date=period_start_date).first()
        unit_price = Decimal('0.00')
        total_period_consumption = sum(consumptions[period_start_date].values())
        if override_obj and override_obj.overridden_bill_amount and total_period_consumption > 0:
            unit_price = override_obj.overridden_bill_amount / total_period_consumption

        row = {'report': {'name': f"{name} {selected_year}", 'unit_price': unit_price}, 'details': []}
        total_row_cost = Decimal('0.00')

        for lokal in lokals:
            lokal_consumption = consumptions[period_start_date].get(lokal.id, Decimal('0.00'))
            cost = lokal_consumption * unit_price
            row['details'].append({'consumption': lokal_consumption, 'cost': cost})
            total_row_cost += cost

        row['total_cost'] = total_row_cost
        row['total_consumption'] = total_period_consumption if request.user.is_superuser else sum(d['consumption'] for d in row['details'])
        table_data.append(row)
        month_start_num += 2

    table_data.reverse()

    context = {
        'lokals': lokals,
        'table_data': table_data,
        'title': f'Tabela kosztów wody dla roku {selected_year}',
        'available_years': available_years,
        'selected_year': selected_year,
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'core/water_cost_table.html', context)


@login_required
def annual_report_pdf(request, pk):
    """
    Generuje raport roczny w formacie PDF dla danej umowy i roku.
    Zapewnia, że lokator może pobrać tylko swój raport.
    """
    agreement = get_object_or_404(Agreement, pk=pk)

    if not request.user.is_superuser:
        if agreement.user.email != request.user.email:
            return HttpResponseForbidden("Nie masz uprawnień do generowania tego raportu.")

    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year

    context = get_annual_report_context(agreement, selected_year, _cache={})
    buffer = build_annual_report_pdf(context)
    filename = f"raport_roczny_{context['agreement'].lokal.unit_number}_{selected_year}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)
