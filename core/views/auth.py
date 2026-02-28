from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect

from ..models import Agreement


def user_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            if getattr(request, '_must_change_password', False):
                request.session['must_change_password'] = True
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
            update_session_auth_hash(request, user)
            request.session.pop('must_change_password', None)
            messages.success(request, 'Hasło zostało pomyślnie zmienione!')
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


@login_required
def home(request):
    """
    Widok dyspozytora - przekierowuje użytkowników do odpowiedniego panelu.
    """
    if request.user.is_superuser:
        from .users import user_list
        return user_list(request)
    else:
        try:
            agreement = Agreement.objects.get(user__email=request.user.email, is_active=True)
            return redirect('annual_agreement_report', pk=agreement.pk)
        except Agreement.DoesNotExist:
            messages.error(request, "Nie znaleziono aktywnej umowy dla Twojego konta.")
            return redirect('login')
