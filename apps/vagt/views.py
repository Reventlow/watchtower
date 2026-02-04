"""
Views for the vagt board - digital version of the physical magnetic board.
"""

from pathlib import Path

import markdown

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm

from .models import Controller, StatusLog


STATUSES = [
    ("FERIE", "Ferie"),
    ("SYG", "Syg"),
    ("MOEDT", "Mødt"),
    ("GAAET", "Gået"),
]


def _get_board_context():
    """Helper to get board context data."""
    controllers = Controller.objects.filter(is_active=True).prefetch_related("status_logs")

    controllers_with_logs = []
    for controller in controllers:
        last_log = controller.status_logs.select_related("changed_by").first()
        controllers_with_logs.append({
            "controller": controller,
            "last_log": last_log,
        })

    return {
        "controllers": controllers_with_logs,
        "statuses": STATUSES,
    }


@login_required
@require_GET
def board_view(request: HttpRequest) -> HttpResponse:
    """Main board view - shows all controllers with their status."""
    return render(request, "vagt/board.html", _get_board_context())


@login_required
@require_GET
def board_rows(request: HttpRequest) -> HttpResponse:
    """Partial view returning just the board rows for HTMX polling."""
    return render(request, "vagt/partials/_board_rows.html", _get_board_context())


@login_required
@require_POST
def set_status(request: HttpRequest, pk: int) -> HttpResponse:
    """HTMX endpoint to set a controller's status."""
    controller = get_object_or_404(Controller, pk=pk)
    new_status = request.POST.get("status")

    if new_status in [s[0] for s in STATUSES]:
        controller.set_status(new_status, by_user=request.user)

    last_log = controller.status_logs.select_related("changed_by").first()

    context = {
        "controller": controller,
        "last_log": last_log,
        "statuses": STATUSES,
    }

    return render(request, "vagt/partials/_controller_row.html", context)


@login_required
@require_GET
def log_view(request: HttpRequest) -> HttpResponse:
    """View the status change log."""
    logs = StatusLog.objects.select_related("controller", "changed_by").order_by("-changed_at")[:100]

    context = {
        "logs": logs,
        "statuses": dict(STATUSES),
    }

    return render(request, "vagt/log.html", context)


# =============================================================================
# Controller CRUD
# =============================================================================

@login_required
@require_GET
def controller_list(request: HttpRequest) -> HttpResponse:
    """List all controllers for management."""
    controllers = Controller.objects.all().order_by("callsign")
    return render(request, "vagt/controllers/list.html", {"controllers": controllers})


@login_required
@require_http_methods(["GET", "POST"])
def controller_add(request: HttpRequest) -> HttpResponse:
    """Add a new controller."""
    if request.method == "POST":
        callsign = request.POST.get("callsign", "").strip()
        name = request.POST.get("name", "").strip()
        note = request.POST.get("note", "").strip()

        errors = []
        if not callsign:
            errors.append("Callsign er påkrævet")
        if not name:
            errors.append("Navn er påkrævet")
        if callsign and Controller.objects.filter(callsign=callsign).exists():
            errors.append(f"Callsign '{callsign}' findes allerede")

        if not errors:
            Controller.objects.create(callsign=callsign, name=name, note=note)
            return redirect("vagt:controllers")

        return render(request, "vagt/controllers/form.html", {
            "errors": errors,
            "callsign": callsign,
            "name": name,
            "note": note,
        })

    return render(request, "vagt/controllers/form.html", {})


@login_required
@require_http_methods(["GET", "POST"])
def controller_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit a controller."""
    controller = get_object_or_404(Controller, pk=pk)

    if request.method == "POST":
        callsign = request.POST.get("callsign", "").strip()
        name = request.POST.get("name", "").strip()
        note = request.POST.get("note", "").strip()

        errors = []
        if not callsign:
            errors.append("Callsign er påkrævet")
        if not name:
            errors.append("Navn er påkrævet")
        if callsign and Controller.objects.filter(callsign=callsign).exclude(pk=pk).exists():
            errors.append(f"Callsign '{callsign}' findes allerede")

        if not errors:
            controller.callsign = callsign
            controller.name = name
            controller.note = note
            controller.save()
            return redirect("vagt:controllers")

        return render(request, "vagt/controllers/form.html", {
            "controller": controller,
            "errors": errors,
            "callsign": callsign,
            "name": name,
            "note": note,
        })

    return render(request, "vagt/controllers/form.html", {
        "controller": controller,
        "callsign": controller.callsign,
        "name": controller.name,
        "note": controller.note,
    })


@login_required
@require_POST
def controller_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a controller."""
    controller = get_object_or_404(Controller, pk=pk)
    controller.delete()
    return redirect("vagt:controllers")


# =============================================================================
# User Profile
# =============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request: HttpRequest) -> HttpResponse:
    """User profile page with password change."""
    password_form = PasswordChangeForm(request.user)
    password_changed = False

    if request.method == "POST":
        password_form = PasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)  # Keep user logged in
            password_changed = True
            password_form = PasswordChangeForm(request.user)  # Reset form

    return render(request, "vagt/profile.html", {
        "password_form": password_form,
        "password_changed": password_changed,
    })


# =============================================================================
# Documentation
# =============================================================================

# Available documentation pages with Danish titles (ordered)
# Using a list of tuples to maintain order for navigation
DOCS_LIST = [
    ("models", "Datamodeller"),
    ("views", "Views & Endpoints"),
    ("api", "REST API"),
    ("deployment", "Deployment"),
]

# Dict version for lookups
DOCS = dict(DOCS_LIST)


@login_required
@require_GET
def docs_index(request: HttpRequest) -> HttpResponse:
    """Documentation index page. Superuser only."""
    if not request.user.is_superuser:
        return redirect("vagt:board")
    return render(request, "vagt/docs/index.html", {"docs": DOCS})


@login_required
@require_GET
def docs_page(request: HttpRequest, slug: str) -> HttpResponse:
    """Render a documentation page from markdown. Superuser only."""
    if not request.user.is_superuser:
        return redirect("vagt:board")
    if slug not in DOCS:
        return redirect("vagt:docs")

    docs_dir = Path(settings.BASE_DIR) / "docs"
    md_file = docs_dir / f"{slug}.md"

    if not md_file.exists():
        return redirect("vagt:docs")

    content = md_file.read_text(encoding="utf-8")

    # Convert markdown to HTML with extensions
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc", "codehilite"],
        extension_configs={
            "codehilite": {"css_class": "highlight", "guess_lang": False},
            "toc": {"permalink": False, "toc_depth": 3},
        },
    )
    html_content = md.convert(content)

    # Compute previous/next navigation
    doc_slugs = [d[0] for d in DOCS_LIST]
    current_index = doc_slugs.index(slug)

    prev_doc = None
    next_doc = None

    if current_index > 0:
        prev_slug = doc_slugs[current_index - 1]
        prev_doc = {"slug": prev_slug, "title": DOCS[prev_slug]}

    if current_index < len(doc_slugs) - 1:
        next_slug = doc_slugs[current_index + 1]
        next_doc = {"slug": next_slug, "title": DOCS[next_slug]}

    return render(request, "vagt/docs/page.html", {
        "docs": DOCS,
        "current_slug": slug,
        "title": DOCS[slug],
        "content": html_content,
        "toc": getattr(md, "toc", ""),
        "prev_doc": prev_doc,
        "next_doc": next_doc,
    })
