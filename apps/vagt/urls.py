"""URL configuration for the vagt board."""

from django.urls import path

from . import views

app_name = "vagt"

urlpatterns = [
    path("", views.board_view, name="board"),
    path("board/rows/", views.board_rows, name="board_rows"),
    path("log/", views.log_view, name="log"),
    path("controller/<int:pk>/status/", views.set_status, name="set_status"),
    # Controller CRUD
    path("controllers/", views.controller_list, name="controllers"),
    path("controllers/add/", views.controller_add, name="controller_add"),
    path("controllers/<int:pk>/edit/", views.controller_edit, name="controller_edit"),
    path("controllers/<int:pk>/delete/", views.controller_delete, name="controller_delete"),
    # User profile
    path("profile/", views.profile_view, name="profile"),
    # Documentation
    path("docs/", views.docs_index, name="docs"),
    path("docs/<slug:slug>/", views.docs_page, name="docs_page"),
]
