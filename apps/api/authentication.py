"""
Custom authentication for the REST API using PersonalAccessToken.

Tokens are passed via the Authorization header:
    Authorization: Bearer <token>
"""

from rest_framework import authentication, exceptions

from apps.vagt.models import PersonalAccessToken


class PersonalAccessTokenAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication using PersonalAccessToken model.

    Tokens are SHA-256 hashed in the database, so we hash the incoming token
    and compare. The token must be active (not revoked, not expired).
    """

    keyword = "Bearer"

    def authenticate(self, request):
        """
        Authenticate the request and return a tuple of (user, token) or None.
        """
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header:
            return None

        # Parse the Authorization header
        parts = auth_header.split()

        if len(parts) != 2:
            return None

        keyword, raw_token = parts

        if keyword.lower() != self.keyword.lower():
            return None

        # Authenticate the token
        token = PersonalAccessToken.authenticate_raw_token(raw_token)

        if token is None:
            raise exceptions.AuthenticationFailed("Invalid or expired token")

        return (token.user, token)

    def authenticate_header(self, request):
        """
        Return the value for the WWW-Authenticate header.
        """
        return self.keyword
