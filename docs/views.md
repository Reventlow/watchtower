# Views Documentation

This document describes the views (endpoints) in the Watchtower (Vagt) application.

## Overview

All views are located in `/home/gorm/projects/watchtower/apps/vagt/views.py`.

The application uses function-based views with Django's decorator-based authentication and HTTP method restrictions. HTMX is used for dynamic updates without full page reloads.

## URL Configuration

### Vagt App URLs

Location: `/home/gorm/projects/watchtower/apps/vagt/urls.py`

| URL Pattern | View | Name | Description |
|-------------|------|------|-------------|
| `/` | `board_view` | `vagt:board` | Main board view |
| `/log/` | `log_view` | `vagt:log` | Change log |
| `/controller/<pk>/status/` | `set_status` | `vagt:set_status` | HTMX status update |
| `/controllers/` | `controller_list` | `vagt:controllers` | Controller management |
| `/controllers/add/` | `controller_add` | `vagt:controller_add` | Add controller |
| `/controllers/<pk>/edit/` | `controller_edit` | `vagt:controller_edit` | Edit controller |
| `/controllers/<pk>/delete/` | `controller_delete` | `vagt:controller_delete` | Delete controller |
| `/profile/` | `profile_view` | `vagt:profile` | User profile |

### Root URLs

Location: `/home/gorm/projects/watchtower/config/urls.py`

| URL Pattern | Include | Description |
|-------------|---------|-------------|
| `/admin/` | Django admin | Administration interface |
| `/` | `django.contrib.auth.urls` | Login, logout, password reset |
| `/` | `apps.vagt.urls` | Main application |
| `/api/` | `apps.api.urls` | REST API |

---

## Board Views

### board_view

**Main board view - shows all controllers with their status.**

```python
@login_required
@require_GET
def board_view(request: HttpRequest) -> HttpResponse
```

**URL**: `/` (GET)

**Authentication**: Required

**Context Variables**:
- `controllers`: List of dicts with `controller` and `last_log` keys
- `statuses`: List of status tuples `[("FERIE", "Ferie"), ...]`

**Template**: `vagt/board.html`

**Description**:

Renders the main board view showing all active controllers arranged in a grid. Each controller row shows the callsign, name, note, and status buttons for each status column.

The view prefetches status logs to efficiently display the last change information for each controller.

**Example Response** (HTML):

```html
<!-- Grid with header row and controller rows -->
<div class="grid grid-cols-5">
    <div><!-- Empty corner --></div>
    <div>Ferie</div>
    <div>Syg</div>
    <div>Modt</div>
    <div>Gaet</div>
    <!-- Controller rows with status buttons -->
</div>
```

---

### set_status

**HTMX endpoint to set a controller's status.**

```python
@login_required
@require_POST
def set_status(request: HttpRequest, pk: int) -> HttpResponse
```

**URL**: `/controller/<pk>/status/` (POST)

**Authentication**: Required

**POST Parameters**:
- `status`: New status value (`FERIE`, `SYG`, `MOEDT`, or `GAAET`)

**Template**: `vagt/partials/_controller_row.html`

**Description**:

This is an HTMX endpoint that handles status changes. When a user clicks a status button on the board, HTMX sends a POST request to this endpoint. The view:

1. Retrieves the controller by primary key
2. Validates the new status
3. Calls `controller.set_status()` to update and log the change
4. Returns the updated controller row HTML

**HTMX Integration**:

```html
<button hx-post="{% url 'vagt:set_status' controller.pk %}"
        hx-vals='{"status": "MOEDT"}'
        hx-target="#controller-{{ controller.pk }}"
        hx-swap="outerHTML">
</button>
```

The response replaces the entire controller row, updating the visual state without a full page reload.

---

### log_view

**View the status change log.**

```python
@login_required
@require_GET
def log_view(request: HttpRequest) -> HttpResponse
```

**URL**: `/log/` (GET)

**Authentication**: Required

**Context Variables**:
- `logs`: QuerySet of recent StatusLog objects (limit 100)
- `statuses`: Dict of status values to display names

**Template**: `vagt/log.html`

**Description**:

Displays a table of recent status changes showing:
- Timestamp
- Controller name and callsign
- Old status (with color coding)
- New status (with color coding)
- Username of who made the change

The log provides an audit trail for accountability and troubleshooting.

---

## Controller CRUD Views

### controller_list

**List all controllers for management.**

```python
@login_required
@require_GET
def controller_list(request: HttpRequest) -> HttpResponse
```

**URL**: `/controllers/` (GET)

**Authentication**: Required

**Context Variables**:
- `controllers`: All Controller objects ordered by callsign

**Template**: `vagt/controllers/list.html`

**Description**:

Shows a management list of all controllers (including inactive ones) with options to:
- Add new controller
- Edit existing controllers
- Delete controllers

---

### controller_add

**Add a new controller.**

```python
@login_required
@require_http_methods(["GET", "POST"])
def controller_add(request: HttpRequest) -> HttpResponse
```

**URL**: `/controllers/add/` (GET, POST)

**Authentication**: Required

**POST Parameters**:
- `callsign`: Unique radio callsign (required)
- `name`: Controller's name (required)
- `note`: Optional note

**Template**: `vagt/controllers/form.html`

**Description**:

Handles both displaying the add form (GET) and processing submissions (POST).

**Validation**:
- Callsign is required
- Name is required
- Callsign must be unique

**On Success**: Redirects to `vagt:controllers`

**On Error**: Re-renders form with error messages and preserved input

---

### controller_edit

**Edit a controller.**

```python
@login_required
@require_http_methods(["GET", "POST"])
def controller_edit(request: HttpRequest, pk: int) -> HttpResponse
```

**URL**: `/controllers/<pk>/edit/` (GET, POST)

**Authentication**: Required

**POST Parameters**: Same as `controller_add`

**Template**: `vagt/controllers/form.html`

**Description**:

Handles editing existing controllers. Pre-populates the form with current values.

**Validation**:
- Same as `controller_add`
- Callsign uniqueness check excludes current controller

---

### controller_delete

**Delete a controller.**

```python
@login_required
@require_POST
def controller_delete(request: HttpRequest, pk: int) -> HttpResponse
```

**URL**: `/controllers/<pk>/delete/` (POST)

**Authentication**: Required

**Description**:

Deletes a controller and all associated status logs (cascade delete).

**On Success**: Redirects to `vagt:controllers`

**Note**: Consider implementing soft-delete (setting `is_active=False`) instead of hard delete to preserve audit history.

---

## User Profile View

### profile_view

**User profile page with password change.**

```python
@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request: HttpRequest) -> HttpResponse
```

**URL**: `/profile/` (GET, POST)

**Authentication**: Required

**Context Variables**:
- `password_form`: Django PasswordChangeForm
- `password_changed`: Boolean indicating successful change

**Template**: `vagt/profile.html`

**Description**:

Allows users to change their password. Uses Django's built-in `PasswordChangeForm` with validation.

After successful password change, the user's session is updated to keep them logged in (`update_session_auth_hash`).

---

## Templates

### Base Template

Location: `/home/gorm/projects/watchtower/templates/base.html`

The base template provides:
- HTML structure with Danish language setting
- Tailwind CSS (CDN)
- HTMX library
- Dark mode support with localStorage persistence
- Responsive navigation with mobile menu
- Theme toggle button
- CSRF token injection for HTMX requests
- Toast/notification container
- Footer with copyright

### Template Inheritance

```
base.html
├── registration/login.html
├── vagt/board.html
├── vagt/log.html
├── vagt/profile.html
└── vagt/controllers/
    ├── list.html
    └── form.html
```

### Partials (HTMX Fragments)

Location: `/home/gorm/projects/watchtower/templates/vagt/partials/`

| Template | Description |
|----------|-------------|
| `_controller_row.html` | Single controller row for the board |
| `_status_buttons.html` | Status button group |
| `_audit_tooltip.html` | Last change tooltip |
| `_undo_toast.html` | Undo notification |

These partials are returned by HTMX endpoints to update specific parts of the page.

---

## Authentication Flow

### Login

URL: `/login/` (provided by `django.contrib.auth.urls`)

After successful login, users are redirected to `vagt:board` (configured in settings as `LOGIN_REDIRECT_URL`).

### Logout

URL: `/logout/` (provided by `django.contrib.auth.urls`)

After logout, users are redirected to `/login/` (configured as `LOGOUT_REDIRECT_URL`).

### Login Required

All vagt views use the `@login_required` decorator. Unauthenticated requests are redirected to `/login/` with a `next` parameter for post-login redirect.

---

## Error Handling

### 404 Not Found

The `get_object_or_404` shortcut is used for controller lookups. Invalid primary keys return a 404 response.

### Form Validation Errors

Form errors are displayed inline in the templates. The views collect errors into a list and pass them to the template context.

### CSRF Protection

All POST requests require a valid CSRF token. HTMX requests include the token via the `hx-headers` attribute on the body element:

```html
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
```

---

## Performance Considerations

### Database Queries

- `board_view` uses `prefetch_related("status_logs")` to avoid N+1 queries
- `log_view` uses `select_related("controller", "changed_by")` for efficient joins
- `set_status` uses `select_related("changed_by")` for the log query

### Caching

Currently, no caching is implemented. For high-traffic deployments, consider:
- Template fragment caching for the board
- Session-based caching for user data
- Redis/Memcached for production
