from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User as AuthUser
from core.models import User as TenantProfile, Agreement

class CustomAuthBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None):
        """
        Authenticates a user based on email.

        Two cases:
        1. Existing account: only the stored password is accepted. There is no
           fallback to the default password — this prevents anyone who knows the
           unit number from resetting a tenant's custom password.
        2. First login (no AuthUser account yet): the default password (the
           unit_number of the tenant's lokal) is accepted and the account is
           created on the fly.
        """
        try:
            auth_user = AuthUser.objects.get(email=username)
            if auth_user.check_password(password):
                return auth_user
            # Wrong password for an existing account — do not fall back to the
            # default password, as that would allow anyone knowing the unit
            # number to take over the account.
            return None
        except AuthUser.DoesNotExist:
            # First login: accept the default password (tenant's last name) and
            # create the account.  Comparison is case-insensitive so capitalisation
            # mistakes don't block the first login.
            agreement = Agreement.objects.filter(user__email=username, is_active=True).first()
            if (
                agreement
                and agreement.user
                and agreement.user.lastname
                and password.strip().lower() == agreement.user.lastname.strip().lower()
            ):
                auth_user = AuthUser.objects.create_user(
                    username=username,
                    email=username,
                    password=password,
                )
                # Signal to the login view that a forced password change is needed.
                request._must_change_password = True
                return auth_user
        return None

    def get_user(self, user_id):
        """
        Standard method to get a user instance from an ID.
        """
        try:
            return AuthUser.objects.get(pk=user_id)
        except AuthUser.DoesNotExist:
            return None

