from django.shortcuts import render, redirect, get_object_or_404
from .models import User, Agreement, Lokal, Meter, MeterReading
from .forms import UserForm, AgreementForm, LokalForm, MeterReadingForm

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
    obj = get_ot_object_or_404(Agreement, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('agreement_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'umowę', 'cancel_url': 'agreement_list'})