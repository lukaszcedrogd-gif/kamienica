# core/services/transaction_processing.py

import csv
import io
import datetime
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Q
from ..models import (
    BUILDING_LOKAL_NUMBER,
    FinancialTransaction,
    CategorizationRule,
    LokalAssignmentRule,
    Lokal,
    User,
    Agreement,
)


def get_title_from_description(description, contractor="", categorization_rules=None):
    """
    Kategoryzuje transakcję na podstawie opisu i kontrahenta.
    Opcjonalny parametr `categorization_rules` pozwala przekazać wstępnie pobrane
    reguły (list), eliminując zapytanie do bazy przy przetwarzaniu wsadowym.
    """
    search_text = (description + " " + (contractor or "")).lower()
    if categorization_rules is None:
        categorization_rules = CategorizationRule.objects.all()

    matching_titles = []
    matched_rules_for_log = []

    for rule in categorization_rules:
        # Keywords are comma-separated phrases. We check each phrase using regex for whole-word matching.
        phrases = [p.strip().lower() for p in rule.keywords.split(",") if p.strip()]
        for phrase in phrases:
            if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", search_text):
                matching_titles.append(rule.title)
                matched_rules_for_log.append(f"'{rule.keywords}'")
                break  # A rule matches if any of its phrases match. Move to next rule.

    unique_matches = list(set(matching_titles))

    if len(unique_matches) == 1:
        log = f"Dopasowano regułę: {', '.join(matched_rules_for_log)}."
        return unique_matches[0], "PROCESSED", log
    elif len(unique_matches) > 1:
        log = f"Konflikt, dopasowano reguły: {', '.join(matched_rules_for_log)}."
        return None, "CONFLICT", log

    # Fallback to the old logic if no rule is found
    description_lower = description.lower()
    fallback_map = {
        "opłata za prowadzenie rachunku": "oplata_bankowa",
        "opłata mies. karta": "oplata_bankowa",
        "opłata za wywóz śmieci": "wywoz_smieci",
        "pzu": "ubezpieczenie",
        "aqua": "oplata_za_wode",
        "czynsz": "czynsz",
        "tauron": "energia_klatka",
        "podatek": "podatek",
        "pit": "podatek",
    }
    for keyword, title in fallback_map.items():
        if keyword in description_lower:
            return title, "PROCESSED", f"Dopasowano regułę wbudowaną dla '{keyword}'."

    return None, "UNPROCESSED", "Nie znaleziono pasującej reguły."


def match_lokal_for_transaction(
    description,
    contractor,
    amount,
    posting_date,
    assignment_rules=None,
    lokals_by_number=None,
    active_users=None,
    agreements_by_user=None,
):
    """
    Przypisuje lokal do transakcji na podstawie opisu, kontrahenta, kwoty i daty.
    Opcjonalne parametry pozwalają przekazać wstępnie pobrane dane (listy/słowniki),
    eliminując wielokrotne zapytania do bazy przy przetwarzaniu wsadowym.
    Bez tych parametrów funkcja działa samodzielnie i pobiera dane sama.
    """
    log_messages = []

    # Reguła nadrzędna: Ujemne kwoty (koszty) są przypisywane do "kamienicy"
    if amount < 0:
        if lokals_by_number is not None:
            kamienica_lokal = lokals_by_number.get(BUILDING_LOKAL_NUMBER)
        else:
            try:
                kamienica_lokal = Lokal.objects.get(unit_number__iexact=BUILDING_LOKAL_NUMBER)
            except Lokal.DoesNotExist:
                kamienica_lokal = None

        if kamienica_lokal:
            return kamienica_lokal, "PROCESSED", f"Automatycznie przypisano do '{BUILDING_LOKAL_NUMBER}' (transakcja kosztowa)."
        log_messages.append(f"Nie znaleziono lokalu '{BUILDING_LOKAL_NUMBER}' dla transakcji kosztowej.")
        # Kontynuujemy, może inna reguła coś znajdzie

    search_text = (description + " " + (contractor or "")).lower()
    found_lokals = []

    # 1. Sprawdzenie Reguł (Słowa kluczowe / Nr konta)
    if assignment_rules is None:
        assignment_rules = LokalAssignmentRule.objects.select_related("lokal").all()
    for rule in assignment_rules:
        if re.search(r"(?<!\w)" + re.escape(rule.keywords.lower()) + r"(?!\w)", search_text):
            found_lokals.append(rule.lokal)
            log_messages.append(
                f"Dopasowano regułę przypisania lokalu: '{rule.keywords}' -> Lokal {rule.lokal.unit_number}."
            )

    # 2. Analiza tekstowa (Regex) - szukanie "lok/m/nr" + liczba
    # Poprawiona reguła, aby 'm.' nie było mylone z 'mieszkanie' w adresach
    matches = re.finditer(
        r"\b(lok|mieszkanie|nr)\.?\s*(\d+[a-zA-Z]?)|\bm\s*(\d+[a-zA-Z]?)", search_text
    )
    for match in matches:
        # Numer lokalu może być w drugiej lub trzeciej grupie przechwytującej
        unit_num = match.group(2) or match.group(3)
        if unit_num:
            if lokals_by_number is not None:
                lokal = lokals_by_number.get(unit_num.lower())
            else:
                try:
                    lokal = Lokal.objects.get(unit_number__iexact=unit_num)
                except Lokal.DoesNotExist:
                    lokal = None
            if lokal:
                found_lokals.append(lokal)
                log_messages.append(
                    f"Dopasowano numer lokalu w tekście: '{match.group(0)}' -> Lokal {lokal.unit_number}."
                )

    # 3. Analiza Umów (Osoby)
    if active_users is None:
        active_users = list(User.objects.filter(is_active=True, role__in=["lokator", "wlasciciel"]))
    for user in active_users:
        if user.lastname.lower() in search_text and user.name.lower() in search_text:
            if agreements_by_user is not None:
                # Filtrowanie po datach w Pythonie — bez zapytania do bazy
                agreement = next(
                    (
                        ag for ag in agreements_by_user.get(user.id, [])
                        if ag.start_date <= posting_date
                        and (ag.end_date is None or ag.end_date >= posting_date)
                    ),
                    None,
                )
            else:
                agreement = (
                    Agreement.objects.filter(
                        user=user,
                        is_active=True,
                        start_date__lte=posting_date,
                    )
                    .filter(Q(end_date__gte=posting_date) | Q(end_date__isnull=True))
                    .first()
                )
            if agreement:
                found_lokals.append(agreement.lokal)
                log_messages.append(
                    f"Dopasowano najemcę: '{user.name} {user.lastname}' -> Lokal {agreement.lokal.unit_number}."
                )

    unique_lokals = list(set(found_lokals))

    if len(unique_lokals) == 1:
        final_log = " ".join(log_messages)
        return unique_lokals[0], "PROCESSED", final_log
    elif len(unique_lokals) > 1:
        final_log = (
            "Konflikt: Znaleziono wiele pasujących lokali. " + " ".join(log_messages)
        )
        return None, "CONFLICT", final_log
    else:
        return None, "UNPROCESSED", "Nie znaleziono pasującego lokalu."


def process_csv_file(file):
    encoding_warning = False
    try:
        decoded_file = file.read().decode("windows-1250")
    except UnicodeDecodeError:
        file.seek(0)
        decoded_file = file.read().decode("utf-8", errors="replace")
        # Znak \ufffd pojawia się w miejscu każdego bajtu niemożliwego do zdekodowania.
        # Może oznaczać uszkodzone liczby lub polskie znaki — zgłaszamy ostrzeżenie.
        encoding_warning = '\ufffd' in decoded_file

    header_found = False
    for row in csv.reader(io.StringIO(decoded_file), delimiter=";"):
        if row and row[0] == "Data transakcji":
            header_found = True
            break

    if not header_found:
        return {
            "error": 'Nie znaleziono nagłówka "Data transakcji" w pliku CSV.',
            "encoding_warning": encoding_warning,
        }

    io_string = io.StringIO(decoded_file)
    reader = csv.reader(io_string, delimiter=";")
    for row in reader:
        if row and row[0] == "Data transakcji":
            break

    # --- Jednorazowy prefetch wszystkich danych potrzebnych w pętli ---
    # Bez tego każda transakcja generowałaby oddzielne zapytania do bazy.
    categorization_rules = list(CategorizationRule.objects.all())
    assignment_rules = list(
        LokalAssignmentRule.objects.select_related("lokal").all()
    )
    lokals_by_number = {
        lokal.unit_number.lower(): lokal
        for lokal in Lokal.objects.all()
    }
    active_users = list(
        User.objects.filter(is_active=True, role__in=["lokator", "wlasciciel"])
    )
    active_agreements = list(
        Agreement.objects.filter(
            user__in=active_users, is_active=True
        ).select_related("user", "lokal")
    )
    agreements_by_user = defaultdict(list)
    for ag in active_agreements:
        agreements_by_user[ag.user_id].append(ag)

    processed_count = 0
    skipped_rows = []
    has_manual_work = False
    row_num = 1

    with transaction.atomic():
        for row in reader:
            row_num += 1
            if not row or (row and row[0].startswith("Dokument ma charakter informacyjny")):
                break

            if len(row) > 8:
                try:
                    date_str = row[0].strip()
                    parsed_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

                    amount_str = row[8].replace(",", ".").strip()
                    if not amount_str:
                        skipped_rows.append((row_num, "Pusta kwota"))
                        continue

                    amount = Decimal(amount_str)
                    description = row[3].strip()
                    contractor = row[2].strip()
                    transaction_id = row[7].strip()

                    if not transaction_id:
                        skipped_rows.append((row_num, "Pusty numer transakcji"))
                        continue

                    title, title_status, title_log = get_title_from_description(
                        description, contractor,
                        categorization_rules=categorization_rules,
                    )
                    (
                        suggested_lokal,
                        lokal_status,
                        lokal_log,
                    ) = match_lokal_for_transaction(
                        description, contractor, amount, parsed_date,
                        assignment_rules=assignment_rules,
                        lokals_by_number=lokals_by_number,
                        active_users=active_users,
                        agreements_by_user=agreements_by_user,
                    )

                    final_status = "PROCESSED"
                    if title_status == "CONFLICT" or lokal_status == "CONFLICT":
                        final_status = "CONFLICT"
                    elif title_status == "UNPROCESSED":
                        final_status = "UNPROCESSED"

                    if final_status != "PROCESSED":
                        has_manual_work = True

                    # Połączenie logów z obu funkcji
                    full_log = (
                        f"Kategoryzacja Tytułu: {title_log} | Przypisanie Lokalu: {lokal_log}"
                    )

                    FinancialTransaction.objects.update_or_create(
                        transaction_id=transaction_id,
                        defaults={
                            "posting_date": parsed_date,
                            "description": description,
                            "amount": amount,
                            "contractor": contractor,
                            "title": title,
                            "lokal": suggested_lokal,
                            "status": final_status,
                            # 'processing_log': full_log # Pole pominięte - brak w bazie danych
                        },
                    )
                    processed_count += 1

                except (ValueError, InvalidOperation, IndexError) as e:
                    skipped_rows.append((row_num, str(e)))
                    continue
            else:
                skipped_rows.append((row_num, "Nieprawidłowa liczba kolumn"))

    return {
        'processed_count': processed_count,
        'skipped_rows': skipped_rows,
        'has_manual_work': has_manual_work,
        'encoding_warning': encoding_warning,
    }
