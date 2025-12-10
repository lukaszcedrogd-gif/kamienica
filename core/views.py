from django.shortcuts import render, redirect
from .forms import UserForm, AgreementForm
from .models import User, Agreement

def create_user(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('user_list')
    else:
        form = UserForm()
    return render(request, 'core/user_form.html', {'form': form})

def user_list(request):
    users = User.objects.all()
    return render(request, 'users/user_list.html', {'users': users})

def create_agreement(request):
    if request.method == 'POST':
        form = AgreementForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('user_list')
    else:
        form = AgreementForm()
    return render(request, 'core/agreement_form.html', {'form': form})
