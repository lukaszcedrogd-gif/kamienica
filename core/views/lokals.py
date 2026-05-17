from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

from ..decorators import require_admin
from ..models import Agreement, Lokal, Meter
from ..forms import LokalForm


@login_required
def lokal_list(request):
    """
    Superużytkownik widzi wszystkie lokale. Lokator widzi tylko swój.
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
    return render(request, 'core/lokal_detail.html', {'lokal': lokal, 'meters': meters})


@require_admin
def create_lokal(request):
    if request.method == 'POST':
        form = LokalForm(request.POST)
        if form.is_valid():
            lokal = form.save()

            meter_ids = request.POST.getlist('meters')
            if meter_ids:
                for meter in Meter.objects.filter(id__in=meter_ids):
                    meter.lokal = lokal
                    meter.save()

            messages.success(request, f'Lokal {lokal.unit_number} został utworzony.')
            return redirect('lokal_list')
    else:
        form = LokalForm()

    return render(request, 'core/lokal_form.html', {
        'form': form,
        'title': 'Dodaj nowy lokal',
        'unassigned_meters': Meter.objects.filter(lokal__isnull=True, status='aktywny'),
        'assigned_meters': [],
    })


@require_admin
def edit_lokal(request, pk):
    lokal = get_object_or_404(Lokal, pk=pk)

    if request.method == 'POST':
        form = LokalForm(request.POST, instance=lokal)
        if form.is_valid():
            lokal = form.save()

            meter_ids = request.POST.getlist('meters')
            for meter in Meter.objects.filter(lokal=lokal).exclude(id__in=meter_ids):
                meter.lokal = None
                meter.save()
            for meter in Meter.objects.filter(id__in=meter_ids):
                meter.lokal = lokal
                meter.save()

            messages.success(request, f'Lokal {lokal.unit_number} został zaktualizowany.')
            return redirect('lokal_list')
    else:
        form = LokalForm(instance=lokal)

    return render(request, 'core/lokal_form.html', {
        'form': form,
        'title': f'Edycja lokalu {lokal.unit_number}',
        'assigned_meters': Meter.objects.filter(lokal=lokal),
        'unassigned_meters': Meter.objects.filter(lokal__isnull=True, status='aktywny'),
    })


@require_admin
def delete_lokal(request, pk):
    obj = get_object_or_404(Lokal, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('lokal_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'lokal', 'cancel_url': 'lokal_list'})
