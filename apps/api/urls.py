"""URL configuration for the REST API."""

from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("health/", views.health_check, name="health"),
    path("v1/controllers/", views.ControllerListView.as_view(), name="controllers"),
    path("v1/logs/", views.StatusLogListView.as_view(), name="logs"),
]
