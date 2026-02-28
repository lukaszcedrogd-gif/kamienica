from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

from ..models import Agreement, Lokal, Meter
from ..forms import LokalForm


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
def create_lokal(request):
    """
    Tworzy nowy lokal i obsługuje przypisywanie do niego liczników.
    """
    if request.method == 'POST':
        form = LokalForm(request.POST)
        if form.is_valid():
            lokal = form.save()

            meter_ids = request.POST.getlist('meters')
            if meter_ids:
                meters_to_assign = Meter.objects.filter(id__in=meter_ids)
                for meter in meters_to_assign:
                    meter.lokal = lokal
                    meter.save()

            messages.success(request, f'Lokal {lokal.unit_number} został utworzony.')
            return redirect('lokal_list')
    else:
        form = LokalForm()

    unassigned_meters = Meter.objects.filter(lokal__isnull=True, status='aktywny')

    context = {
        'form': form,
        'title': 'Dodaj nowy lokal',
        'unassigned_meters': unassigned_meters,
        'assigned_meters': [],
    }
    return render(request, 'core/lokal_form.html', context)

@login_required
def edit_lokal(request, pk):
    """
    Edytuje istniejący lokal, w tym zarządza przypisaniem i odpinaniem liczników.
    """
    lokal = get_object_or_404(Lokal, pk=pk)

    if request.method == 'POST':
        form = LokalForm(request.POST, instance=lokal)
        if form.is_valid():
            lokal = form.save()

            meter_ids = request.POST.getlist('meters')

            meters_to_detach = Meter.objects.filter(lokal=lokal).exclude(id__in=meter_ids)
            for meter in meters_to_detach:
                meter.lokal = None
                meter.save()

            if meter_ids:
                meters_to_assign = Meter.objects.filter(id__in=meter_ids)
                for meter in meters_to_assign:
                    meter.lokal = lokal
                    meter.save()

            messages.success(request, f'Lokal {lokal.unit_number} został zaktualizowany.')
            return redirect('lokal_list')
    else:
        form = LokalForm(instance=lokal)

    assigned_meters = Meter.objects.filter(lokal=lokal)
    unassigned_meters = Meter.objects.filter(lokal__isnull=True, status='aktywny')

    context = {
        'form': form,
        'title': f'Edycja lokalu {lokal.unit_number}',
        'assigned_meters': assigned_meters,
        'unassigned_meters': unassigned_meters,
    }
    return render(request, 'core/lokal_form.html', context)

@login_required
def delete_lokal(request, pk):
    """
    Dezaktywuje lokal (soft delete).
    """
    obj = get_object_or_404(Lokal, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('lokal_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'lokal', 'cancel_url': 'lokal_list'})
