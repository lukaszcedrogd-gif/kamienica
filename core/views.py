from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.forms import modelform_factory
from django.contrib import messages
import csv
import io
import datetime
from decimal import Decimal, InvalidOperation
from .models import User, Agreement, Lokal, Meter, MeterReading, FinancialTransaction, CategorizationRule
from .forms import UserForm, AgreementForm, LokalForm, MeterReadingForm, CSVUploadForm


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
    agreements = Agreement.objects.all() # .objects is the ActiveManager
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
            form.save()
            return redirect('lokal_list')
    else:
        form = LokalForm()
    return render(request, 'core/lokal_form.html', {'form': form, 'title': 'Dodaj Nowy Lokal'})

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

def edit_lokal(request, pk):
    lokal = get_object_or_404(Lokal, pk=pk)
    if request.method == 'POST':
        form = LokalForm(request.POST, instance=lokal)
        if form.is_valid():
            form.save()
            return redirect('lokal_list')
    else:
        form = LokalForm(instance=lokal)
    return render(request, 'core/lokal_form.html', {'form': form, 'title': f'Edytuj lokal: {lokal}'})

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
def get_title_from_description(description):
    description_lower = description.lower()
    rules = CategorizationRule.objects.all()
    for rule in rules:
        keywords = [kw.strip().lower() for kw in rule.keywords.split(',') if kw.strip()]
        if keywords and any(keyword in description_lower for keyword in keywords):
            return rule.title
    # Fallback to the old logic if no rule is found
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

def upload_csv(request):
    transactions = FinancialTransaction.objects.all().order_by('-posting_date')

    # Filtering
    category_filter = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if category_filter:
        transactions = transactions.filter(title=category_filter)
    if date_from:
        transactions = transactions.filter(posting_date__gte=date_from)
    if date_to:
        transactions = transactions.filter(posting_date__lte=date_to)

    context = {
        'form': CSVUploadForm(),
        'transactions': transactions,
        'upload_summary': request.session.pop('upload_summary', None),
        'rules_count': CategorizationRule.objects.count(),
        'title_choices': FinancialTransaction.TITLE_CHOICES,
        'current_category': category_filter,
        'current_date_from': date_from,
        'current_date_to': date_to,
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
                        
                        title = get_title_from_description(description)

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
                                defaults={**transaction_data, 'title': title}
                            )
                            processed_count += 1
                        else:
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
    
    context = {
        'transactions': uncategorized_rows,
        'title_choices': FinancialTransaction.TITLE_CHOICES,
        'upload_summary': request.session.get('upload_summary', {})
    }
    
    return render(request, 'core/categorize_transactions.html', context)

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
    
    if request.method == 'POST':
        new_category = request.POST.get('category')
        create_rule = request.POST.get('create_rule') == 'on'
        keyword = request.POST.get('keyword')

        if new_category:
            transaction.title = new_category
            transaction.save()

            if create_rule and keyword:
                CategorizationRule.objects.get_or_create(
                    keywords=keyword.strip(),
                    defaults={'title': new_category}
                )
                messages.success(request, "Zaktualizowano transakcję i utworzono nową regułę.")
            else:
                messages.success(request, "Zaktualizowano transakcję.")
            
            return redirect('upload_csv')

    return render(request, 'core/transaction_edit.html', {
        'transaction': transaction,
        'title_choices': FinancialTransaction.TITLE_CHOICES
    })
