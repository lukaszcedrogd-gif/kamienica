# twoja_aplikacja/validators.py

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_pesel(value):
    """
    Podstawowa walidacja długości i sumy kontrolnej numeru PESEL.
    """
    if len(value) != 11:
        raise ValidationError(
            _('%(value)s ma niepoprawną długość (powinien mieć 11 cyfr)'),
            params={'value': value},
            code='invalid_length'
        )

    # Sprawdzenie, czy składa się tylko z cyfr
    if not value.isdigit():
        raise ValidationError(
            _('Numer PESEL może zawierać tylko cyfry.'),
            code='not_digits'
        )

    # Wagi dla sumy kontrolnej
    weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    checksum = 0
    
    # Obliczanie sumy kontrolnej (dla uproszczenia, nie jest to pełna weryfikacja daty urodzenia)
    for i in range(10):
        checksum += weights[i] * int(value[i])
        
    last_digit = int(value[10])
    
    if (10 - (checksum % 10)) % 10 != last_digit:
        raise ValidationError(
            _('%(value)s ma niepoprawną sumę kontrolną.'),
            params={'value': value},
            code='invalid_checksum'
        )

class CustomPasswordValidator:
    """
    Validator for custom password policy:
    - Minimum 3 characters long.
    - Must contain at least one special character.
    """
    def validate(self, password, user=None):
        if len(password) < 3:
            raise ValidationError(
                _("Hasło musi mieć co najmniej 3 znaki."),
                code='password_too_short',
            )
        
        if password.isalnum():
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jeden znak specjalny (np. !, @, #)."),
                code='password_no_special_char',
            )

    def get_help_text(self):
        return _(
            "Hasło musi mieć co najmniej 3 znaki i zawierać co najmniej jeden znak specjalny."
        )