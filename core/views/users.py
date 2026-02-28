from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

from ..models import User
from ..forms import UserForm


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
def create_user(request):
    """
    Tworzy nowego użytkownika na podstawie danych z formularza.
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
def edit_user(request, pk):
    """
    Edytuje istniejącego użytkownika.
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
def delete_user(request, pk):
    """
    Dezaktywuje użytkownika (soft delete).
    """
    obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('user_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'użytkownika', 'cancel_url': 'user_list'})
