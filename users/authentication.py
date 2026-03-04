from django.conf import settings
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed


class CookieOrHeaderJWTAuthentication(JWTAuthentication):
    """
    Authenticate with Authorization header first, then fall back to httpOnly cookie.
    For cookie-authenticated unsafe requests, enforce CSRF validation.
    """

    def _enforce_csrf(self, request):
        check = CSRFCheck(lambda req: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise PermissionDenied(f'CSRF Failed: {reason}')

    def authenticate(self, request):
        header = self.get_header(request)

        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                try:
                    validated_token = self.get_validated_token(raw_token)
                    return self.get_user(validated_token), validated_token
                except (InvalidToken, AuthenticationFailed):
                    # Fall back to cookie auth when header token is stale/invalid.
                    pass

        cookie_name = getattr(settings, 'JWT_ACCESS_COOKIE_NAME', 'access_token')
        cookie_token = request.COOKIES.get(cookie_name)
        if not cookie_token:
            return None

        if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            self._enforce_csrf(request)

        validated_token = self.get_validated_token(cookie_token)
        return self.get_user(validated_token), validated_token
