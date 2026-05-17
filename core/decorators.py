from functools import wraps

from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def require_admin(view_func):
    """Wymaga zalogowania i uprawnień superużytkownika (is_superuser=True)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if not request.user.is_superuser:
            return HttpResponseForbidden("Nie masz uprawnień do tej strony.")
        return view_func(request, *args, **kwargs)
    return _wrapped
