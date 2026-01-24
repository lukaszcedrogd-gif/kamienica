# core/services/reporting.py
from collections import defaultdict
from datetime import date
from decimal import Decimal
from dateutil.relativedelta import relativedelta
import datetime

from ..models import (
    Agreement,
    FinancialTransaction,
    FixedCost,
    Lokal,
    Meter,
    WaterCostOverride,
)


def get_bimonthly_report_context(lokal, selected_year):
    agreement = Agreement.objects.filter(lokal=lokal, is_active=True).first()

    # --- Pre-calculate all consumptions for the lokal ---
    period_data_map = defaultdict(
        lambda: {
            "consumption_by_meter": defaultdict(
                lambda: {
                    "consumption": Decimal("0.00"),
                    "start_reading": None,
                    "end_reading": None,
                }
            ),
            "total_consumption": Decimal("0.00"),
        }
    )

    water_meters = Meter.objects.filter(
        lokal=lokal, type__in=["hot_water", "cold_water"], status="aktywny"
    )

    for meter in water_meters:
        readings = list(meter.readings.all().order_by("reading_date"))
        for i in range(1, len(readings)):
            start_reading, end_reading = readings[i - 1], readings[i]
            consumption = end_reading.value - start_reading.value

            # Correct period assignment logic
            end_date = end_reading.reading_date
            period_start_month = ((end_date.month - 1) // 2) * 2 + 1
            # Handle edge case where reading is early in the month, belongs to previous period
            if end_date.day < 15 and end_date.month % 2 != 0:
                # e.g., reading on March 5th should likely close Jan-Feb period
                effective_date = end_date - relativedelta(months=2)
                period_start_month = ((effective_date.month - 1) // 2) * 2 + 1
                period_start_date = date(effective_date.year, period_start_month, 1)
            else:
                period_start_date = date(end_date.year, period_start_month, 1)

            meter_display_name = f"{meter.get_type_display()} ({meter.serial_number})"

            data = period_data_map[period_start_date]
            data["total_consumption"] += consumption
            data["consumption_by_meter"][meter_display_name][
                "consumption"
            ] += consumption
            data["consumption_by_meter"][meter_display_name][
                "start_reading"
            ] = start_reading
            data["consumption_by_meter"][meter_display_name][
                "end_reading"
            ] = end_reading

    # --- Pre-calculate consumptions for ALL lokals (for unit price calculation) ---
    all_lokals_consumptions = defaultdict(lambda: defaultdict(Decimal))
    all_active_lokals = Lokal.objects.filter(is_active=True).exclude(
        unit_number__iexact="kamienica"
    )
    all_water_meters = Meter.objects.filter(
        lokal__in=all_active_lokals,
        type__in=["hot_water", "cold_water"],
        status="aktywny",
    ).select_related("lokal").prefetch_related("readings")

    for meter in all_water_meters:
        readings = list(meter.readings.all().order_by("reading_date"))
        for i in range(1, len(readings)):
            start_reading, end_reading = readings[i - 1], readings[i]
            consumption = end_reading.value - start_reading.value

            end_date = end_reading.reading_date
            period_start_month = ((end_date.month - 1) // 2) * 2 + 1
            if end_date.day < 15 and end_date.month % 2 != 0:
                effective_date = end_date - relativedelta(months=2)
                period_start_month = ((effective_date.month - 1) // 2) * 2 + 1
                period_key = date(effective_date.year, period_start_month, 1)
            else:
                period_key = date(end_date.year, period_start_month, 1)

            all_lokals_consumptions[period_key][meter.lokal_id] += consumption

    # --- Assemble final report data for the selected year ---
    report_data = []
    all_lokals_total_consumption_for_context = None

    # Iterate only over periods that have data and are in the selected year
    sorted_periods = sorted(
        [p for p in period_data_map.keys() if p.year == selected_year], reverse=True
    )

    for period_start in sorted_periods:
        period_consumptions = period_data_map[period_start]
        period_end = period_start + relativedelta(months=2, days=-1)

        period_dict = {
            "period_start_date": period_start,
            "period_end_date": period_end,
            "consumption_by_meter": dict(period_consumptions["consumption_by_meter"]),
            "total_consumption": period_consumptions["total_consumption"],
            "water_cost_details": {},
            "waste_cost": Decimal("0.00"),
        }

        # --- Calculate costs for the period ---
        # 1. Water Cost
        bill_amount, source = None, "Brak danych"

        water_cost_override = WaterCostOverride.objects.filter(
            period_start_date=period_start
        ).first()
        if water_cost_override and water_cost_override.overridden_bill_amount is not None:
            bill_amount = water_cost_override.overridden_bill_amount
            source = "Ręczne ustawienie (admin)"

        # Calculate total consumption for ALL lokals for this period
        total_building_consumption = sum(all_lokals_consumptions[period_start].values())
        consumption_source = "Suma liczników"

        unit_price = Decimal("0.00")
        if bill_amount and total_building_consumption > 0:
            unit_price = bill_amount / total_building_consumption

        lokal_water_cost = period_dict["total_consumption"] * unit_price

        period_dict["water_cost_details"] = {
            "bill_amount": bill_amount,
            "source": source,
            "total_building_consumption": total_building_consumption,
            "consumption_source": consumption_source,
            "unit_price": unit_price,
            "lokal_water_cost": lokal_water_cost.quantize(Decimal("0.01")),
            "override_obj": water_cost_override,
        }

        # 2. Waste Cost (if agreement exists)
        if agreement:
            waste_rule = (
                FixedCost.objects.filter(
                    name__icontains="śmieci",
                    calculation_method="per_person",
                    effective_date__lte=period_start,
                )
                .order_by("-effective_date")
                .first()
            )
            if waste_rule:
                period_dict["waste_cost"] = (
                    waste_rule.amount * agreement.number_of_occupants * 2
                )

        report_data.append(period_dict)

        # Set the total consumption for all lokals for the latest period (for context/test)
        if all_lokals_total_consumption_for_context is None:
            all_lokals_total_consumption_for_context = total_building_consumption

    return {
        "lokal": lokal,
        "agreement": agreement,
        "report_data": report_data,
        "selected_year": selected_year,
        "all_lokals_total_consumption": all_lokals_total_consumption_for_context,
    }


def get_annual_report_context(agreement, selected_year, _cache=None):
    if _cache is None:
        _cache = {}
    if selected_year in _cache:
        return _cache[selected_year]

    # Base case for recursion: if the selected year is before the agreement starts, there's no data.
    if agreement.start_date and selected_year < agreement.start_date.year:
        return {
            "final_balance": Decimal("0.00"),
            "rent_schedule": [],
            "total_rent": Decimal("0.00"),
            "total_payments": Decimal("0.00"),
            "cumulative_payments": [],
            "bimonthly_data": [],
            "total_waste_cost_year": Decimal("0.00"),
            "total_water_cost_year": Decimal("0.00"),
            "total_water_consumption_year": Decimal("0.00"),
            "total_costs": Decimal("0.00"),
            "agreement": agreement,
            "title": "",
            "selected_year": selected_year,
            "available_years": [],
        }

    lokal = agreement.lokal
    current_date = date.today()
    current_year = current_date.year
    if agreement.start_date:
        available_years = list(range(current_year, agreement.start_date.year - 1, -1))
    else:
        available_years = list(range(current_year, current_year - 5, -1))

    year_start = date(selected_year, 1, 1)
    year_end = date(selected_year, 12, 31)

    # --- CARRY-OVER BALANCE ---
    previous_year_balance = Decimal("0.00")
    if agreement.start_date and selected_year > agreement.start_date.year:
        prev_year_context = get_annual_report_context(
            agreement, selected_year - 1, _cache
        )
        previous_year_balance = prev_year_context.get("final_balance", Decimal("0.00"))

    # --- RENT SCHEDULE CALCULATION ---
    rent_schedule = []
    total_rent = Decimal("0.00")
    month_names = [
        "Styczeń",
        "Luty",
        "Marzec",
        "Kwiecień",
        "Maj",
        "Czerwiec",
        "Lipiec",
        "Sierpień",
        "Wrzesień",
        "Październik",
        "Listopad",
        "Grudzień",
    ]

    limit_month = 12
    if selected_year == current_year:
        limit_month = current_date.month

    for i, month_name in enumerate(month_names[:limit_month], 1):
        current_month = date(selected_year, i, 1)
        month_end = current_month + relativedelta(months=1, days=-1)
        monthly_rent = Decimal("0.00")

        agreement_starts_before_month_end = agreement.start_date <= month_end
        agreement_ends_after_month_start = (
            agreement.end_date is None or agreement.end_date >= current_month
        )

        if agreement_starts_before_month_end and agreement_ends_after_month_start:
            date_in_month = datetime.datetime(selected_year, i, 15)
            historical_record = (
                agreement.history.filter(history_date__lte=date_in_month)
                .order_by("-history_date")
                .first()
            )

            if historical_record:
                monthly_rent = historical_record.rent_amount
            elif agreement.start_date <= date_in_month.date():
                earliest_record = agreement.history.order_by("history_date").first()
                if earliest_record:
                    monthly_rent = earliest_record.rent_amount
                else:
                    monthly_rent = agreement.rent_amount

        rent_schedule.append({"month_name": month_name, "rent": monthly_rent})
        total_rent += monthly_rent

    # --- PAYMENTS ---
    payments = FinancialTransaction.objects.filter(
        lokal=lokal, amount__gt=0, posting_date__range=(year_start, year_end)
    ).order_by("posting_date")

    cumulative_payments = []
    running_total = previous_year_balance  # Start with the balance from the previous year

    if previous_year_balance != Decimal("0.00"):
        cumulative_payments.append(
            {
                "date": year_start,
                "amount": previous_year_balance,
                "running_total": running_total,
                "description": f"Bilans z roku {selected_year - 1}",
            }
        )

    for payment in payments:
        running_total += payment.amount
        cumulative_payments.append(
            {
                "date": payment.posting_date,
                "amount": payment.amount,
                "running_total": running_total,
                "description": payment.title,
            }
        )

    total_payments = running_total

    # --- BIMONTHLY CALCULATIONS (Waste & Water) ---
    all_lokals_consumptions = defaultdict(lambda: defaultdict(Decimal))
    all_active_lokals = Lokal.objects.filter(is_active=True).exclude(
        unit_number__iexact="kamienica"
    )
    all_water_meters = Meter.objects.filter(
        lokal__in=all_active_lokals,
        type__in=["hot_water", "cold_water"],
        status="aktywny",
    ).select_related("lokal").prefetch_related("readings")

    for meter in all_water_meters:
        readings = list(meter.readings.all().order_by("reading_date"))
        for i in range(1, len(readings)):
            start_reading, end_reading = readings[i - 1], readings[i]
            end_date = end_reading.reading_date
            if end_date.year == selected_year:
                period_start_month = ((end_date.month - 1) // 2) * 2 + 1
                if end_date.day < 15 and end_date.month % 2 != 0:
                    effective_date = end_date - relativedelta(months=2)
                    period_start_month = ((effective_date.month - 1) // 2) * 2 + 1
                    period_key = date(effective_date.year, period_start_month, 1)
                else:
                    period_key = date(end_date.year, period_start_month, 1)

                if period_key.year == selected_year:
                    consumption = end_reading.value - start_reading.value
                    all_lokals_consumptions[period_key][meter.lokal_id] += consumption

    bimonthly_data = []
    month_start_num = 1
    for name in [
        "styczeń-luty",
        "marzec-kwiecień",
        "maj-czerwiec",
        "lipiec-sierpień",
        "wrzesień-październik",
        "listopad-grudzień",
    ]:
        period_start_date = date(selected_year, month_start_num, 1)

        if selected_year == current_year and period_start_date > current_date:
            break

        bimonthly_data.append(
            {
                "name": f"{name} {selected_year}",
                "period_start": period_start_date,
                "period_end": period_start_date + relativedelta(months=2, days=-1),
                "waste_cost": Decimal("0.00"),
                "water_consumption": Decimal("0.00"),
                "water_cost": Decimal("0.00"),
                "meter_details": [],
            }
        )
        month_start_num += 2

    lokal_meters = Meter.objects.filter(
        lokal=lokal, type__in=["hot_water", "cold_water"], status="aktywny"
    )
    for meter in lokal_meters:
        all_readings_for_meter = list(
            meter.readings.filter(
                reading_date__lt=year_end + relativedelta(months=2)
            ).order_by("reading_date")
        )
        last_reading_before_year = (
            meter.readings.filter(reading_date__lt=year_start)
            .order_by("-reading_date")
            .first()
        )
        if (
            last_reading_before_year
            and last_reading_before_year not in all_readings_for_meter
        ):
            all_readings_for_meter.insert(0, last_reading_before_year)

        unique_readings = sorted(
            list({r.id: r for r in all_readings_for_meter}.values()),
            key=lambda r: r.reading_date,
        )

        for i in range(1, len(unique_readings)):
            start_r, end_r = unique_readings[i - 1], unique_readings[i]
            end_date = end_r.reading_date
            if not (
                year_start <= end_date < year_end + relativedelta(months=2)
            ):
                continue

            period_start_month = ((end_date.month - 1) // 2) * 2 + 1
            if end_date.day < 15 and end_date.month % 2 != 0:
                effective_date = end_date - relativedelta(months=2)
                period_start_month = ((effective_date.month - 1) // 2) * 2 + 1
                period_key = date(effective_date.year, period_start_month, 1)
            else:
                period_key = date(end_date.year, period_start_month, 1)

            if period_key.year != selected_year:
                continue

            for period in bimonthly_data:
                if period["period_start"] == period_key:
                    consumption = end_r.value - start_r.value
                    period["water_consumption"] += consumption
                    period["meter_details"].append(
                        {
                            "meter": meter,
                            "start_reading": start_r,
                            "end_reading": end_r,
                            "consumption": consumption,
                        }
                    )
                    break

    (
        total_water_cost_year,
        total_waste_cost_year,
        total_water_consumption_year,
    ) = (Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))
    for period in bimonthly_data:
        waste_rule = (
            FixedCost.objects.filter(
                name__icontains="śmieci",
                calculation_method="per_person",
                effective_date__lte=period["period_start"],
            )
            .order_by("-effective_date")
            .first()
        )
        if waste_rule:
            period["waste_cost"] = waste_rule.amount * agreement.number_of_occupants * 2

        total_building_consumption = sum(
            all_lokals_consumptions[period["period_start"]].values()
        )
        water_cost_override = WaterCostOverride.objects.filter(
            period_start_date=period["period_start"]
        ).first()
        unit_price = Decimal("0.00")
        if (
            water_cost_override
            and water_cost_override.overridden_bill_amount
            and total_building_consumption > 0
        ):
            unit_price = (
                water_cost_override.overridden_bill_amount / total_building_consumption
            )

        period["water_cost"] = period["water_consumption"] * unit_price
        total_waste_cost_year += period["waste_cost"]
        total_water_cost_year += period["water_cost"]
        total_water_consumption_year += period["water_consumption"]

    total_costs = total_rent + total_waste_cost_year + total_water_cost_year
    final_balance = total_payments - total_costs

    context = {
        "agreement": agreement,
        "title": f"Raport roczny dla lokalu {lokal.unit_number} ({selected_year})",
        "selected_year": selected_year,
        "available_years": available_years,
        "rent_schedule": rent_schedule,
        "total_rent": total_rent,
        "total_payments": total_payments,
        "cumulative_payments": cumulative_payments,
        "bimonthly_data": bimonthly_data,
        "total_waste_cost_year": total_waste_cost_year,
        "total_water_cost_year": total_water_cost_year,
        "total_water_consumption_year": total_water_consumption_year,
        "total_costs": total_costs,
        "final_balance": final_balance,
    }
    _cache[selected_year] = context
    return context