import time
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

from ..models import FinancialTransaction, CategorizationRule, LokalAssignmentRule, Lokal
from ..forms import CSVUploadForm
from ..services.transaction_processing import (
    process_csv_file,
    get_title_from_description,
    match_lokal_for_transaction,
)


@login_required
def upload_csv(request):
    """
    Obsługuje import transakcji finansowych z pliku CSV oraz wyświetla listę transakcji.
    """
    transactions = FinancialTransaction.objects.all().order_by('-posting_date')
    lokale = Lokal.objects.all().order_by('unit_number')

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
        'lokale': lokale,
        'current_category': category_filter,
        'current_lokal_id': lokal_filter,
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
                'skipped_rows': summary.get('skipped_rows', []),
                'encoding_warning': summary.get('encoding_warning', False),
            }

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
    edytowane ręcznie.
    """
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

        is_changed = (
            transaction.title != title or
            transaction.lokal != suggested_lokal or
            transaction.status != final_status
        )
        if is_changed:
            transaction.title = title
            transaction.lokal = suggested_lokal
            transaction.status = final_status
            transaction.save()
            updated_count += 1

    messages.success(request, f"Pomyślnie przetworzono ponownie transakcje. Zaktualizowano {updated_count} wpisów. Pominięto te edytowane ręcznie.")
    return redirect('upload_csv')


@login_required
def categorize_transactions(request):
    """
    Wyświetla stronę do ręcznej kategoryzacji transakcji, które nie zostały
    automatycznie przetworzone lub są w konflikcie.
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

            if title:
                transaction.title = title
            if lokal_id:
                transaction.lokal_id = lokal_id

            transaction.status = 'MANUALLY_EDITED'
            transaction.save()

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
    Dostępny wyłącznie dla administratorów. Wymaga potwierdzenia (metoda POST).
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    if request.method == 'POST':
        FinancialTransaction.objects.all().delete()
        return redirect('upload_csv')
    return render(request, 'core/confirm_clear_transactions.html')


@login_required
def edit_transaction(request, pk):
    """
    Umożliwia edycję pojedynczej transakcji, w tym zmianę kategorii, przypisanie
    do lokalu, a także podział transakcji na dwie mniejsze.
    """
    transaction = get_object_or_404(FinancialTransaction, pk=pk)
    lokale = Lokal.objects.filter(is_active=True)

    if request.method == 'POST':
        new_category = request.POST.get('category')
        new_lokal_id = request.POST.get('lokal')
        create_rule = request.POST.get('create_rule') == 'on'
        keyword = request.POST.get('keyword')

        enable_split = request.POST.get('enable_split') == 'on'
        split_amount_str = request.POST.get('split_amount')
        split_lokal_id = request.POST.get('split_lokal')
        remaining_amount_str = request.POST.get('remaining_amount')

        if enable_split and split_amount_str and split_lokal_id and remaining_amount_str:
            try:
                split_amount = Decimal(split_amount_str.replace(',', '.'))
                remaining_amount = Decimal(remaining_amount_str.replace(',', '.'))

                if abs(split_amount + remaining_amount - transaction.amount) > Decimal('0.01'):
                    messages.error(request, f"Błąd: Suma kwot ({split_amount + remaining_amount}) nie zgadza się z pierwotną kwotą ({transaction.amount}).")
                    return redirect('transaction-edit', pk=pk)

                transaction.amount = remaining_amount

                new_trans_id = f"{transaction.transaction_id}_split" if transaction.transaction_id else None
                if new_trans_id and FinancialTransaction.objects.filter(transaction_id=new_trans_id).exists():
                    new_trans_id = f"{new_trans_id}_{int(time.time())}"

                FinancialTransaction.objects.create(
                    transaction_id=new_trans_id,
                    posting_date=transaction.posting_date,
                    amount=split_amount,
                    description=f"{transaction.description} (część wydzielona)",
                    contractor=transaction.contractor,
                    title=new_category if new_category else transaction.title,
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

        if new_lokal_id:
            transaction.lokal_id = new_lokal_id
        elif new_lokal_id == "":
            transaction.lokal = None

        transaction.status = 'MANUALLY_EDITED'
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


@login_required
def delete_transaction(request, pk):
    """
    Obsługuje usuwanie transakcji z różnymi opcjami w zależności od tego,
    czy transakcja jest częścią podziału.
    """
    transaction = get_object_or_404(FinancialTransaction, pk=pk)

    parent_transaction = None
    if transaction.transaction_id and '_split' in transaction.transaction_id:
        potential_parent_id = transaction.transaction_id.rsplit('_split', 1)[0]
        parent_transaction = FinancialTransaction.objects.filter(transaction_id=potential_parent_id).first()

    child_transactions = None
    if transaction.transaction_id:
        children = FinancialTransaction.objects.filter(transaction_id__startswith=f"{transaction.transaction_id}_split")
        if children.exists():
            child_transactions = children

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'merge' and parent_transaction:
            parent_transaction.amount += transaction.amount
            parent_transaction.save()
            transaction.delete()
            messages.success(request, f"Cofnięto podział. Kwota {transaction.amount} została zwrócona do transakcji {parent_transaction.transaction_id}.")

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

        elif action == 'delete_all' and child_transactions:
            count = child_transactions.count() + 1
            child_transactions.delete()
            transaction.delete()
            messages.success(request, f"Usunięto transakcję główną oraz {count-1} powiązanych części.")

        else:
            transaction.delete()
            messages.success(request, "Transakcja została trwale usunięta.")

        return redirect('upload_csv')

    return render(request, 'core/transaction_confirm_delete.html', {
        'transaction': transaction,
        'parent_transaction': parent_transaction,
        'child_transactions': child_transactions
    })
