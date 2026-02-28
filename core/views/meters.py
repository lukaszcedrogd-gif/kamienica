from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from ..models import Lokal, Meter, MeterReading
from ..forms import MeterReadingForm


@login_required
def meter_readings_view(request):
    """
    Wyświetla formularz do wprowadzania odczytów liczników dla wszystkich lokali
    i przetwarza dane z tego formularza.
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
                        reading_date=request.POST.get('date')
                    )
        return redirect('meter_readings')

    context = {'lokale': lokale}
    return render(request, 'core/meter_readings.html', context)


@login_required
def add_meter_reading(request, meter_id):
    """
    Dodaje nowy odczyt dla konkretnego licznika.
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


@login_required
def meter_consumption_report(request):
    """
    Generuje raport zużycia mediów na podstawie dwóch ostatnich odczytów
    dla każdego aktywnego licznika przypisanego do lokalu.
    """
    meters = Meter.objects.select_related('lokal').prefetch_related('readings').filter(status='aktywny', lokal__isnull=False)
    consumption_data = []

    for meter in meters:
        readings = meter.readings.all()[:2]

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
