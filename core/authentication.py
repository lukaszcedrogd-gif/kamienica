from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User as AuthUser
from core.models import User as TenantProfile, Agreement

class CustomAuthBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None):
        """
        Authenticates a user based on email.
        If the user exists, it first tries to authenticate with the provided password.
        If that fails, it checks against the default password (unit_number of the lokal).
        If the default password is correct, it updates the user's password and logs them in.
        """
        try:
            auth_user = AuthUser.objects.get(email=username)
            # First, try to authenticate with the existing password
            if auth_user.check_password(password):
                return auth_user
            else:
                # If the password check fails, try the default password
                agreement = Agreement.objects.filter(user__email=username, is_active=True).first()
                if agreement and agreement.lokal and password == agreement.lokal.unit_number:
                    auth_user.set_password(password)
                    auth_user.save()
                    return auth_user
        except AuthUser.DoesNotExist:
            # If the user does not exist, this is the first login.
            # The username is the email address.
            email = username
            try:
                # Check if there is an active agreement for this email
                agreement = Agreement.objects.filter(user__email=email, is_active=True).first()
                if agreement and agreement.lokal and password == agreement.lokal.unit_number:
                    # Create a new user with the default password
                    auth_user = AuthUser.objects.create_user(
                        username=email,  # Use email as the username
                        email=email,
                        password=password
                    )
                    return auth_user
            except Agreement.DoesNotExist:
                return None
        return None

    def get_user(self, user_id):
        """
        Standard method to get a user instance from an ID.
        """
        try:
            return AuthUser.objects.get(pk=user_id)
        except AuthUser.DoesNotExist:
            return None

