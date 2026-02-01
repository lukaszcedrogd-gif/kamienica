from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from datetime import date
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
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


def user_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Nieprawidłowy email lub hasło.')
    return render(request, 'core/login.html')

@login_required
def user_logout(request):
    logout(request)
    return redirect('login')

@login_required
def password_change(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(request, 'Your password was successfully updated!')
            return redirect('password_change_done')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'core/password_change_form.html', {
        'form': form
    })

@login_required
def password_change_done(request):
    return render(request, 'core/password_change_done.html')


# --- List Views ---

@login_required
def home(request):
    """
    Widok dyspozytora - przekierowuje użytkowników do odpowiedniego panelu.
    """
    if request.user.is_superuser:
        return user_list(request) # Superuser widzi listę użytkowników jako stronę główną
    else:
        try:
            agreement = Agreement.objects.get(user__email=request.user.email, is_active=True)
            return redirect('annual_agreement_report', pk=agreement.pk)
        except Agreement.DoesNotExist:
            messages.error(request, "Nie znaleziono aktywnej umowy dla Twojego konta.")
            return redirect('login')


@login_required
def user_list(request):
    """
    Wyświetla listę wszystkich aktywnych użytkowników.
    Dostępne tylko dla superużytkownika.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden("Nie masz uprawnień do przeglądania tej strony.")
        
    users = User.objects.all()
    return render(request, 'users/user_list.html', {'users': users, 'is_dashboard': True})

@login_required
def lokal_list(request):
    """
    Wyświetla listę lokali.
    Superużytkownik widzi wszystkie. Zwykły użytkownik (lokator) widzi tylko swój lokal.
    """
    if request.user.is_superuser:
        lokale = Lokal.objects.all()
    else:
        try:
            # Znajdź umowę powiązaną z zalogowanym użytkownikiem (przez email)
            agreement = Agreement.objects.get(user__email=request.user.email, is_active=True)
            lokale = [agreement.lokal] if agreement.lokal else []
        except Agreement.DoesNotExist:
            lokale = []
            
    return render(request, 'core/lokal_list.html', {'lokale': lokale})

@login_required
def lokal_detail(request, pk):
    """
    Wyświetla szczegóły konkretnego lokalu.
    Superużytkownik może zobaczyć każdy lokal. Lokator tylko swój.
    """
    lokal = get_object_or_404(Lokal, pk=pk)

    if not request.user.is_superuser:
        try:
            # Sprawdź, czy lokal z danego URL zgadza się z lokalem z umowy użytkownika
            agreement = Agreement.objects.get(user__email=request.user.email, is_active=True)
            if lokal.pk != agreement.lokal.pk:
                return HttpResponseForbidden("Nie masz uprawnień do przeglądania tego lokalu.")
        except Agreement.DoesNotExist:
            return HttpResponseForbidden("Nie masz przypisanej żadnej aktywnej umowy.")

    meters = lokal.meters.prefetch_related('readings').filter(status='aktywny')
    context = {
        'lokal': lokal,
        'meters': meters,
    }
    return render(request, 'core/lokal_detail.html', context)

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
def meter_readings_view(request):
    """
    Wyświetla formularz do wprowadzania odczytów liczników dla wszystkich lokali
    i przetwarza dane z tego formularza.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z formularzem odczytów lub przekierowanie.
    """
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

@login_required
def create_user(request):
    """
    Tworzy nowego użytkownika na podstawie danych z formularza.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z formularzem lub przekierowanie do listy użytkowników.
    """
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('user_list')
    else:
        form = UserForm()
    return render(request, 'core/user_form.html', {'form': form, 'title': 'Dodaj nowego użytkownika'})

@login_required
def create_lokal(request):
    """
    Tworzy nowy lokal i obsługuje przypisywanie do niego liczników.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z formularzem lub przekierowanie do listy lokali.
    """
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

@login_required
def edit_lokal(request, pk):
    """
    Edytuje istniejący lokal, w tym zarządza przypisaniem i odpinaniem liczników.

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) lokalu do edycji.

    Returns:
        HttpResponse: Renderowana strona z formularzem lub przekierowanie do listy lokali.
    """
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

@login_required
def create_agreement(request):
    """
    Tworzy nową umowę na podstawie danych z formularza.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z formularzem lub przekierowanie do listy umów.
    """
    if request.method == 'POST':
        form = AgreementForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('agreement_list') # Corrected redirect
    else:
        form = AgreementForm()
    return render(request, 'core/agreement_form.html', {'form': form, 'title': 'Dodaj nową umowę'})

@login_required
def add_meter_reading(request, meter_id):
    """
    Dodaje nowy odczyt dla konkretnego licznika.

    Args:
        request: Obiekt HttpRequest.
        meter_id (int): Klucz główny (ID) licznika.

    Returns:
        HttpResponse: Renderowana strona z formularzem lub przekierowanie do szczegółów lokalu.
    """
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

@login_required
def edit_user(request, pk):
    """
    Edytuje istniejącego użytkownika.

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) użytkownika do edycji.

    Returns:
        HttpResponse: Renderowana strona z formularzem lub przekierowanie do listy użytkowników.
    """
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('user_list')
    else:
        form = UserForm(instance=user)
    return render(request, 'core/user_form.html', {'form': form, 'title': f'Edytuj użytkownika: {user}'})

@login_required
def edit_agreement(request, pk):
    """
    Edytuje istniejącą umowę.

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) umowy do edycji.

    Returns:
        HttpResponse: Renderowana strona z formularzem lub przekierowanie do listy umów.
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

# --- Delete Views (Soft Delete) ---

@login_required
def delete_user(request, pk):
    """
    Dezaktywuje użytkownika (soft delete).

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) użytkownika do dezaktywacji.

    Returns:
        HttpResponse: Renderowana strona z potwierdzeniem lub przekierowanie do listy użytkowników.
    """
    obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('user_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'użytkownika', 'cancel_url': 'user_list'})

@login_required
def delete_lokal(request, pk):
    """
    Dezaktywuje lokal (soft delete).

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) lokalu do dezaktywacji.

    Returns:
        HttpResponse: Renderowana strona z potwierdzeniem lub przekierowanie do listy lokali.
    """
    obj = get_object_or_404(Lokal, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('lokal_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'lokal', 'cancel_url': 'lokal_list'})

@login_required
def delete_agreement(request, pk):
    """
    Dezaktywuje umowę (soft delete).

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) umowy do dezaktywacji.

    Returns:
        HttpResponse: Renderowana strona z potwierdzeniem lub przekierowanie do listy umów.
    """
    obj = get_object_or_404(Agreement, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('agreement_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'umowę', 'cancel_url': 'agreement_list'})

# --- Financial Views ---
from .services.transaction_processing import process_csv_file


@login_required
def upload_csv(request):
    """
    Obsługuje import transakcji finansowych z pliku CSV oraz wyświetla listę transakcji.

    GET: Wyświetla listę transakcji z możliwością filtrowania po kategorii, zakresie dat,
         lokalu i frazie w opisie lub u kontrahenta.
    POST: Przetwarza przesłany plik CSV, importuje transakcje i w razie potrzeby
          przekierowuje do strony ręcznej kategoryzacji.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z listą transakcji i formularzem do importu.
    """
    transactions = FinancialTransaction.objects.all().order_by('-posting_date')
    lokale = Lokal.objects.all().order_by('unit_number') # For the filter dropdown

    # --- Filtrowanie transakcji ---
    category_filter = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search_query = request.GET.get('search_query')
    lokal_filter = request.GET.get('lokal_id')

    # Filtracja po kategorii (tytule)
    if category_filter:
        transactions = transactions.filter(title=category_filter)
    # Filtracja po przypisanym lokalu
    if lokal_filter:
        transactions = transactions.filter(lokal_id=lokal_filter)
    # Filtracja po dacie początkowej
    if date_from:
        transactions = transactions.filter(posting_date__gte=date_from)
    # Filtracja po dacie końcowej
    if date_to:
        transactions = transactions.filter(posting_date__lte=date_to)
    # Wyszukiwanie tekstowe w opisie lub nazwie kontrahenta
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
            
            # Przetwarzanie pliku CSV przez dedykowany serwis
            summary = process_csv_file(csv_file)

            # W przypadku błędu krytycznego podczas przetwarzania, wyświetl informację
            if summary.get('error'):
                context['upload_summary'] = summary
                return render(request, 'core/upload_csv.html', context)
            
            # Zapisz podsumowanie importu w sesji, aby wyświetlić je po przekierowaniu
            request.session['upload_summary'] = {
                'processed_count': summary.get('processed_count', 0),
                'skipped_rows': summary.get('skipped_rows', [])
            }

            # Jeśli są transakcje wymagające ręcznej interwencji, przekieruj do kategoryzacji
            if summary.get('has_manual_work'):
                return redirect('categorize_transactions')
            else:
                messages.success(request, f"Import zakończony. Pomyślnie przetworzono {summary.get('processed_count', 0)} transakcji.")
                return redirect('upload_csv')

    return render(request, 'core/upload_csv.html', context)

@login_required
def reprocess_transactions(request):
    """
    Uruchamia ponowne przetwarzanie wszystkich transakcji, które nie były
    edytowane ręcznie. Stosuje istniejące reguły kategoryzacji i przypisywania
    do lokali.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Przekierowanie do strony importu CSV z komunikatem o wyniku.
    """
    # Wykluczamy transakcje edytowane ręcznie, aby ich nie nadpisać
    transactions = FinancialTransaction.objects.exclude(status='MANUALLY_EDITED')
    updated_count = 0

    for transaction in transactions:
        
        # Pobranie sugerowanego tytułu i lokalu na podstawie reguł
        title, title_status, title_log = get_title_from_description(transaction.description, transaction.contractor)
        suggested_lokal, lokal_status, lokal_log = match_lokal_for_transaction(
            transaction.description, 
            transaction.contractor, 
            transaction.amount, 
            transaction.posting_date
        )

        # Ustalenie ostatecznego statusu transakcji
        final_status = 'PROCESSED'
        if title_status == 'CONFLICT' or lokal_status == 'CONFLICT':
            final_status = 'CONFLICT'
        elif title_status == 'UNPROCESSED':
            final_status = 'UNPROCESSED'
            
        full_log = f"Kategoryzacja Tytułu: {title_log} | Przypisanie Lokalu: {lokal_log}"

        # Sprawdzenie, czy dane transakcji uległy zmianie
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

@login_required
def categorize_transactions(request):
    """
    Wyświetla stronę do ręcznej kategoryzacji transakcji, które nie zostały
    automatycznie przetworzone lub są w konflikcie.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z listą transakcji do kategoryzacji.
    """
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

@login_required
def save_categorization(request):
    """
    Zapisuje zmiany wprowadzone na stronie ręcznej kategoryzacji.
    Aktualizuje transakcje i opcjonalnie tworzy nowe reguły na podstawie
    wprowadzonych danych.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Przekierowanie do strony importu CSV lub strony kategoryzacji.
    """
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

            # Tworzenie nowych reguł, jeśli podano słowa kluczowe
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

@login_required
def clear_all_transactions(request):
    """
    Usuwa wszystkie transakcje finansowe z bazy danych.
    Wymaga potwierdzenia (metoda POST).

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z potwierdzeniem lub przekierowanie do listy transakcji.
    """
    if request.method == 'POST':
        FinancialTransaction.objects.all().delete()
        return redirect('upload_csv')
    return render(request, 'core/confirm_clear_transactions.html')

# --- Rule Management Views ---

@login_required
def rule_list(request):
    """
    Wyświetla listę wszystkich reguł kategoryzacji.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z listą reguł.
    """
    rules = CategorizationRule.objects.all().order_by('keywords')
    return render(request, 'core/rule_list.html', {'rules': rules})

@login_required
def edit_rule(request, pk):
    """
    Edytuje istniejącą regułę kategoryzacji.

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) reguły do edycji.

    Returns:
        HttpResponse: Renderowana strona z formularzem edycji lub przekierowanie do listy reguł.
    """
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

@login_required
def delete_rule(request, pk):
    """
    Usuwa regułę kategoryzacji. Wymaga potwierdzenia (metoda POST).

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) reguły do usunięcia.

    Returns:
        HttpResponse: Renderowana strona z potwierdzeniem lub przekierowanie do listy reguł.
    """
    rule = get_object_or_404(CategorizationRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        return redirect('rule_list')
    return render(request, 'core/confirm_delete.html', {'object': rule, 'type': 'regułę', 'cancel_url': 'rule_list'})

@login_required
def edit_transaction(request, pk):
    """
    Umożliwia edycję pojedynczej transakcji, w tym zmianę kategorii, przypisanie
    do lokalu, a także podział transakcji na dwie mniejsze.

    Obsługuje również tworzenie nowych reguł kategoryzacji na podstawie wprowadzonych zmian.

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) transakcji do edycji.

    Returns:
        HttpResponse: Renderowana strona z formularzem edycji lub przekierowanie do listy transakcji.
    """
    transaction = get_object_or_404(FinancialTransaction, pk=pk)
    lokale = Lokal.objects.filter(is_active=True)
    
    if request.method == 'POST':
        new_category = request.POST.get('category')
        new_lokal_id = request.POST.get('lokal')
        create_rule = request.POST.get('create_rule') == 'on'
        keyword = request.POST.get('keyword')
        
        # --- Obsługa podziału transakcji ---
        enable_split = request.POST.get('enable_split') == 'on'
        split_amount_str = request.POST.get('split_amount')
        split_lokal_id = request.POST.get('split_lokal')
        remaining_amount_str = request.POST.get('remaining_amount')

        if enable_split and split_amount_str and split_lokal_id and remaining_amount_str:
            try:
                split_amount = Decimal(split_amount_str.replace(',', '.'))
                remaining_amount = Decimal(remaining_amount_str.replace(',', '.'))
                
                # Walidacja: Sprawdzenie, czy suma kwot po podziale zgadza się z oryginałem
                if abs(split_amount + remaining_amount - transaction.amount) > Decimal('0.01'):
                    messages.error(request, f"Błąd: Suma kwot ({split_amount + remaining_amount}) nie zgadza się z pierwotną kwotą ({transaction.amount}).")
                    return redirect('transaction-edit', pk=pk)
                
                # 1. Aktualizacja bieżącej transakcji (zmniejszenie kwoty)
                transaction.amount = remaining_amount
                
                # 2. Utworzenie nowej transakcji dla wydzielonej części
                new_trans_id = f"{transaction.transaction_id}_split" if transaction.transaction_id else None
                # Zabezpieczenie przed duplikatem ID transakcji
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

        # Aktualizacja głównej transakcji (lub tej, która została po podziale)
        if new_category:
            transaction.title = new_category
        
        if new_lokal_id:
            transaction.lokal_id = new_lokal_id
        elif new_lokal_id == "": # Pozwala na odpięcie lokalu
            transaction.lokal = None
        
        # Oznaczenie transakcji jako ręcznie edytowanej
        transaction.status = 'MANUALLY_EDITED'
        # transaction.processing_log = "Transakcja została ręcznie zedytowana przez użytkownika." # Pole pominięte - brak w bazie danych
        transaction.save()

        # Opcjonalne tworzenie nowej reguły
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

@login_required
def delete_transaction(request, pk):
    """
    Obsługuje usuwanie transakcji z różnymi opcjami w zależności od tego,
    czy transakcja jest częścią podziału.

    - Zwykłe usunięcie: Usuwa pojedynczą transakcję.
    - Scalenie z rodzicem: Jeśli transakcja jest "dzieckiem" podziału, jej kwota
      jest zwracana do transakcji "rodzica", a ona sama jest usuwana.
    - Scalenie dzieci: Jeśli transakcja jest "rodzicem", wszystkie jej "dzieci"
      są scalane z powrotem w jedną transakcję.
    - Usunięcie wszystkich: Usuwa transakcję "rodzica" wraz ze wszystkimi "dziećmi".

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) transakcji do usunięcia.

    Returns:
        HttpResponse: Strona z potwierdzeniem lub przekierowanie do listy transakcji.
    """
    transaction = get_object_or_404(FinancialTransaction, pk=pk)
    
    # Logika do identyfikacji transakcji nadrzędnej (rodzica)
    parent_transaction = None
    if transaction.transaction_id and '_split' in transaction.transaction_id:
        # Zakładamy, że ID podziału ma format "ID_RODZICA_split" lub "ID_RODZICA_split_TIMESTAMP"
        # Bierzemy część ID przed ostatnim wystąpieniem "_split"
        potential_parent_id = transaction.transaction_id.rsplit('_split', 1)[0]
        parent_transaction = FinancialTransaction.objects.filter(transaction_id=potential_parent_id).first()

    # Logika do identyfikacji transakcji podrzędnych (dzieci)
    child_transactions = None
    if transaction.transaction_id:
        children = FinancialTransaction.objects.filter(transaction_id__startswith=f"{transaction.transaction_id}_split")
        if children.exists():
            child_transactions = children

    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Opcja 1: Scalanie "dziecka" z powrotem do "rodzica"
        if action == 'merge' and parent_transaction:
            parent_transaction.amount += transaction.amount
            parent_transaction.save()
            transaction.delete()
            messages.success(request, f"Cofnięto podział. Kwota {transaction.amount} została zwrócona do transakcji {parent_transaction.transaction_id}.")
        
        # Opcja 2: Scalanie wszystkich "dzieci" z powrotem do "rodzica"
        elif action == 'merge_children' and child_transactions:
            total_restored = Decimal('0.00')
            count = 0
            for child in child_transactions:
                total_restored += child.amount
                count += 1
            
            transaction.amount += total_restored
            transaction.save()
            child_transactions.delete()
            messages.success(request, f"Scalono {count} części. Łączna kwota {total_restored} PLN wróciła do transakcji głównej.")

        # Opcja 3: Usunięcie "rodzica" wraz ze wszystkimi "dziećmi"
        elif action == 'delete_all' and child_transactions:
            count = child_transactions.count() + 1
            child_transactions.delete()
            transaction.delete()
            messages.success(request, f"Usunięto transakcję główną oraz {count-1} powiązanych części.")
            
        # Domyślna akcja: Zwykłe usunięcie pojedynczej transakcji
        else:
            transaction.delete()
            messages.success(request, "Transakcja została trwale usunięta.")
            
        return redirect('upload_csv')

    return render(request, 'core/transaction_confirm_delete.html', {
        'transaction': transaction,
        'parent_transaction': parent_transaction,
        'child_transactions': child_transactions
    })
@login_required
def meter_consumption_report(request):
    """
    Generuje raport zużycia mediów na podstawie dwóch ostatnich odczytów
    dla każdego aktywnego licznika przypisanego do lokalu.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z raportem zużycia.
    """
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

@login_required
def fixed_costs_view(request):
    """
    Oblicza i wyświetla narastające koszty stałe (wywóz śmieci) dla wszystkich
    aktywnych umów od początku ich trwania do bieżącego dnia.

    Args:
        request: Obiekt HttpRequest.

    Returns:
        HttpResponse: Renderowana strona z listą kosztów stałych dla poszczególnych umów.
    """
    # Pobranie wszystkich reguł dotyczących kosztów wywozu śmieci
    waste_rules = FixedCost.objects.filter(
        name__icontains="śmieci",
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
        
        # Iteracja po miesiącach od początku trwania umowy
        current_month_start = agreement.start_date.replace(day=1)
        months_counted = 0

        while current_month_start <= today:
            # Znalezienie odpowiedniej reguły kosztowej dla danego miesiąca
            active_rule_for_month = None
            for rule in waste_rules:
                if rule.effective_date <= current_month_start:
                    active_rule_for_month = rule
                    break

            # Obliczenie i dodanie miesięcznego kosztu
            if active_rule_for_month:
                monthly_cost = agreement.number_of_occupants * active_rule_for_month.amount
                agreement_total_cost += monthly_cost
                months_counted += 1

            # Przejście do następnego miesiąca
            current_month_start += relativedelta(months=1)
        
        if agreement_total_cost > 0:
            calculated_costs.append({
                'agreement': agreement,
                'total_cost': agreement_total_cost,
                'start_date': agreement.start_date,
                'months_counted': months_counted,
            })
            grand_total_cost += agreement_total_cost

    # Sortowanie naturalne po numerze lokalu
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]
    calculated_costs.sort(key=lambda x: natural_sort_key(x['agreement'].lokal.unit_number))

    context = {
        'waste_rule': waste_rules.first(), # Do wyświetlenia najnowszej reguły
        'calculated_costs': calculated_costs,
        'total_cost': grand_total_cost,
        'title': 'Koszty stałe - Wywóz śmieci (narastająco)'
    }
    return render(request, 'core/fixed_costs_list.html', context)


@login_required
def terminate_agreement(request, pk):
    """
    Obsługuje proces zakończenia umowy. Ustawia datę końcową i dezaktywuje umowę,
    a następnie przekierowuje do strony rozliczenia końcowego.

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) umowy do zakończenia.

    Returns:
        HttpResponse: Renderowana strona z formularzem lub przekierowanie do rozliczenia.
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


from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from datetime import date

@login_required
def settlement(request, pk):
    """
    Generuje i wyświetla rozliczenie końcowe dla zakończonej umowy.
    Oblicza sumę czynszu, kosztów stałych, wpłat i kaucji w danym roku,
    aby określić ostateczny bilans.

    Args:
        request: Obiekt HttpRequest.
        pk (int): Klucz główny (ID) zakończonej umowy.

    Returns:
        HttpResponse: Renderowana strona z podsumowaniem rozliczenia.
    """
    agreement = get_object_or_404(Agreement.all_objects, pk=pk) # Użycie all_objects, aby pobrać także nieaktywne umowy

    # Określenie okresu rozliczeniowego (rok kalendarzowy, w którym umowa się zakończyła)
    if not agreement.end_date:
        agreement.end_date = date.today()
        
    year = agreement.end_date.year
    period_start = date(year, 1, 1)
    period_end = date(year, 12, 31)

    # --- OBLICZENIA ---

    # 1. Obliczenie sumy należnego czynszu w okresie rozliczeniowym
    total_rent = Decimal('0.00')
    current_month = period_start
    while current_month <= period_end:
        # Sprawdzenie, czy umowa była aktywna w danym miesiącu
        agreement_starts_before_month_end = agreement.start_date <= (current_month + relativedelta(months=1, days=-1))
        agreement_ends_after_month_start = agreement.end_date >= current_month
        
        if agreement_starts_before_month_end and agreement_ends_after_month_start:
            total_rent += agreement.rent_amount
        
        current_month += relativedelta(months=1)

    # 2. Obliczenie sumy kosztów stałych (np. za śmieci)
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

    # 3. Obliczenie sumy wpłat od najemcy w okresie rozliczeniowym
    total_payments = FinancialTransaction.objects.filter(
        lokal=agreement.lokal,
        amount__gt=0, # Tylko przychody
        posting_date__range=(period_start, period_end)
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 4. Obsługa dodatkowych kosztów wprowadzanych ręcznie w formularzu
    additional_costs = Decimal('0.00')
    if request.method == 'POST':
        try:
            additional_costs = Decimal(request.POST.get('additional_costs', '0.00').replace(',', '.'))
        except (InvalidOperation, ValueError):
            messages.error(request, "Nieprawidłowa wartość w polu 'Koszty dodatkowe'.")
            additional_costs = Decimal('0.00')
    
    # 5. Obliczenie ostatecznego bilansu
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




from .services.reporting import get_bimonthly_report_context, get_annual_report_context


@login_required
def bimonthly_report_view(request, pk):
    """
    Generuje i wyświetla raport dwumiesięczny dla wybranego lokalu i roku.
    Zapewnia, że lokator widzi tylko swój raport.
    """
    lokal = get_object_or_404(Lokal, pk=pk)
    
    # Security check
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
def annual_agreement_report(request, pk):
    """
    Generuje i wyświetla raport roczny dla wybranej umowy i roku.
    Zapewnia, że lokator widzi tylko swój raport.
    """
    agreement = get_object_or_404(Agreement, pk=pk)
    
    # Security check
    if not request.user.is_superuser:
        if agreement.user.email != request.user.email:
            return HttpResponseForbidden("Nie masz uprawnień do przeglądania tego raportu.")

    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year
    
    # Initialize a cache for this request to memoize report calculations
    context = get_annual_report_context(agreement, selected_year, _cache={})
    return render(request, 'core/annual_agreement_report.html', context)


@login_required
def water_cost_summary_view(request):
    """
    Panel do zarządzania kosztami wody. Dostępny tylko dla superużytkownika.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden("Nie masz uprawnień do zarządzania kosztami wody.")

    # --- Obsługa zapisu formularza (POST) ---
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
                
                # Znajdź lub utwórz obiekt nadpisania dla danego okresu
                override, created = WaterCostOverride.objects.get_or_create(
                    period_start_date=period_start_date
                )
                
                # Zawsze aktualizuj, aby umożliwić wyczyszczenie (usunięcie) nadpisań
                override.overridden_bill_amount = bill_amount
                override.overridden_total_consumption = total_consumption
                override.save()

            except (ValueError, InvalidOperation) as e:
                messages.error(request, f"Błąd podczas przetwarzania danych dla okresu {period_start_str}: {e}")
                continue
        
        messages.success(request, "Pomyślnie zaktualizowano ręczne ustawienia kosztów wody.")
        return redirect('water_cost_summary')

    # --- Logika wyświetlania danych (GET) ---
    report_data = []
    today = date.today()
    
    # Ustalenie początku bieżącego okresu dwumiesięcznego
    current_period_start_month = today.month if today.month % 2 != 0 else today.month - 1
    period_start = date(today.year, current_period_start_month, 1)

    # Pobranie wszystkich lokali z licznikami wody do obliczeń
    all_lokals_with_water = Lokal.objects.filter(
        is_active=True,
        meters__type__in=['hot_water', 'cold_water'],
        meters__status='aktywny'
    ).exclude(unit_number__iexact='kamienica').distinct().prefetch_related('meters__readings')

    # Pętla generująca dane dla 12 poprzednich okresów (2 lata)
    for _ in range(12):
        period_end = period_start + relativedelta(months=2, days=-1)

        # Sprawdzenie, czy istnieje ręczne nadpisanie dla tego okresu
        override_obj = WaterCostOverride.objects.filter(period_start_date=period_start).first()
        
        # Obliczenie ceny jednostkowej, jeśli są dostępne dane nadpisane
        unit_price = Decimal('0.00')
        if override_obj and override_obj.overridden_bill_amount and override_obj.overridden_total_consumption and override_obj.overridden_total_consumption > 0:
            unit_price = override_obj.overridden_bill_amount / override_obj.overridden_total_consumption

        # Obliczanie sumarycznego zużycia i kosztów dla wszystkich lokali w okresie
        total_lokal_water_costs = Decimal('0.00')
        total_calculated_consumption = Decimal('0.00')

        for lokal in all_lokals_with_water:
            lokal_consumption_for_period = Decimal('0.00')
            for meter in lokal.meters.all():
                if meter.type not in ['hot_water', 'cold_water']:
                    continue

                all_readings = sorted(meter.readings.all(), key=lambda r: r.reading_date)
                
                # Znalezienie odczytu początkowego i końcowego dla okresu
                start_reading = next((r for r in reversed(all_readings) if r.reading_date <= period_start), None)
                end_reading = next((r for r in all_readings if r.reading_date >= period_end), None)
                
                if start_reading and end_reading and start_reading.id != end_reading.id:
                    consumption = end_reading.value - start_reading.value
                    lokal_consumption_for_period += consumption
        
            total_calculated_consumption += lokal_consumption_for_period
            if unit_price > 0:
                total_lokal_water_costs += lokal_consumption_for_period * unit_price
        
        # Wyszukiwanie faktury za wodę pasującej do okresu rozliczeniowego
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
        
        # Przejście do poprzedniego okresu dwumiesięcznego
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

    # --- Filtrowanie lokali w zależności od uprawnień ---
    if request.user.is_superuser:
        lokals = Lokal.objects.filter(is_active=True).exclude(unit_number__iexact='kamienica').order_by('unit_number')
    else:
        try:
            agreement = Agreement.objects.get(user__email=request.user.email, is_active=True)
            lokals = Lokal.objects.filter(pk=agreement.lokal.pk) if agreement.lokal else Lokal.objects.none()
        except Agreement.DoesNotExist:
            lokals = Lokal.objects.none()

    # --- Obliczenie zużycia wody dla wybranych lokali ---
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

    # --- Strukturyzacja danych do tabeli ---
    period_names = [
        "styczeń-luty", "marzec-kwiecień", "maj-czerwiec", 
        "lipiec-sierpień", "wrzesień-październik", "listopad-grudzień"
    ]
    
    table_data = []
    month_start_num = 1
    for name in period_names:
        period_start_date = date(selected_year, month_start_num, 1)
        
        # Obliczenie ceny jednostkowej (logika ta jest złożona i zależy od superużytkownika)
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
import os
from Kamienica.settings import BASE_DIR

@login_required
def annual_report_pdf(request, pk):
    """
    Generuje raport roczny w formacie PDF dla danej umowy i roku.
    Zapewnia, że lokator może pobrać tylko swój raport.
    """
    agreement = get_object_or_404(Agreement, pk=pk)

    # Security check
    if not request.user.is_superuser:
        if agreement.user.email != request.user.email:
            return HttpResponseForbidden("Nie masz uprawnień do generowania tego raportu.")

    try:
        selected_year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        selected_year = date.today().year

    context = get_annual_report_context(agreement, selected_year, _cache={})
    # ... (reszta kodu generowania PDF bez zmian)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # --- Rejestracja czcionek ---
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
        pass

    styles = getSampleStyleSheet()
    styles['Normal'].fontName = font_name
    styles['h1'].fontName = font_name_bold
    styles['h2'].fontName = font_name_bold
    styles['h1'].alignment = 1

    elements = []

    # --- Budowanie dokumentu PDF ---
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
