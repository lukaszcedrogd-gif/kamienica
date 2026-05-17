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

from ..decorators import require_admin
from ..models import Agreement, FinancialTransaction, FixedCost, User
from ..forms import AgreementForm
from ..services.reporting import get_annual_report_context


@login_required
def agreement_list(request):
    """
    Superużytkownik widzi wszystkie umowy. Lokator widzi tylko swoją aktywną.
    """
    if request.user.is_superuser:
        agreements_query = Agreement.objects.all()
    else:
        agreements_query = Agreement.objects.filter(user__email__iexact=request.user.email, is_active=True)

    agreements = list(agreements_query)

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

    agreements.sort(key=lambda x: natural_sort_key(x.lokal.unit_number))
    return render(request, 'core/agreement_list.html', {'agreements': agreements})


@require_admin
def create_agreement(request):
    if request.method == 'POST':
        form = AgreementForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('agreement_list')
    else:
        form = AgreementForm()
    return render(request, 'core/agreement_form.html', {'form': form, 'title': 'Dodaj nową umowę'})


@require_admin
def edit_agreement(request, pk):
    agreement = get_object_or_404(Agreement, pk=pk)
    if request.method == 'POST':
        form = AgreementForm(request.POST, instance=agreement)
        if form.is_valid():
            form.save()
            return redirect('agreement_list')
    else:
        form = AgreementForm(instance=agreement)
    return render(request, 'core/agreement_form.html', {'form': form, 'title': f'Edytuj umowę: {agreement}'})


@require_admin
def delete_agreement(request, pk):
    obj = get_object_or_404(Agreement, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('agreement_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'umowę', 'cancel_url': 'agreement_list'})


@require_admin
def terminate_agreement(request, pk):
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


@require_admin
def create_annex(request, pk):
    """
    Generuje aneks do istniejącej umowy. Wszystkie pola wstępnie wypełnione
    wartościami z oryginału — wypełniaj tylko to, co chcesz zmienić.
    Poprzednia umowa zostaje zarchiwizowana (is_active=False).
    """
    original = get_object_or_404(Agreement, pk=pk)

    users = User.objects.all().order_by('lastname', 'name')

    # Wartości domyślne jako stringi gotowe dla HTML date input (YYYY-MM-DD)
    defaults = {
        'user': str(original.user.pk),
        'signing_date': date.today().strftime('%Y-%m-%d'),
        'start_date': original.start_date.strftime('%Y-%m-%d'),
        'end_date': original.end_date.strftime('%Y-%m-%d') if original.end_date else '',
        'rent_amount': str(original.rent_amount),
        'deposit_amount': str(original.deposit_amount) if original.deposit_amount is not None else '',
        'number_of_occupants': str(original.number_of_occupants),
    }

    errors = {}

    if request.method == 'POST':

        def get_date(field):
            """Parsuje datę z POST; jeśli puste lub błędne — zwraca wartość domyślną."""
            raw = request.POST.get(field, '').strip()
            if not raw:
                return datetime.datetime.strptime(defaults[field], '%Y-%m-%d').date()
            try:
                return datetime.datetime.strptime(raw, '%Y-%m-%d').date()
            except ValueError:
                errors[field] = "Nieprawidłowy format daty (wymagany: RRRR-MM-DD)."
                return datetime.datetime.strptime(defaults[field], '%Y-%m-%d').date()

        def get_decimal(field, fallback):
            """Parsuje kwotę z POST; jeśli puste — zwraca fallback."""
            raw = request.POST.get(field, '').replace(',', '.').strip()
            if not raw:
                return fallback
            try:
                return Decimal(raw)
            except (InvalidOperation, ValueError):
                errors[field] = "Wprowadź prawidłową kwotę."
                return fallback

        def get_int(field, fallback):
            """Parsuje liczbę całkowitą z POST; jeśli puste — zwraca fallback."""
            raw = request.POST.get(field, '').strip()
            if not raw:
                return fallback
            try:
                val = int(raw)
                if val < 1:
                    raise ValueError
                return val
            except (ValueError, TypeError):
                errors[field] = "Wprowadź liczbę całkowitą większą od 0."
                return fallback

        user_id = request.POST.get('user', defaults['user'])
        try:
            annex_user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            errors['user'] = "Wybierz prawidłowego lokatora."
            annex_user = original.user

        signing_date = get_date('signing_date')
        start_date = get_date('start_date')
        end_date = get_date('end_date')
        rent_amount = get_decimal('rent_amount', original.rent_amount)
        deposit_amount = get_decimal('deposit_amount', original.deposit_amount)
        number_of_occupants = get_int('number_of_occupants', original.number_of_occupants)

        # Sprawdzenie konfliktu dat (z wyłączeniem oryginalnej umowy, która jest jeszcze aktywna)
        if not errors.get('start_date') and not errors.get('end_date'):
            conflict = Agreement.objects.filter(
                lokal=original.lokal,
                is_active=True,
                start_date__lte=end_date,
                end_date__gte=start_date,
            ).exclude(pk=original.pk).exists()
            if conflict:
                errors['dates'] = (
                    f"Dla lokalu {original.lokal.unit_number} istnieje już aktywna umowa "
                    f"pokrywająca się z wybranym okresem."
                )

        if not errors:
            annex = Agreement.objects.create(
                user=annex_user,
                lokal=original.lokal,
                signing_date=signing_date,
                start_date=start_date,
                end_date=end_date,
                rent_amount=rent_amount,
                deposit_amount=deposit_amount,
                type='aneks',
                old_agreement=original,
                additional_info=f"Aneks do umowy z dnia {original.signing_date}.\n{original.additional_info}",
                number_of_occupants=number_of_occupants,
                is_active=True,
            )
            original.is_active = False
            original.save()

            messages.success(
                request,
                f"Aneks dla lokalu {annex.lokal.unit_number} na okres "
                f"{annex.start_date} – {annex.end_date} został utworzony."
            )
            return redirect('agreement_list')

        # Przy błędach wróć z zachowanymi wartościami z POST
        form_data = {k: request.POST.get(k, defaults[k]) for k in defaults}
        context = {
            'original': original,
            'users': users,
            'errors': errors,
            'defaults': defaults,
            'form_data': form_data,
            'title': f'Generuj aneks: Lokal {original.lokal.unit_number}',
        }
        return render(request, 'core/annex_confirm.html', context)

    context = {
        'original': original,
        'users': users,
        'errors': {},
        'defaults': defaults,
        'form_data': defaults,  # pierwsze otwarcie = wartości domyślne
        'title': f'Generuj aneks: Lokal {original.lokal.unit_number}',
    }
    return render(request, 'core/annex_confirm.html', context)


@login_required
def settlement(request, pk):
    """
    Generuje rozliczenie końcowe dla zakończonej umowy.
    Lokator może przeglądać tylko swoje rozliczenie.
    """
    agreement = get_object_or_404(Agreement.all_objects, pk=pk)

    if not request.user.is_superuser:
        if agreement.user.email.lower() != request.user.email.lower():
            return HttpResponseForbidden("Nie masz uprawnień do przeglądania tego rozliczenia.")

    if not agreement.end_date:
        agreement.end_date = date.today()

    year = agreement.end_date.year
    period_start = date(year, 1, 1)
    period_end = date(year, 12, 31)

    total_rent = Decimal('0.00')
    current_month = period_start
    while current_month <= period_end:
        agreement_starts_before_month_end = agreement.start_date <= (current_month + relativedelta(months=1, days=-1))
        agreement_ends_after_month_start = agreement.end_date >= current_month

        if agreement_starts_before_month_end and agreement_ends_after_month_start:
            total_rent += agreement.rent_amount

        current_month += relativedelta(months=1)

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

    total_payments = FinancialTransaction.objects.filter(
        lokal=agreement.lokal,
        amount__gt=0,
        posting_date__range=(period_start, period_end)
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    additional_costs = Decimal('0.00')
    if request.method == 'POST':
        try:
            additional_costs = Decimal(request.POST.get('additional_costs', '0.00').replace(',', '.'))
        except (InvalidOperation, ValueError):
            messages.error(request, "Nieprawidłowa wartość w polu 'Koszty dodatkowe'.")
            additional_costs = Decimal('0.00')

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
    Raport roczny. Lokator może przeglądać tylko swój raport.
    """
    agreement = get_object_or_404(Agreement, pk=pk)

    if not request.user.is_superuser:
        if agreement.user.email.lower() != request.user.email.lower():
            return HttpResponseForbidden("Nie masz uprawnień do przeglądania tego raportu.")

    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year

    context = get_annual_report_context(agreement, selected_year, _cache={})
    return render(request, 'core/annual_agreement_report.html', context)
