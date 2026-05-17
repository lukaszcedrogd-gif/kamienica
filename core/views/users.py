from django.contrib import messages
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User as AuthUser
from django.shortcuts import render, redirect, get_object_or_404

from ..decorators import require_admin
from ..models import User
from ..forms import UserForm


def _sync_auth_user(tenant: User) -> None:
    """Synchronizuje is_superuser/is_staff w AuthUser jeśli konto już istnieje."""
    try:
        auth_user = AuthUser.objects.get(email=tenant.email)
        if auth_user.is_superuser != tenant.is_admin or auth_user.is_staff != tenant.is_admin:
            auth_user.is_superuser = tenant.is_admin
            auth_user.is_staff = tenant.is_admin
            auth_user.save(update_fields=['is_superuser', 'is_staff'])
    except AuthUser.DoesNotExist:
        pass


def _ensure_auth_user_for_admin(tenant: User) -> bool:
    """
    Dla użytkownika z is_admin=True tworzy AuthUser z nieużywalnym hasłem,
    jeśli konto logowania jeszcze nie istnieje.
    Zwraca True jeśli konto zostało właśnie utworzone.
    """
    if not tenant.is_admin:
        return False
    _, created = AuthUser.objects.get_or_create(
        email=tenant.email,
        defaults={
            'username': tenant.email,
            'is_superuser': True,
            'is_staff': True,
        },
    )
    if created:
        AuthUser.objects.filter(email=tenant.email).update(password='!')  # nieużywalne hasło
    return created


@require_admin
def user_list(request):
    users = User.objects.all()
    auth_emails = set(
        AuthUser.objects.filter(email__in=[u.email for u in users])
        .values_list('email', flat=True)
    )
    return render(request, 'users/user_list.html', {
        'users': users,
        'auth_emails': auth_emails,
        'is_dashboard': True,
    })


@require_admin
def create_user(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            saved = form.save()
            _ensure_auth_user_for_admin(saved)
            return redirect('user_list')
    else:
        form = UserForm()
    return render(request, 'core/user_form.html', {'form': form, 'title': 'Dodaj nowego użytkownika'})


@require_admin
def edit_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            saved = form.save()
            _ensure_auth_user_for_admin(saved)
            _sync_auth_user(saved)
            return redirect('user_list')
    else:
        form = UserForm(instance=user)
    return render(request, 'core/user_form.html', {'form': form, 'title': f'Edytuj użytkownika: {user}'})


@require_admin
def delete_user(request, pk):
    obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        return redirect('user_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'type': 'użytkownika', 'cancel_url': 'user_list'})


@require_admin
def send_setup_email(request, pk):
    """
    Wysyła użytkownikowi link do ustawienia hasła (password reset).
    Jeśli AuthUser nie istnieje (admin bez umowy), tworzy go najpierw.
    """
    tenant = get_object_or_404(User, pk=pk)

    _ensure_auth_user_for_admin(tenant)

    if not AuthUser.objects.filter(email=tenant.email).exists():
        messages.error(
            request,
            f"Użytkownik {tenant.email} nie posiada jeszcze konta logowania. "
            "Konto tworzone jest automatycznie przy pierwszym logowaniu (dla lokatorów z umową) "
            "lub po zaznaczeniu opcji Administrator systemu."
        )
        return redirect('user_list')

    form = PasswordResetForm({'email': tenant.email})
    if form.is_valid():
        form.save(
            request=request,
            use_https=request.is_secure(),
            from_email=None,
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
        )
        messages.success(
            request,
            f"Link do ustawienia hasła został wysłany na adres {tenant.email}."
        )
    else:
        messages.error(request, "Nie udało się wysłać wiadomości — sprawdź konfigurację email w .env.")

    return redirect('user_list')
