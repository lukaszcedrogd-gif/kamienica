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
from .models import User, Agreement, Lokal, Meter, MeterReading, FinancialTransaction, CategorizationRule, LokalAssignmentRule, FixedCost
from .forms import UserForm, AgreementForm, LokalForm, MeterReadingForm, CSVUploadForm
from .models import Lokal, Meter
from .forms import LokalForm


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
def get_title_from_description(description, contractor=''):
    search_text = (description + ' ' + (contractor or '')).lower()
    rules = CategorizationRule.objects.all()
    
    matching_titles = []
    matched_rules_for_log = []

    for rule in rules:
        # Keywords are comma-separated phrases. We check each phrase using regex for whole-word matching.
        phrases = [p.strip().lower() for p in rule.keywords.split(',') if p.strip()]
        for phrase in phrases:
            if re.search(r'\b' + re.escape(phrase) + r'\b', search_text):
                matching_titles.append(rule.title)
                matched_rules_for_log.append(f"'{rule.keywords}'")
                break # A rule matches if any of its phrases match. Move to next rule.

    unique_matches = list(set(matching_titles))

    if len(unique_matches) == 1:
        log = f"Dopasowano regułę: {', '.join(matched_rules_for_log)}."
        return unique_matches[0], 'PROCESSED', log
    elif len(unique_matches) > 1:
        log = f"Konflikt, dopasowano reguły: {', '.join(matched_rules_for_log)}."
        return None, 'CONFLICT', log

    # Fallback to the old logic if no rule is found
    description_lower = description.lower()
    fallback_map = {
        'opłata za prowadzenie rachunku': 'oplata_bankowa',
        'opłata mies. karta': 'oplata_bankowa',
        'opłata za wywóz śmieci': 'wywoz_smieci',
        'pzu': 'ubezpieczenie',
        'aqua': 'oplata_za_wode',
        'czynsz': 'czynsz',
        'tauron': 'energia_klatka',
        'podatek': 'podatek',
        'pit': 'podatek',
    }
    for keyword, title in fallback_map.items():
        if keyword in description_lower:
            return title, 'PROCESSED', f"Dopasowano regułę wbudowaną dla '{keyword}'."
        
    return None, 'UNPROCESSED', "Nie znaleziono pasującej reguły."

def match_lokal_for_transaction(description, contractor, amount, posting_date):
    log_messages = []
    
    # Reguła nadrzędna: Ujemne kwoty (koszty) są przypisywane do "kamienicy"
    if amount < 0:
        try:
            kamienica_lokal = Lokal.objects.get(unit_number__iexact='kamienica')
            log_message = "Automatycznie przypisano do 'kamienica' (transakcja kosztowa)."
            return kamienica_lokal, 'PROCESSED', log_message
        except Lokal.DoesNotExist:
            log_messages.append("Nie znaleziono lokalu 'kamienica' dla transakcji kosztowej.")
            # Kontynuujemy, może inna reguła coś znajdzie

    search_text = (description + ' ' + (contractor or '')).lower()
    found_lokals = []
    
    # 1. Sprawdzenie Reguł (Słowa kluczowe / Nr konta)
    for rule in LokalAssignmentRule.objects.all():
        if re.search(r'\b' + re.escape(rule.keywords.lower()) + r'\b', search_text):
            found_lokals.append(rule.lokal)
            log_messages.append(f"Dopasowano regułę przypisania lokalu: '{rule.keywords}' -> Lokal {rule.lokal.unit_number}.")

    # 2. Analiza tekstowa (Regex) - szukanie "lok/m/nr" + liczba
    # Poprawiona reguła, aby 'm.' nie było mylone z 'mieszkanie' w adresach
    matches = re.finditer(r'\b(lok|mieszkanie|nr)\.?\s*(\d+[a-zA-Z]?)|\bm\s*(\d+[a-zA-Z]?)', search_text)
    for match in matches:
        # Numer lokalu może być w drugiej lub trzeciej grupie przechwytującej, w zależności od części reguły
        unit_num = match.group(2) or match.group(3)
        if unit_num:
            try:
                lokal = Lokal.objects.get(unit_number__iexact=unit_num)
                found_lokals.append(lokal)
                log_messages.append(f"Dopasowano numer lokalu w tekście: '{match.group(0)}' -> Lokal {lokal.unit_number}.")
            except Lokal.DoesNotExist:
                pass

    # 3. Analiza Umów (Osoby)
    users = User.objects.filter(is_active=True, role__in=['lokator', 'wlasciciel'])
    for user in users:
        if user.lastname.lower() in search_text and user.name.lower() in search_text:
            agreement = Agreement.objects.filter(user=user, is_active=True, start_date__lte=posting_date).filter(Q(end_date__gte=posting_date) | Q(end_date__isnull=True)).first()
            if agreement:
                found_lokals.append(agreement.lokal)
                log_messages.append(f"Dopasowano najemcę: '{user.name} {user.lastname}' -> Lokal {agreement.lokal.unit_number}.")

    unique_lokals = list(set(found_lokals))

    if len(unique_lokals) == 1:
        final_log = " ".join(log_messages)
        return unique_lokals[0], 'PROCESSED', final_log
    elif len(unique_lokals) > 1:
        final_log = "Konflikt: Znaleziono wiele pasujących lokali. " + " ".join(log_messages)
        return None, 'CONFLICT', final_log
    else:
        return None, 'UNPROCESSED', "Nie znaleziono pasującego lokalu."

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
            try:
                decoded_file = csv_file.read().decode('windows-1250')
            except UnicodeDecodeError:
                csv_file.seek(0)
                decoded_file = csv_file.read().decode('utf-8', errors='ignore')

            io_string = io.StringIO(decoded_file)
            
            header_found = False
            for row in csv.reader(io.StringIO(decoded_file), delimiter=';'):
                if row and row[0] == "Data transakcji":
                    header_found = True
                    break
            
            if not header_found:
                context['upload_summary'] = {'error': 'Nie znaleziono nagłówka "Data transakcji" w pliku CSV.'}
                return render(request, 'core/upload_csv.html', context)

            io_string = io.StringIO(decoded_file)
            reader = csv.reader(io_string, delimiter=';')
            for row in reader:
                if row and row[0] == "Data transakcji":
                    break

            processed_count = 0
            skipped_rows = []
            has_manual_work = False
            row_num = 1

            for row in reader:
                row_num += 1
                if not row or (row and row[0].startswith("Dokument ma charakter informacyjny")):
                    break
                
                if len(row) > 8:
                    try:
                        date_str = row[0].strip()
                        parsed_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                        
                        amount_str = row[8].replace(',', '.').strip()
                        if not amount_str:
                            skipped_rows.append((row_num, 'Pusta kwota'))
                            continue

                        amount = Decimal(amount_str)
                        description = row[3].strip()
                        contractor = row[2].strip()
                        transaction_id = row[7].strip()
                        
                        if not transaction_id:
                            skipped_rows.append((row_num, 'Pusty numer transakcji'))
                            continue
                        
                        title, title_status, title_log = get_title_from_description(description, contractor)
                        suggested_lokal, lokal_status, lokal_log = match_lokal_for_transaction(description, contractor, amount, parsed_date)

                        final_status = 'PROCESSED'
                        if title_status == 'CONFLICT' or lokal_status == 'CONFLICT':
                            final_status = 'CONFLICT'
                        elif title_status == 'UNPROCESSED':
                            final_status = 'UNPROCESSED'

                        if final_status != 'PROCESSED':
                            has_manual_work = True
                        
                        # Połączenie logów z obu funkcji
                        full_log = f"Kategoryzacja Tytułu: {title_log} | Przypisanie Lokalu: {lokal_log}"

                        FinancialTransaction.objects.update_or_create(
                            transaction_id=transaction_id,
                            defaults={
                                'posting_date': parsed_date,
                                'description': description,
                                'amount': amount,
                                'contractor': contractor,
                                'title': title,
                                'lokal': suggested_lokal,
                                'status': final_status,
                                # 'processing_log': full_log # Pole pominięte - brak w bazie danych
                            }
                        )
                        processed_count += 1

                    except (ValueError, InvalidOperation, IndexError) as e:
                        skipped_rows.append((row_num, str(e)))
                        continue
                else:
                    skipped_rows.append((row_num, 'Nieprawidłowa liczba kolumn'))
            
            request.session['upload_summary'] = {
                'processed_count': processed_count,
                'skipped_rows': skipped_rows
            }

            if has_manual_work:
                return redirect('categorize_transactions')
            else:
                messages.success(request, f"Import zakończony. Pomyślnie przetworzono {processed_count} transakcji.")
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


def bimonthly_report_view(request, pk):
    lokal = get_object_or_404(Lokal, pk=pk)
    agreement = Agreement.objects.filter(lokal=lokal, is_active=True).first()
    
    report_data = []
    # A dictionary to hold aggregated data for each period, keyed by (year, start_month)
    # e.g., {(2025, 1): {data}, (2025, 3): {data}}
    periods = {}

    water_meters = Meter.objects.filter(lokal=lokal, type__in=['hot_water', 'cold_water'], status='aktywny')
    
    if water_meters and agreement:
        for meter in water_meters:
            readings = list(meter.readings.all().order_by('reading_date'))

            # Iterate through readings in pairs
            for i in range(1, len(readings)):
                start_reading = readings[i-1]
                end_reading = readings[i]

                consumption = end_reading.value - start_reading.value

                # Heuristic to determine the period
                end_date = end_reading.reading_date
                year, month = end_date.year, end_date.month

                if month % 2 == 0: # Even month (Feb, Apr, etc.) -> period is (month-1, month)
                    period_start_month = month - 1
                else: # Odd month (Mar, May, etc.) -> period is (month-2, month-1)
                    period_start_month = month - 2
                
                # Handle January case (end reading is in Jan, so period is Nov-Dec of previous year)
                if period_start_month < 1:
                    period_start_month = 11
                    year -= 1

                period_key = (year, period_start_month)

                # Initialize period in dictionary if not present
                if period_key not in periods:
                    periods[period_key] = {
                        'period_start_date': date(year, period_start_month, 1),
                        'period_end_date': date(year, period_start_month, 1) + relativedelta(months=2, days=-1),
                        'consumption_by_meter': {},
                        'total_consumption': Decimal('0.00'),
                    }
                
                # Store consumption data for this specific meter and reading pair
                periods[period_key]['consumption_by_meter'][meter.get_type_display()] = {
                    'consumption': consumption,
                    'start_reading': start_reading,
                    'end_reading': end_reading,
                }
                periods[period_key]['total_consumption'] += consumption

        # Convert the dictionary to a list and calculate waste costs
        report_data = list(periods.values())
        for period in report_data:
            # Calculate waste disposal cost for this 2-month period
            waste_rule = FixedCost.objects.filter(name__icontains="śmieci", calculation_method='per_person', effective_date__lte=period['period_start_date']).order_by('-effective_date').first()
            if waste_rule:
                period['waste_cost'] = waste_rule.amount * agreement.number_of_occupants * 2
            else:
                period['waste_cost'] = Decimal('0.00')

    # Sort the data to show the most recent period first
    report_data.sort(key=lambda p: p['period_start_date'], reverse=True)

    context = {
        'lokal': lokal,
        'agreement': agreement,
        'title': f"Raport dwumiesięczny dla lokalu {lokal.unit_number}",
        'report_data': report_data,
    }
    return render(request, 'core/bimonthly_report.html', context)


