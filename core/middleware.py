from django.shortcuts import redirect


class ForcePasswordChangeMiddleware:
    """
    Przekierowuje zalogowanego użytkownika na stronę zmiany hasła,
    jeśli w sesji ustawiona jest flaga 'must_change_password'.
    Flaga jest ustawiana przy pierwszym logowaniu (domyślne hasło = nazwisko).
    """

    # Ścieżki dostępne nawet gdy wymagana jest zmiana hasła.
    EXEMPT_PREFIXES = (
        '/password_change/',
        '/logout/',
        '/admin/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.session.get('must_change_password')
            and not any(request.path.startswith(p) for p in self.EXEMPT_PREFIXES)
        ):
            return redirect('password_change')
        return self.get_response(request)
