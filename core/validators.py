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
    Polityka haseł:
    - Minimum 8 znaków.
    - Co najmniej jedna wielka litera.
    - Co najmniej jedna cyfra.
    - Co najmniej jeden znak specjalny.
    """
    MIN_LENGTH = 8

    def validate(self, password, user=None):
        if len(password) < self.MIN_LENGTH:
            raise ValidationError(
                _("Hasło musi mieć co najmniej %(min_length)d znaków."),
                code='password_too_short',
                params={'min_length': self.MIN_LENGTH},
            )
        if not any(c.isupper() for c in password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jedną wielką literę."),
                code='password_no_uppercase',
            )
        if not any(c.isdigit() for c in password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jedną cyfrę."),
                code='password_no_digit',
            )
        if password.isalnum():
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jeden znak specjalny (np. !, @, #)."),
                code='password_no_special_char',
            )

    def get_help_text(self):
        return _(
            "Hasło musi mieć co najmniej %(min_length)d znaków oraz zawierać: "
            "wielką literę, cyfrę i znak specjalny."
        ) % {'min_length': self.MIN_LENGTH}