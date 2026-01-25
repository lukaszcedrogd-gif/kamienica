from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from datetime import date
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.forms import modelform_factory
from django.contrib import messages
import csv
import io
import datetime
import re
from decimal import Decimal, InvalidOperation
from django.db.models import Q
from .models import User, Agreement, Lokal, Meter, MeterReading, FinancialTransaction, CategorizationRule, LokalAssignmentRule, FixedCost, WaterCostOverride
from .forms import UserForm, AgreementForm, LokalForm, MeterReadingForm, CSVUploadForm
from collections import defaultdict
from .models import Lokal, Meter, WaterCostOverride
from .forms import LokalForm

# PDF Generation Imports
import io
from django.http import FileResponse
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# --- List Views ---

def user_list(request):
    users = User.objects.all() # .objects is the ActiveManager, so this gets only active users
    return render(request, 'users/user_list.html', {'users': users})

def lokal_list(request):
    lokale = Lokal.objects.all() # .objects is the ActiveManager
    return render(request, 'core/lokal_list.html', {'lokale': lokale})

def lokal_detail(request, pk):
    lokal = get_object_or_404(Lokal, pk=pk)
    # Prefetch related meters and their readings for efficiency
    meters = lokal.meters.prefetch_related('readings').filter(status='aktywny')
    context = {
        'lokal': lokal,
        'meters': meters,
    }
    return render(request, 'core/lokal_detail.html', context)

def agreement_list(request):
    agreements = list(Agreement.objects.all()) # .objects is the ActiveManager

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

    agreements.sort(key=lambda x: natural_sort_key(x.lokal))
    return render(request, 'core/agreement_list.html', {'agreements': agreements})

def meter_readings_view(request):
    lokale = Lokal.objects.prefetch_related('meters__readings').all()

    if request.method == 'POST':
        for lokal in lokale:
            for meter in lokal.meters.all():
                reading_value = request.POST.get(f'meter_{meter.id}')
                if reading_value:
                    MeterReading.objects.create(
                        meter=meter,
                        value=reading_value,
                        reading_date=request.POST.get('date') # You might want to get the date from the form
                    )
        return redirect('meter_readings')

    context = {'lokale': lokale}
    return render(request, 'core/meter_readings.html', context)


# --- Create Views ---

def create_user(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('user_list')
    else:
        form = UserForm()
    return render(request, 'core/user_form.html', {'form': form, 'title': 'Dodaj nowego użytkownika'})

def create_lokal(request):
    if request.method == 'POST':
        form = LokalForm(request.POST)
        if form.is_valid():
            lokal = form.save()
            
            # Obsługa przypisywania liczników
            meter_ids = request.POST.getlist('meters')
            
            # Przypisz wybrane liczniki do nowo utworzonego lokalu
            if meter_ids:
                meters_to_assign = Meter.objects.filter(id__in=meter_ids)
                for meter in meters_to_assign:
                    meter.lokal = lokal
                    meter.save()
            
            messages.success(request, f'Lokal {lokal.unit_number} został utworzony.')
            return redirect('lokal_list')
    else:
        form = LokalForm()

    # Pobierz liczniki nieprzypisane do żadnego lokalu (do wyboru)
    unassigned_meters = Meter.objects.filter(lokal__isnull=True, status='aktywny')
    
    context = {
        'form': form,
        'title': 'Dodaj nowy lokal',
        'unassigned_meters': unassigned_meters,
        'assigned_meters': [], # Nowy lokal nie ma jeszcze liczników
    }
    return render(request, 'core/lokal_form.html', context)

def edit_lokal(request, pk):
    lokal = get_object_or_404(Lokal, pk=pk)
    
    if request.method == 'POST':
        form = LokalForm(request.POST, instance=lokal)
        if form.is_valid():
            lokal = form.save()
            
            # Obsługa liczników
            meter_ids = request.POST.getlist('meters')
            
            # 1. Odepnij liczniki, które były przypisane do tego lokalu, ale zostały odznaczone
            # Szukamy liczników tego lokalu, których ID NIE ma na liście z formularza
            meters_to_detach = Meter.objects.filter(lokal=lokal).exclude(id__in=meter_ids)
            for meter in meters_to_detach:
                meter.lokal = None
                meter.save()
            
            # 2. Przypisz zaznaczone liczniki (lub upewnij się, że są przypisane)
            if meter_ids:
                meters_to_assign = Meter.objects.filter(id__in=meter_ids)
                for meter in meters_to_assign:
                    meter.lokal = lokal
                    meter.save()
            
            messages.success(request, f'Lokal {lokal.unit_number} został zaktualizowany.')
            return redirect('lokal_list')
    else:
        form = LokalForm(instance=lokal)

    # Liczniki aktualnie przypisane do tego lokalu
    assigned_meters = Meter.objects.filter(lokal=lokal)
    
    # Liczniki wolne (nieprzypisane)
    unassigned_meters = Meter.objects.filter(lokal__isnull=True, status='aktywny')

    context = {
        'form': form,
        'title': f'Edycja lokalu {lokal.unit_number}',
        'assigned_meters': assigned_meters,
        'unassigned_meters': unassigned_meters,
    }
    return render(request, 'core/lokal_form.html', context)

def create_agreement(request):
    if request.method == 'POST':
        form = AgreementForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('agreement_list') # Corrected redirect
    else:
        form = AgreementForm()
    return render(request, 'core/agreement_form.html', {'form': form, 'title': 'Dodaj nową umowę'})

def add_meter_reading(request, meter_id):
    meter = get_object_or_404(Meter, pk=meter_id)
    if request.method == 'POST':
        form = MeterReadingForm(request.POST)
        if form.is_valid():
            reading = form.save(commit=False)
            reading.meter = meter
            reading.save()
            return redirect('lokal-detail', pk=meter.lokal.id)
    else:
        form = MeterReadingForm()
    return render(request, 'core/meter_reading_form.html', {
        'form': form,
        'meter': meter,
        'title': f'Dodaj odczyt dla licznika: {meter}'
    })

# --- Edit Views ---

def edit_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('user_list')
    else:
        form = UserForm(instance=user)
    return render(request, 'core/user_form.html', {'form': form, 'title': f'Edytuj użytkownika: {user}'})

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

# --- Delete Views (Soft Delete) ---

def delete_user(request, pk):
    obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('user_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'użytkownika', 'cancel_url': 'user_list'})

def delete_lokal(request, pk):
    obj = get_object_or_404(Lokal, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('lokal_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'lokal', 'cancel_url': 'lokal_list'})

def delete_agreement(request, pk):
    obj = get_object_or_404(Agreement, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('agreement_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'umowę', 'cancel_url': 'agreement_list'})

# --- Financial Views ---
from .services.transaction_processing import process_csv_file


def upload_csv(request):
    transactions = FinancialTransaction.objects.all().order_by('-posting_date')
    lokale = Lokal.objects.all().order_by('unit_number') # For the filter dropdown

    # Filtering
    category_filter = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search_query = request.GET.get('search_query')
    lokal_filter = request.GET.get('lokal_id')

    if category_filter:
        transactions = transactions.filter(title=category_filter)
    if lokal_filter:
        transactions = transactions.filter(lokal_id=lokal_filter)
    if date_from:
        transactions = transactions.filter(posting_date__gte=date_from)
    if date_to:
        transactions = transactions.filter(posting_date__lte=date_to)
    if search_query:
        transactions = transactions.filter(
            Q(description__icontains=search_query) | 
            Q(contractor__icontains=search_query)
        )

    context = {
        'form': CSVUploadForm(),
        'transactions': transactions,
        'upload_summary': request.session.pop('upload_summary', None),
        'rules_count': CategorizationRule.objects.count(),
        'title_choices': FinancialTransaction.TITLE_CHOICES,
        'lokale': lokale, # Pass lokale to template
        'current_category': category_filter,
        'current_lokal_id': lokal_filter, # Pass current filter value
        'current_date_from': date_from,
        'current_date_to': date_to,
        'current_search_query': search_query,
    }

    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            
            summary = process_csv_file(csv_file)

            if summary.get('error'):
                context['upload_summary'] = summary
                return render(request, 'core/upload_csv.html', context)
            
            request.session['upload_summary'] = {
                'processed_count': summary.get('processed_count', 0),
                'skipped_rows': summary.get('skipped_rows', [])
            }

            if summary.get('has_manual_work'):
                return redirect('categorize_transactions')
            else:
                messages.success(request, f"Import zakończony. Pomyślnie przetworzono {summary.get('processed_count', 0)} transakcji.")
                return redirect('upload_csv')

    return render(request, 'core/upload_csv.html', context)

def reprocess_transactions(request):
    # Wykluczamy transakcje edytowane ręcznie, aby ich nie nadpisać
    transactions = FinancialTransaction.objects.exclude(status='MANUALLY_EDITED')
    updated_count = 0

    for transaction in transactions:
        
        title, title_status, title_log = get_title_from_description(transaction.description, transaction.contractor)
        suggested_lokal, lokal_status, lokal_log = match_lokal_for_transaction(
            transaction.description, 
            transaction.contractor, 
            transaction.amount, 
            transaction.posting_date
        )

        final_status = 'PROCESSED'
        if title_status == 'CONFLICT' or lokal_status == 'CONFLICT':
            final_status = 'CONFLICT'
        elif title_status == 'UNPROCESSED':
            final_status = 'UNPROCESSED'
            
        full_log = f"Kategoryzacja Tytułu: {title_log} | Przypisanie Lokalu: {lokal_log}"

        # Sprawdzamy czy coś się zmieniło, ignorując processing_log, którego brakuje w bazie danych
        is_changed = (
            transaction.title != title or
            transaction.lokal != suggested_lokal or
            transaction.status != final_status
        )
        if is_changed: # Oryginalne sprawdzenie zawierało: or transaction.processing_log != full_log
            
            transaction.title = title
            transaction.lokal = suggested_lokal
            transaction.status = final_status
            # transaction.processing_log = full_log # Pole pominięte - brak w bazie danych
            transaction.save()
            updated_count += 1
            
    messages.success(request, f"Pomyślnie przetworzono ponownie transakcje. Zaktualizowano {updated_count} wpisów. Pominięto te edytowane ręcznie.")
    return redirect('upload_csv')

def categorize_transactions(request):
    transactions_to_process = FinancialTransaction.objects.filter(
        status__in=['UNPROCESSED', 'CONFLICT']
    ).order_by('-posting_date')
    
    lokale = Lokal.objects.filter(is_active=True)
    
    context = {
        'transactions': transactions_to_process,
        'title_choices': FinancialTransaction.TITLE_CHOICES,
        'lokale': lokale,
    }
    
    return render(request, 'core/categorize_transactions.html', context)

def save_categorization(request):
    if request.method == 'POST':
        transaction_ids = request.POST.getlist('transaction_id')

        for trans_id in transaction_ids:
            try:
                transaction = FinancialTransaction.objects.get(id=trans_id)
            except FinancialTransaction.DoesNotExist:
                continue

            title = request.POST.get(f'title_{trans_id}')
            lokal_id = request.POST.get(f'lokal_id_{trans_id}')
            
            keywords = request.POST.get(f'keywords_{trans_id}')
            lokal_keywords = request.POST.get(f'lokal_keywords_{trans_id}')

            # Aktualizacja transakcji
            if title:
                transaction.title = title
            if lokal_id:
                transaction.lokal_id = lokal_id
            
            # Oznaczamy jako ręcznie edytowane, aby chronić przed przyszłym automatycznym nadpisaniem
            transaction.status = 'MANUALLY_EDITED'
            # transaction.processing_log = "Transakcja została ręcznie skategoryzowana przez użytkownika." # Pole pominięte - brak w bazie danych
            transaction.save()

            # Tworzenie nowych reguł
            if keywords and title:
                CategorizationRule.objects.get_or_create(
                    keywords=keywords.strip(),
                    defaults={'title': title}
                )
            
            if lokal_keywords and lokal_id:
                LokalAssignmentRule.objects.get_or_create(
                    keywords=lokal_keywords.strip(),
                    defaults={'lokal_id': lokal_id}
                )

        messages.success(request, "Pomyślnie skategoryzowano i zapisano transakcje.")
        return redirect('upload_csv')
    
    return redirect('categorize_transactions')

def clear_all_transactions(request):
    if request.method == 'POST':
        FinancialTransaction.objects.all().delete()
        return redirect('upload_csv')
    return render(request, 'core/confirm_clear_transactions.html')

# --- Rule Management Views ---

def rule_list(request):
    rules = CategorizationRule.objects.all().order_by('keywords')
    return render(request, 'core/rule_list.html', {'rules': rules})

def edit_rule(request, pk):
    rule = get_object_or_404(CategorizationRule, pk=pk)
    RuleForm = modelform_factory(CategorizationRule, fields=['keywords', 'title'])
    
    if request.method == 'POST':
        form = RuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            return redirect('rule_list')
    else:
        form = RuleForm(instance=rule)
    return render(request, 'core/rule_form.html', {'form': form, 'title': f'Edytuj regułę: {rule.keywords}'})

def delete_rule(request, pk):
    rule = get_object_or_404(CategorizationRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        return redirect('rule_list')
    return render(request, 'core/confirm_delete.html', {'object': rule, 'type': 'regułę', 'cancel_url': 'rule_list'})

def edit_transaction(request, pk):
    transaction = get_object_or_404(FinancialTransaction, pk=pk)
    lokale = Lokal.objects.filter(is_active=True)
    
    if request.method == 'POST':
        new_category = request.POST.get('category')
        new_lokal_id = request.POST.get('lokal')
        create_rule = request.POST.get('create_rule') == 'on'
        keyword = request.POST.get('keyword')
        
        # Obsługa podziału transakcji
        enable_split = request.POST.get('enable_split') == 'on'
        split_amount_str = request.POST.get('split_amount')
        split_lokal_id = request.POST.get('split_lokal')
        remaining_amount_str = request.POST.get('remaining_amount')

        if enable_split and split_amount_str and split_lokal_id and remaining_amount_str:
            try:
                split_amount = Decimal(split_amount_str.replace(',', '.'))
                remaining_amount = Decimal(remaining_amount_str.replace(',', '.'))
                
                # Walidacja: czy suma kwot zgadza się z pierwotną kwotą
                if abs(split_amount + remaining_amount - transaction.amount) > Decimal('0.01'):
                    messages.error(request, f"Błąd: Suma kwot ({split_amount + remaining_amount}) nie zgadza się z pierwotną kwotą ({transaction.amount}).")
                    return redirect('transaction-edit', pk=pk)
                
                # 1. Aktualizacja bieżącej transakcji (kwota pozostała)
                transaction.amount = remaining_amount
                
                # 2. Utworzenie nowej transakcji (wydzielona część)
                new_trans_id = f"{transaction.transaction_id}_split" if transaction.transaction_id else None
                # Zabezpieczenie przed duplikatem ID
                if new_trans_id and FinancialTransaction.objects.filter(transaction_id=new_trans_id).exists():
                    import time
                    new_trans_id = f"{new_trans_id}_{int(time.time())}"

                FinancialTransaction.objects.create(
                    transaction_id=new_trans_id,
                    posting_date=transaction.posting_date,
                    amount=split_amount,
                    description=f"{transaction.description} (część wydzielona)",
                    contractor=transaction.contractor,
                    title=new_category if new_category else transaction.title, # Dziedziczy kategorię
                    lokal_id=split_lokal_id
                )
                messages.success(request, f"Pomyślnie wydzielono kwotę {split_amount} dla drugiego lokalu.")

            except (InvalidOperation, ValueError):
                messages.error(request, "Nieprawidłowy format kwoty do podziału.")
                return redirect('transaction-edit', pk=pk)
        elif enable_split:
            messages.error(request, "Wypełnij wszystkie pola podziału (kwoty i drugi lokal).")
            return redirect('transaction-edit', pk=pk)

        if new_category:
            transaction.title = new_category
        
        # Aktualizacja lokalu dla głównej transakcji (tej, która została po odjęciu kwoty)
        if new_lokal_id:
            transaction.lokal_id = new_lokal_id
        elif new_lokal_id == "":
            transaction.lokal = None
        
        # Oznaczamy jako ręcznie edytowane
        transaction.status = 'MANUALLY_EDITED'
        # transaction.processing_log = "Transakcja została ręcznie zedytowana przez użytkownika." # Pole pominięte - brak w bazie danych
        transaction.save()

        if create_rule and keyword:
            if new_category:
                CategorizationRule.objects.get_or_create(
                    keywords=keyword.strip(),
                    defaults={'title': new_category}
                )
            
            if new_lokal_id:
                LokalAssignmentRule.objects.get_or_create(
                    keywords=keyword.strip(),
                    defaults={'lokal_id': new_lokal_id}
                )
            messages.success(request, "Zaktualizowano transakcję i utworzono nową regułę.")
        else:
            messages.success(request, "Zaktualizowano transakcję.")
        
        return redirect('upload_csv')

    return render(request, 'core/transaction_edit.html', {
        'transaction': transaction,
        'title_choices': FinancialTransaction.TITLE_CHOICES,
        'lokale': lokale,
    })

def delete_transaction(request, pk):
    transaction = get_object_or_404(FinancialTransaction, pk=pk)
    
    # Próba znalezienia transakcji macierzystej (jeśli to był podział)
    parent_transaction = None
    if transaction.transaction_id and '_split' in transaction.transaction_id:
        # Logika: ID podziału to zazwyczaj "PARENTID_split" lub "PARENTID_split_TIMESTAMP"
        # Bierzemy wszystko przed ostatnim wystąpieniem "_split"
        potential_parent_id = transaction.transaction_id.rsplit('_split', 1)[0]
        parent_transaction = FinancialTransaction.objects.filter(transaction_id=potential_parent_id).first()

    # Sprawdzenie, czy to jest transakcja macierzysta (czy posiada wydzielone części)
    child_transactions = None
    if transaction.transaction_id:
        children = FinancialTransaction.objects.filter(transaction_id__startswith=f"{transaction.transaction_id}_split")
        if children.exists():
            child_transactions = children

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'merge' and parent_transaction:
            # Opcja "Cofnij podział": Dodaj kwotę z powrotem do rodzica i usuń tę transakcję
            parent_transaction.amount += transaction.amount
            parent_transaction.save()
            transaction.delete()
            messages.success(request, f"Cofnięto podział. Kwota {transaction.amount} została zwrócona do transakcji {parent_transaction.transaction_id}.")
        
        elif action == 'merge_children' and child_transactions:
            # Opcja dla rodzica: Scal dzieci z powrotem do rodzica
            total_restored = Decimal('0.00')
            count = 0
            for child in child_transactions:
                total_restored += child.amount
                count += 1
            
            transaction.amount += total_restored
            transaction.save()
            child_transactions.delete()
            messages.success(request, f"Scalono {count} części. Łączna kwota {total_restored} PLN wróciła do transakcji głównej.")

        elif action == 'delete_all' and child_transactions:
            # Opcja dla rodzica: Usuń wszystko (rodzica i dzieci)
            count = child_transactions.count() + 1
            child_transactions.delete()
            transaction.delete()
            messages.success(request, f"Usunięto transakcję główną oraz {count-1} powiązanych części.")
            
        else:
            # Zwykłe usuwanie
            transaction.delete()
            messages.success(request, "Transakcja została trwale usunięta.")
            
        return redirect('upload_csv')

    return render(request, 'core/transaction_confirm_delete.html', {
        'transaction': transaction,
        'parent_transaction': parent_transaction,
        'child_transactions': child_transactions
    })

def meter_consumption_report(request):
    meters = Meter.objects.select_related('lokal').prefetch_related('readings').filter(status='aktywny', lokal__isnull=False)
    consumption_data = []

    for meter in meters:
        readings = meter.readings.all()[:2]  # Pobieramy 2 najnowsze odczyty
        
        consumption = None
        latest_reading = None
        previous_reading = None

        if len(readings) == 2:
            latest_reading = readings[0]
            previous_reading = readings[1]
            consumption = latest_reading.value - previous_reading.value
        elif len(readings) == 1:
            latest_reading = readings[0]

        consumption_data.append({
            'meter': meter,
            'latest_reading': latest_reading,
            'previous_reading': previous_reading,
            'consumption': consumption,
        })

    context = {
        'consumption_data': consumption_data,
        'title': 'Raport Zużycia Mediów'
    }
    return render(request, 'core/meter_consumption_report.html', context)

# --- Fixed Costs View ---

def fixed_costs_view(request):
    # Get all waste rules, ordered by date, to find the correct one for each month
    waste_rules = FixedCost.objects.filter(
        name__icontains="śmieci",
        calculation_method='per_person'
    ).order_by('-effective_date')

    if not waste_rules.exists():
        return render(request, 'core/fixed_costs_list.html', {'waste_rule': None, 'title': 'Błąd: Brak reguł kosztów'})

    calculated_costs = []
    grand_total_cost = Decimal('0.00')
    today = date.today()

    agreements = Agreement.objects.filter(is_active=True).select_related('lokal', 'user')

    for agreement in agreements:
        agreement_total_cost = Decimal('0.00')
        
        # Start from the beginning of the agreement's start month
        current_month_start = agreement.start_date.replace(day=1)
        months_counted = 0

        while current_month_start <= today:
            # Find the rule that was active in this month
            active_rule_for_month = None
            for rule in waste_rules:
                if rule.effective_date <= current_month_start:
                    active_rule_for_month = rule
                    break

            if active_rule_for_month:
                monthly_cost = agreement.number_of_occupants * active_rule_for_month.amount
                agreement_total_cost += monthly_cost
                months_counted += 1

            # Move to the next month
            current_month_start += relativedelta(months=1)
        
        if agreement_total_cost > 0:
            calculated_costs.append({
                'agreement': agreement,
                'total_cost': agreement_total_cost,
                'start_date': agreement.start_date,
                'months_counted': months_counted,
            })
            grand_total_cost += agreement_total_cost

    # Natural sort by lokal unit number
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]
    calculated_costs.sort(key=lambda x: natural_sort_key(x['agreement'].lokal.unit_number))

    context = {
        'waste_rule': waste_rules.first(), # For display, show the latest rule
        'calculated_costs': calculated_costs,
        'total_cost': grand_total_cost,
        'title': 'Koszty stałe - Wywóz śmieci (narastająco)'
    }
    return render(request, 'core/fixed_costs_list.html', context)


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


from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from datetime import date

def settlement(request, pk):
    agreement = get_object_or_404(Agreement.all_objects, pk=pk) # Use all_objects to get even inactive ones

    # Determine the settlement period (calendar year of the end date)
    if not agreement.end_date:
        # Fallback if somehow called on an agreement without an end date
        agreement.end_date = date.today()
        
    year = agreement.end_date.year
    period_start = date(year, 1, 1)
    period_end = date(year, 12, 31)

    # --- CALCULATIONS ---

    # 1. Calculate Total Rent
    total_rent = Decimal('0.00')
    current_month = period_start
    while current_month <= period_end:
        # Check if the agreement was active at any point in this month
        agreement_starts_before_month_end = agreement.start_date <= (current_month + relativedelta(months=1, days=-1))
        agreement_ends_after_month_start = agreement.end_date >= current_month
        
        if agreement_starts_before_month_end and agreement_ends_after_month_start:
            total_rent += agreement.rent_amount
        
        current_month += relativedelta(months=1)

    # 2. Calculate Total Fixed Costs (example for waste)
    total_fixed_costs = Decimal('0.00')
    waste_rule = FixedCost.objects.filter(name__icontains="śmieci", calculation_method='per_person').order_by('-effective_date').first()
    if waste_rule:
        current_month = period_start
        while current_month <= period_end:
            agreement_starts_before_month_end = agreement.start_date <= (current_month + relativedelta(months=1, days=-1))
            agreement_ends_after_month_start = agreement.end_date >= current_month

            if agreement_starts_before_month_end and agreement_ends_after_month_start and waste_rule.effective_date <= current_month:
                total_fixed_costs += waste_rule.amount * agreement.number_of_occupants

            current_month += relativedelta(months=1)

    # 3. Calculate Total Payments
    total_payments = FinancialTransaction.objects.filter(
        lokal=agreement.lokal,
        amount__gt=0, # Only income
        posting_date__range=(period_start, period_end)
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 4. Handle POST for additional costs
    additional_costs = Decimal('0.00')
    if request.method == 'POST':
        try:
            additional_costs = Decimal(request.POST.get('additional_costs', '0.00').replace(',', '.'))
        except (InvalidOperation, ValueError):
            messages.error(request, "Nieprawidłowa wartość w polu 'Koszty dodatkowe'.")
            additional_costs = Decimal('0.00')
    
    # 5. Calculate final totals
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


def bimonthly_report_list_view(request):
    lokale = Lokal.objects.all().order_by('unit_number')
    context = {
        'title': 'Raporty dwumiesięczne - Wybór lokalu',
        'lokale': lokale
    }
    return render(request, 'core/bimonthly_report_list.html', context)


from .services.reporting import get_bimonthly_report_context, get_annual_report_context


def bimonthly_report_view(request, pk):
    lokal = get_object_or_404(Lokal, pk=pk)
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


def annual_agreement_report(request, pk):
    agreement = get_object_or_404(Agreement, pk=pk)
    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year
    
    # Initialize a cache for this request to memoize report calculations
    context = get_annual_report_context(agreement, selected_year, _cache={})
    return render(request, 'core/annual_agreement_report.html', context)


def water_cost_summary_view(request):
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
                
                # Zawsze aktualizujemy, aby umożliwić wyczyszczenie pól
                override.overridden_bill_amount = bill_amount
                override.overridden_total_consumption = total_consumption
                override.save()

            except (ValueError, InvalidOperation) as e:
                messages.error(request, f"Błąd podczas przetwarzania danych dla okresu {period_start_str}: {e}")
                continue
        
        messages.success(request, "Pomyślnie zaktualizowano ręczne ustawienia kosztów wody.")
        return redirect('water_cost_summary')


    # GET request
    report_data = []
    today = date.today()
    
    current_period_start_month = today.month if today.month % 2 != 0 else today.month - 1
    period_start = date(today.year, current_period_start_month, 1)

    all_lokals_with_water = Lokal.objects.filter(
        is_active=True,
        meters__type__in=['hot_water', 'cold_water'],
        meters__status='aktywny'
    ).exclude(unit_number__iexact='kamienica').distinct().prefetch_related('meters__readings')

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


def water_cost_table(request):
    # --- Year Selection ---
    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year
    
    current_year = date.today().year
    available_years = list(range(current_year, current_year - 6, -1))

    # --- Data Calculation (same as before) ---
    lokals = Lokal.objects.filter(is_active=True).exclude(unit_number__iexact='kamienica').order_by('unit_number')
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
            # Handle edge case where reading is early in the month, belongs to previous period
            if end_date.day < 15 and end_date.month % 2 != 0:
                 # e.g., reading on March 5th should likely close Jan-Feb period
                 effective_date = end_date - relativedelta(months=2)
                 period_start_month = ((effective_date.month - 1) // 2) * 2 + 1
                 period_key = date(effective_date.year, period_start_month, 1)
            else:
                 period_key = date(end_date.year, period_start_month, 1)

            consumptions[period_key][meter.lokal_id] += consumption

    # --- Period and Cost Structuring (uses selected_year) ---
    period_names = [
        "styczeń-luty", "marzec-kwiecień", "maj-czerwiec", 
        "lipiec-sierpień", "wrzesień-październik", "listopad-grudzień"
    ]
    
    table_data = []
    month_start_num = 1
    for name in period_names:
        period_start_date = date(selected_year, month_start_num, 1)
        period_end_date = period_start_date + relativedelta(months=2, days=-1)
        
        # 1. Oblicz całkowite zużycie dla okresu
        total_row_consumption = Decimal('0.00')
        for lokal in lokals:
            total_row_consumption += consumptions[period_start_date].get(lokal.id, Decimal('0.00'))

        # 2. Oblicz cenę jednostkową na podstawie obliczonego zużycia
        override_obj = WaterCostOverride.objects.filter(period_start_date=period_start_date).first()
        unit_price = Decimal('0.00')
        if override_obj and override_obj.overridden_bill_amount and total_row_consumption > 0:
            unit_price = override_obj.overridden_bill_amount / total_row_consumption

        # 3. Zbuduj wiersz danych dla szablonu
        row = {
            'report': {
                'name': f"{name} {selected_year}",
                'unit_price': unit_price
            },
            'details': []
        }
        total_row_cost = Decimal('0.00')

        for lokal in lokals:
            lokal_consumption = consumptions[period_start_date].get(lokal.id, Decimal('0.00'))
            cost = lokal_consumption * unit_price
            
            row['details'].append({
                'consumption': lokal_consumption,
                'cost': cost
            })
            
            total_row_cost += cost
            
        row['total_cost'] = total_row_cost
        row['total_consumption'] = total_row_consumption # Już obliczone
        table_data.append(row)
        
        month_start_num += 2

    table_data.reverse()

    context = {
        'lokals': lokals,
        'table_data': table_data,
        'title': f'Tabela kosztów wody dla roku {selected_year}',
        'available_years': available_years,
        'selected_year': selected_year,
    }
    return render(request, 'core/water_cost_table.html', context)
import os
from Kamienica.settings import BASE_DIR
# ... (other imports)

def annual_report_pdf(request, pk):
    agreement = get_object_or_404(Agreement, pk=pk)
    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year

    context = _get_annual_report_context(agreement, selected_year, _cache={})

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # --- Font Registration ---
    font_name = 'Helvetica'
    font_name_bold = 'Helvetica-Bold'
    try:
        font_path_regular = os.path.join(BASE_DIR, 'Roboto', 'static', 'Roboto-Regular.ttf')
        font_path_bold = os.path.join(BASE_DIR, 'Roboto', 'static', 'Roboto-Bold.ttf')
        
        pdfmetrics.registerFont(TTFont('Roboto-Regular', font_path_regular))
        pdfmetrics.registerFont(TTFont('Roboto-Bold', font_path_bold))
        pdfmetrics.registerFontFamily('Roboto', normal='Roboto-Regular', bold='Roboto-Bold')
        
        font_name = 'Roboto-Regular'
        font_name_bold = 'Roboto-Bold'
    except:
        # Fallback to default fonts if local files are not found
        pass

    styles = getSampleStyleSheet()
    styles['Normal'].fontName = font_name
    styles['h1'].fontName = font_name_bold
    styles['h2'].fontName = font_name_bold
    styles['h1'].alignment = 1

    elements = []

    elements.append(Paragraph(context['title'], styles['h1']))
    elements.append(Spacer(1, 0.25*inch))

    elements.append(Paragraph('Podsumowanie roczne', styles['h2']))
    summary_data = [
        ['Suma wpłat:', f"{context['total_payments']:.2f} zł"],
        ['Należny czynsz:', f"{context['total_rent']:.2f} zł"],
        ['Wywóz śmieci:', f"{context['total_waste_cost_year']:.2f} zł"],
        ['Woda:', f"{context['total_water_cost_year']:.2f} zł"],
        ['Suma kosztów:', f"{context['total_costs']:.2f} zł"],
        ['Bilans:', f"{context['final_balance']:.2f} zł"]
    ]
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,4), (0,4), font_name_bold),
        ('FONTNAME', (0,5), (0,5), font_name_bold),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.25*inch))
    
    elements.append(Paragraph('Harmonogram Czynszu', styles['h2']))
    rent_data = [['Miesiąc', 'Należny Czynsz']]
    for item in context['rent_schedule']:
        rent_data.append([item['month_name'], f"{item['rent']:.2f} zł"])
    rent_data.append(['Suma:', f"{context['total_rent']:.2f} zł"])
    rent_table = Table(rent_data, colWidths=[2.5*inch, 2.5*inch])
    rent_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.gray),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('ALIGN', (0,0), (0,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTNAME', (0,0), (-1,0), font_name_bold),
        ('FONTNAME', (0,-1), (-1,-1), font_name_bold),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    elements.append(rent_table)
    elements.append(Spacer(1, 0.25*inch))

    # Bimonthly data
    elements.append(Paragraph('Zestawienie dwumiesięczne kosztów wody i wywozu śmieci', styles['h2']))
    bimonthly_header = ['Okres', 'Wywóz śmieci', 'Zużycie wody', 'Koszt wody']
    bimonthly_table_data = [bimonthly_header]
    for p in context['bimonthly_data']:
        bimonthly_table_data.append([
            p['name'],
            f"{p['waste_cost']:.2f} zł",
            f"{p['water_consumption']:.3f} m³",
            f"{p['water_cost']:.2f} zł"
        ])
    bimonthly_table_data.append(['Suma roczna:', f"{context['total_waste_cost_year']:.2f} zł", f"{context['total_water_consumption_year']:.3f} m³", f"{context['total_water_cost_year']:.2f} zł"])
    bimonthly_table = Table(bimonthly_table_data)
    bimonthly_table.setStyle(TableStyle([
       ('BACKGROUND', (0,0), (-1,0), colors.gray),
       ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
       ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
       ('ALIGN', (0,0), (0,-1), 'LEFT'),
       ('FONTNAME', (0,0), (-1,-1), font_name),
       ('FONTNAME', (0,0), (-1,0), font_name_bold),
       ('GRID', (0,0), (-1,-1), 1, colors.black),
       ('FONTNAME', (0,-1), (-1,-1), font_name_bold),
    ]))
    elements.append(bimonthly_table)
    elements.append(Spacer(1, 0.5*inch))

    # Payments
    elements.append(Paragraph('Wpłaty', styles['h2']))
    payment_data = [['Data', 'Opis', 'Kwota']]
    for p in context['cumulative_payments']:
        payment_data.append([p['date'].strftime('%Y-%m-%d'), p['description'] or '', f"{p['amount']:.2f} zł"])
    payment_data.append(['', 'Suma wpłat:', f"{context['total_payments']:.2f} zł"])
    payment_table = Table(payment_data, colWidths=[1*inch, 2.7*inch, 1.3*inch])
    payment_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.gray),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('ALIGN', (0,0), (1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTNAME', (0,0), (-1,0), font_name_bold),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('FONTNAME', (0,-1), (-1,-1), font_name_bold),
    ]))
    elements.append(payment_table)

    doc.build(elements)
    buffer.seek(0)
    
    filename = f"raport_roczny_{context['agreement'].lokal.unit_number}_{selected_year}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)
