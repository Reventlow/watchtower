"""
URL configuration for Watchtower (Vagt) project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from apps.accounts.views import LoginView

# allauth is mounted for Microsoft sign-in only. Its own account pages
# (login, sign-up, password reset, e-mail confirmation, ...) are not part of
# Vagt: left reachable they would be a second, unadvertised way in, so they
# all lead to Vagt's login page. With SSO off, the Microsoft routes go there
# too instead of erroring.
_UNUSED_ALLAUTH = r"login|signup|password|confirm-email|inactive|email|reauthenticate|account|logout"
if not settings.SSO_ENABLED:
    _UNUSED_ALLAUTH += r"|microsoft|3rdparty|social"
_to_login = RedirectView.as_view(pattern_name="login", query_string=True)

# Django's own password reset and change pages (from django.contrib.auth.urls)
# are not used: the profile page changes a password. A reset by e-mail would
# also let whoever reads a break-glass account's mailbox set its password and
# sign in without MFA.
_UNUSED_AUTH = r"password_reset|password_change|reset"

urlpatterns = [
    re_path(rf"^allauth/(?:{_UNUSED_ALLAUTH})(?:/|$)", _to_login),
    re_path(rf"^(?:{_UNUSED_AUTH})(?:/|$)", _to_login),
    # Django admin
    path("admin/", admin.site.urls),
    # Authentication: Vagt's login page (password and/or Microsoft), the rest
    # of Django's auth views, and allauth for the Microsoft callback.
    path("login/", LoginView.as_view(), name="login"),
    path("", include("django.contrib.auth.urls")),
    path("allauth/", include("allauth.urls")),
    # Main application
    path("", include("apps.vagt.urls", namespace="vagt")),
    # REST API
    path("api/", include("apps.api.urls", namespace="api")),
]

# Debug toolbar URLs (only in development and if installed)
if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns

    # Serve media files in development
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
