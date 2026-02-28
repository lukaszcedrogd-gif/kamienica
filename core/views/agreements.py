import datetime
import re
from decimal import Decimal, InvalidOperation
from datetime import date
from dateutil.relativedelta import relativedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

from ..models import Agreement, FinancialTransaction, FixedCost
from ..forms import AgreementForm
from ..services.reporting import get_annual_report_context


@login_required
def agreement_list(request):
    """
    Wyświetla listę umów.
    Superużytkownik widzi wszystkie. Lokator widzi tylko swoją aktywną umowę.
    """
    if request.user.is_superuser:
        agreements_query = Agreement.objects.all()
    else:
        agreements_query = Agreement.objects.filter(user__email=request.user.email, is_active=True)

    agreements = list(agreements_query)

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

    agreements.sort(key=lambda x: natural_sort_key(x.lokal.unit_number))
    return render(request, 'core/agreement_list.html', {'agreements': agreements})

@login_required
def create_agreement(request):
    """
    Tworzy nową umowę na podstawie danych z formularza.
    """
    if request.method == 'POST':
        form = AgreementForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('agreement_list')
    else:
        form = AgreementForm()
    return render(request, 'core/agreement_form.html', {'form': form, 'title': 'Dodaj nową umowę'})

@login_required
def edit_agreement(request, pk):
    """
    Edytuje istniejącą umowę.
    """
    agreement = get_object_or_404(Agreement, pk=pk)
    if request.method == 'POST':
        form = AgreementForm(request.POST, instance=agreement)
        if form.is_valid():
            form.save()
            return redirect('agreement_list')
    else:
        form = AgreementForm(instance=agreement)
    return render(request, 'core/agreement_form.html', {'form': form, 'title': f'Edytuj umowę: {agreement}'})

@login_required
def delete_agreement(request, pk):
    """
    Dezaktywuje umowę (soft delete).
    """
    obj = get_object_or_404(Agreement, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('agreement_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'umowę', 'cancel_url': 'agreement_list'})

@login_required
def terminate_agreement(request, pk):
    """
    Obsługuje proces zakończenia umowy. Ustawia datę końcową i dezaktywuje umowę,
    a następnie przekierowuje do strony rozliczenia końcowego.
    """
    agreement = get_object_or_404(Agreement, pk=pk)
    if request.method == 'POST':
        end_date_str = request.POST.get('end_date')
        if not end_date_str:
            messages.error(request, "Data zakończenia jest wymagana.")
            return render(request, 'core/terminate_agreement_form.html', {'agreement': agreement})

        try:
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Nieprawidłowy format daty.")
            return render(request, 'core/terminate_agreement_form.html', {'agreement': agreement})

        agreement.end_date = end_date
        agreement.is_active = False
        agreement.save()

        messages.success(request, f"Umowa dla lokalu {agreement.lokal.unit_number} została zakończona z dniem {end_date}.")
        return redirect('settlement', pk=agreement.pk)

    return render(request, 'core/terminate_agreement_form.html', {'agreement': agreement})


@login_required
def settlement(request, pk):
    """
    Generuje i wyświetla rozliczenie końcowe dla zakończonej umowy.
    """
    agreement = get_object_or_404(Agreement.all_objects, pk=pk)

    if not agreement.end_date:
        agreement.end_date = date.today()

    year = agreement.end_date.year
    period_start = date(year, 1, 1)
    period_end = date(year, 12, 31)

    # 1. Suma należnego czynszu w okresie rozliczeniowym
    total_rent = Decimal('0.00')
    current_month = period_start
    while current_month <= period_end:
        agreement_starts_before_month_end = agreement.start_date <= (current_month + relativedelta(months=1, days=-1))
        agreement_ends_after_month_start = agreement.end_date >= current_month

        if agreement_starts_before_month_end and agreement_ends_after_month_start:
            total_rent += agreement.rent_amount

        current_month += relativedelta(months=1)

    # 2. Suma kosztów stałych (śmieci)
    total_fixed_costs = Decimal('0.00')
    waste_rule = FixedCost.objects.filter(category="waste", calculation_method='per_person').order_by('-effective_date').first()
    if waste_rule:
        current_month = period_start
        while current_month <= period_end:
            agreement_starts_before_month_end = agreement.start_date <= (current_month + relativedelta(months=1, days=-1))
            agreement_ends_after_month_start = agreement.end_date >= current_month

            if agreement_starts_before_month_end and agreement_ends_after_month_start and waste_rule.effective_date <= current_month:
                total_fixed_costs += waste_rule.amount * agreement.number_of_occupants

            current_month += relativedelta(months=1)

    # 3. Suma wpłat od najemcy w okresie rozliczeniowym
    total_payments = FinancialTransaction.objects.filter(
        lokal=agreement.lokal,
        amount__gt=0,
        posting_date__range=(period_start, period_end)
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 4. Dodatkowe koszty z formularza
    additional_costs = Decimal('0.00')
    if request.method == 'POST':
        try:
            additional_costs = Decimal(request.POST.get('additional_costs', '0.00').replace(',', '.'))
        except (InvalidOperation, ValueError):
            messages.error(request, "Nieprawidłowa wartość w polu 'Koszty dodatkowe'.")
            additional_costs = Decimal('0.00')

    # 5. Ostateczny bilans
    deposit = agreement.deposit_amount or Decimal('0.00')
    total_income = total_payments + deposit
    total_costs = total_rent + total_fixed_costs + additional_costs
    final_balance = total_income - total_costs

    context = {
        'agreement': agreement,
        'period_start': period_start,
        'period_end': period_end,
        'total_rent': total_rent,
        'total_fixed_costs': total_fixed_costs,
        'total_payments': total_payments,
        'additional_costs': additional_costs,
        'total_income': total_income,
        'total_costs': total_costs,
        'final_balance': final_balance,
        'title': f"Rozliczenie dla lokalu {agreement.lokal.unit_number}"
    }

    return render(request, 'core/settlement_summary.html', context)


@login_required
def annual_agreement_report(request, pk):
    """
    Generuje i wyświetla raport roczny dla wybranej umowy i roku.
    Zapewnia, że lokator widzi tylko swój raport.
    """
    agreement = get_object_or_404(Agreement, pk=pk)

    if not request.user.is_superuser:
        if agreement.user.email != request.user.email:
            return HttpResponseForbidden("Nie masz uprawnień do przeglądania tego raportu.")

    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year

    context = get_annual_report_context(agreement, selected_year, _cache={})
    return render(request, 'core/annual_agreement_report.html', context)
