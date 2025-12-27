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
    meters = lokal.meters.prefetch_related('readings').all()
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
                        date=request.POST.get('date') # You might want to get the date from the form
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
    unassigned_meters = Meter.objects.filter(lokal__isnull=True)
    
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
    unassigned_meters = Meter.objects.filter(lokal__isnull=True)

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
    # Szukamy w opisie ORAZ w nazwie kontrahenta (nr faktury/nazwa)
    search_text = (description + ' ' + contractor).lower()
    rules = CategorizationRule.objects.all()
    for rule in rules:
        keywords = [kw.strip().lower() for kw in rule.keywords.split(',') if kw.strip()]
        if keywords and any(keyword in search_text for keyword in keywords):
            return rule.title
    # Fallback to the old logic if no rule is found
    description_lower = description.lower()
    if 'opłata za prowadzenie rachunku' in description_lower:
        return 'oplata_bankowa'
    if 'opłata mies. karta' in description_lower:
        return 'oplata_bankowa'
    if 'opłata za wywóz śmieci' in description_lower:
        return 'wywoz_smieci'
    if 'pzu' in description_lower:
        return 'ubezpieczenie'
    if 'aqua' in description_lower:
        return 'oplata_za_wode'
    if 'czynsz' in description_lower:
        return 'czynsz'
    if 'tauron' in description_lower:
        return 'energia_klatka'
    if 'podatek' in description_lower:
        return 'podatek'
    if 'pit' in description_lower:
        return 'podatek'
    return None

def match_lokal_for_transaction(description, contractor, amount, posting_date):
    """
    Funkcja próbująca przypisać lokal do transakcji na podstawie:
    1. Reguł zdefiniowanych przez użytkownika (LokalAssignmentRule) - np. nr konta, nazwiska.
    2. Analizy tekstu pod kątem numeru lokalu (np. "m 4", "lok. 12").
    3. Wyszukiwania najemcy w bazie danych (Imię + Nazwisko) i sprawdzenia aktywnej umowy.
    """
    # Jeśli to wypłata (kwota ujemna), zazwyczaj nie przypisujemy lokalu (chyba że zwrot kaucji, ale to rzadkość)
    # Zgodnie z życzeniem pomijamy ujemne.
    if amount < 0:
        return None

    search_text = (description + ' ' + contractor).lower()

    # 1. Sprawdzenie Reguł (Słowa kluczowe / Nr konta)
    # To pokrywa przypadek "nr konta z którego przyszedł przelew"
    for rule in LokalAssignmentRule.objects.all():
        if rule.keywords.lower() in search_text:
            return rule.lokal

    # 2. Analiza tekstowa (Regex) - szukanie "lok/m/nr" + liczba
    # \b oznacza granicę słowa, więc nie złapie "blok" jako "lok"
    match = re.search(r'\b(lok|m|mieszkanie|nr)\.?\s*(\d+[a-zA-Z]?)', search_text)
    if match:
        unit_num = match.group(2)
        try:
            return Lokal.objects.get(unit_number=unit_num)
        except Lokal.DoesNotExist:
            pass # Szukamy dalej

    # 3. Analiza Umów (Osoby)
    # Szukamy użytkowników, których Imię ORAZ Nazwisko występują w tekście
    users = User.objects.filter(is_active=True, role__in=['lokator', 'wlasciciel'])
    for user in users:
        if user.lastname.lower() in search_text and user.name.lower() in search_text:
            # Znaleziono osobę, sprawdzamy czy miała aktywną umowę w dniu transakcji
            agreement = Agreement.objects.filter(user=user, is_active=True, start_date__lte=posting_date).filter(Q(end_date__gte=posting_date) | Q(end_date__isnull=True)).first()
            if agreement:
                return agreement.lokal

    return None

def upload_csv(request):
    transactions = FinancialTransaction.objects.all().order_by('-posting_date')

    # Filtering
    category_filter = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search_query = request.GET.get('search_query')

    if category_filter:
        transactions = transactions.filter(title=category_filter)
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
        'current_category': category_filter,
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
            uncategorized_rows = []
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
                        
                        title = get_title_from_description(description, contractor)
                        suggested_lokal = match_lokal_for_transaction(description, contractor, amount, parsed_date)

                        transaction_data = {
                            'posting_date': parsed_date.isoformat(),
                            'description': description,
                            'amount': str(amount),
                            'contractor': contractor,
                            'transaction_id': transaction_id,
                        }

                        if title:
                            FinancialTransaction.objects.update_or_create(
                                transaction_id=transaction_id,
                                defaults={**transaction_data, 'title': title, 'lokal': suggested_lokal}
                            )
                            processed_count += 1
                        else:
                            transaction_data['suggested_lokal_id'] = suggested_lokal.id if suggested_lokal else ''
                            uncategorized_rows.append(transaction_data)

                    except (ValueError, InvalidOperation, IndexError) as e:
                        skipped_rows.append((row_num, str(e)))
                        continue
                else:
                    skipped_rows.append((row_num, 'Nieprawidłowa liczba kolumn'))
            
            request.session['upload_summary'] = {
                'processed_count': processed_count,
                'skipped_rows': skipped_rows
            }

            if uncategorized_rows:
                request.session['uncategorized_rows'] = uncategorized_rows
                return redirect('categorize_transactions')
            
            context['upload_summary'] = request.session.pop('upload_summary', None)
            context['transactions'] = FinancialTransaction.objects.all().order_by('-posting_date')
            return redirect('upload_csv')

    return render(request, 'core/upload_csv.html', context)


def categorize_transactions(request):
    uncategorized_rows = request.session.get('uncategorized_rows', [])
    lokale = Lokal.objects.filter(is_active=True)
    
    context = {
        'transactions': uncategorized_rows,
        'title_choices': FinancialTransaction.TITLE_CHOICES,
        'upload_summary': request.session.get('upload_summary', {}),
        'lokale': lokale,
    }
    
    return render(request, 'core/categorize_transactions.html', context)

def save_categorization(request):
    if request.method == 'POST':
        try:
            transaction_count = int(request.POST.get('transaction_count', 0))
        except ValueError:
            transaction_count = 0

        for i in range(transaction_count):
            idx = str(i)
            transaction_id = request.POST.get(f'transaction_id_{idx}')
            title = request.POST.get(f'title_{idx}')
            keywords = request.POST.get(f'keywords_{idx}')
            lokal_id = request.POST.get(f'lokal_id_{idx}')
            lokal_keywords = request.POST.get(f'lokal_keywords_{idx}')
            
            # Pobieramy dane transakcji z ukrytych pól formularza
            description = request.POST.get(f'description_{idx}')
            posting_date = request.POST.get(f'posting_date_{idx}')
            amount = request.POST.get(f'amount_{idx}')
            contractor = request.POST.get(f'contractor_{idx}')

            defaults = {
                'description': description,
                'posting_date': posting_date,
                'amount': amount,
                'contractor': contractor,
                'title': title,
                'lokal_id': lokal_id if lokal_id else None
            }

            if transaction_id and title:
                FinancialTransaction.objects.update_or_create(
                    transaction_id=transaction_id,
                    defaults=defaults
                )

                if keywords:
                    CategorizationRule.objects.get_or_create(
                        keywords=keywords.strip(),
                        defaults={'title': title}
                    )
                
                if lokal_keywords and lokal_id:
                    LokalAssignmentRule.objects.get_or_create(
                        keywords=lokal_keywords.strip(),
                        defaults={'lokal_id': lokal_id}
                    )

        # Czyścimy sesję
        if 'uncategorized_rows' in request.session:
            del request.session['uncategorized_rows']
            
        messages.success(request, "Pomyślnie skategoryzowano i zapisano transakcje.")
        return redirect('upload_csv')
    
    return redirect('upload_csv')

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
    meters = Meter.objects.select_related('lokal').prefetch_related('readings').all()
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


