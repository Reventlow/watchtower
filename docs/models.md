# Data Models

This document describes the database models used in the Watchtower (Vagt) application.

## Overview

The application uses three main models:

1. **Controller** - Represents a ticket controller (person) on the board
2. **StatusLog** - Audit trail for all status changes
3. **PersonalAccessToken** - API authentication tokens

## Entity Relationship

```
┌─────────────────┐       ┌─────────────────┐
│   Controller    │       │      User       │
├─────────────────┤       │   (built-in)    │
│ id              │       ├─────────────────┤
│ callsign        │       │ id              │
│ name            │       │ username        │
│ note            │       │ ...             │
│ is_active       │       └────────┬────────┘
│ status          │                │
│ status_changed_at│               │
│ status_changed_by├───────────────┤
│ created_at      │                │
│ updated_at      │                │
└────────┬────────┘                │
         │                         │
         │ 1:N                     │
         ▼                         │
┌─────────────────┐                │
│   StatusLog     │                │
├─────────────────┤                │
│ id              │                │
│ controller (FK) │                │
│ changed_by (FK) ├────────────────┤
│ changed_at      │                │
│ old_status      │                │
│ new_status      │                │
└─────────────────┘                │
                                   │
┌─────────────────┐                │
│ PersonalAccess  │                │
│     Token       │                │
├─────────────────┤                │
│ id              │                │
│ user (FK)       ├────────────────┘
│ label           │
│ token_hash      │
│ created_at      │
│ expires_at      │
│ revoked_at      │
│ last_used_at    │
└─────────────────┘
```

## Controller

Represents a ticket controller on the board. This is analogous to a row on the physical magnetic board.

### Location

`/home/gorm/projects/watchtower/apps/vagt/models.py`

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | BigAutoField | Primary key (auto-generated) |
| `callsign` | CharField(10) | Radio callsign, e.g., "01", "02". **Unique**. |
| `name` | CharField(120) | Controller's name, e.g., "Theis", "Casper" |
| `note` | CharField(50) | Optional note, e.g., "Flex", "Deltid" |
| `is_active` | BooleanField | Whether controller appears on the board |
| `status` | CharField(10) | Current status (see Status Choices) |
| `status_changed_at` | DateTimeField | When status was last changed |
| `status_changed_by` | ForeignKey(User) | Who made the last change |
| `created_at` | DateTimeField | Record creation timestamp |
| `updated_at` | DateTimeField | Last modification timestamp |

### Status Choices

```python
class Status(models.TextChoices):
    FERIE = "FERIE", "Ferie"    # Vacation
    SYG = "SYG", "Syg"          # Sick
    MOEDT = "MOEDT", "Modt"     # On duty
    GAAET = "GAAET", "Gaet"     # Off duty
```

### Methods

#### `set_status(new_status: str, by_user=None) -> None`

Sets the controller's status and creates an audit log entry.

```python
controller = Controller.objects.get(callsign="01")
controller.set_status("MOEDT", by_user=request.user)
```

This method:
1. Checks if status actually changed (no-op if same)
2. Updates `status`, `status_changed_at`, and `status_changed_by`
3. Creates a `StatusLog` entry
4. Saves with optimized field list

### Ordering

Controllers are ordered by `callsign` by default, ensuring "01" comes before "02", etc.

### String Representation

Returns `"{callsign} {name} {note}"`, e.g., "01 Theis Flex"

---

## StatusLog

Audit trail for status changes. Every call to `Controller.set_status()` creates a log entry.

### Location

`/home/gorm/projects/watchtower/apps/vagt/models.py`

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | BigAutoField | Primary key |
| `controller` | ForeignKey(Controller) | The controller whose status changed |
| `changed_by` | ForeignKey(User) | User who made the change (nullable) |
| `changed_at` | DateTimeField | When the change occurred |
| `old_status` | CharField(10) | Previous status value |
| `new_status` | CharField(10) | New status value |

### Relationships

- **controller**: `CASCADE` delete (logs are deleted when controller is deleted)
- **changed_by**: `SET_NULL` (logs preserved if user is deleted)

### Ordering

Logs are ordered by `-changed_at` (newest first).

### String Representation

Returns `"{name}: {old_status} -> {new_status}"`, e.g., "Theis: GAAET -> MOEDT"

### Usage

```python
# Get recent logs for a controller
logs = StatusLog.objects.filter(controller=controller)[:10]

# Get all changes by a specific user
user_changes = StatusLog.objects.filter(changed_by=user)

# Get today's changes
from django.utils import timezone
today = timezone.now().date()
today_logs = StatusLog.objects.filter(changed_at__date=today)
```

---

## PersonalAccessToken

Token-based authentication for the REST API. Tokens are stored as SHA-256 hashes for security.

### Location

`/home/gorm/projects/watchtower/apps/vagt/models.py`

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | BigAutoField | Primary key |
| `user` | ForeignKey(User) | Token owner |
| `label` | CharField(80) | Human-readable label, e.g., "Integration Script" |
| `token_hash` | CharField(64) | SHA-256 hash of the token. **Unique**. |
| `created_at` | DateTimeField | When token was created |
| `expires_at` | DateTimeField | Optional expiration timestamp |
| `revoked_at` | DateTimeField | When token was revoked (if applicable) |
| `last_used_at` | DateTimeField | Last successful authentication |

### Properties

#### `is_revoked -> bool`

Returns `True` if the token has been revoked.

#### `is_expired -> bool`

Returns `True` if the token has an expiration date that has passed.

### Methods

#### `is_active() -> bool`

Returns `True` if the token is neither revoked nor expired.

#### `issue(user, label: str, ttl_hours: int | None = None) -> tuple[PersonalAccessToken, str]` (classmethod)

Creates a new token and returns both the model instance and the raw token.

```python
token_obj, raw_token = PersonalAccessToken.issue(
    user=user,
    label="My Integration",
    ttl_hours=24 * 30  # 30 days
)
# raw_token is shown to user once, then lost
# token_obj.token_hash is stored in database
```

**Important**: The raw token is only available at creation time. Store it securely.

#### `authenticate_raw_token(raw_token: str) -> PersonalAccessToken | None` (classmethod)

Authenticates a raw token and returns the token object if valid.

```python
token = PersonalAccessToken.authenticate_raw_token(raw_token)
if token:
    user = token.user
    # Token is valid, update last_used_at
else:
    # Invalid, expired, or revoked
```

This method:
1. Hashes the provided token
2. Looks up the hash in the database
3. Checks if token is active
4. Updates `last_used_at` timestamp
5. Returns the token object or `None`

### Security

- Tokens are 32 bytes of cryptographically secure random data (URL-safe base64 encoded)
- Only the SHA-256 hash is stored; raw tokens cannot be recovered from the database
- Tokens can be revoked without deletion (preserves audit trail)
- Optional expiration provides time-limited access

### Ordering

Tokens are ordered by `-created_at` (newest first).

---

## Database Migrations

Migrations are stored in `/home/gorm/projects/watchtower/apps/vagt/migrations/`.

### Creating Migrations

```bash
python manage.py makemigrations vagt
```

### Applying Migrations

```bash
python manage.py migrate
```

### Viewing Migration Status

```bash
python manage.py showmigrations vagt
```

---

## Database Considerations

### SQLite (Default)

The application uses SQLite with WAL (Write-Ahead Logging) mode for better concurrency:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL;",
        },
    }
}
```

WAL mode allows:
- Readers do not block writers
- Writers do not block readers
- Better performance for read-heavy workloads

### PostgreSQL (Production)

For high-traffic production deployments, configure PostgreSQL:

```python
import dj_database_url
DATABASES = {
    "default": dj_database_url.config(
        default="postgres://user:password@localhost:5432/watchtower",
        conn_max_age=600,
        conn_health_checks=True,
    )
}
```

### Indexes

The following indexes are created automatically:
- `Controller.callsign` - unique index
- `PersonalAccessToken.token_hash` - unique index
- All foreign key fields have indexes

Consider adding additional indexes for:
- `StatusLog.changed_at` if querying by date range frequently
- `Controller.is_active` if filtering active controllers often
