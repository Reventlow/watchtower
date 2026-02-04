# Watchtower (Vagt)

A Django application for FynBus that digitizes the physical magnetic board used for tracking ticket controller statuses. The system provides real-time status tracking with full audit logging.

## Overview

Watchtower replaces a physical magnetic board where ticket controllers' status magnets are moved between columns. Each controller has a callsign (e.g., "01", "02") used for radio communication, and their status is tracked across four states:

| Status | Danish | Description |
|--------|--------|-------------|
| FERIE | Ferie | On vacation |
| SYG | Syg | Sick leave |
| MOEDT | Modt | On duty (checked in) |
| GAAET | Gaet | Off duty (checked out) |

## Features

- **Digital Board Interface**: Visual representation of the physical magnetic board
- **Real-time Updates**: HTMX-powered instant status changes without page reloads
- **Audit Trail**: Complete logging of all status changes with timestamps and user attribution
- **Controller Management**: CRUD operations for managing controllers
- **User Authentication**: Login required for all board operations
- **Dark Mode**: System-aware theme with manual toggle
- **REST API**: Read-only API for integration with external systems
- **Token Authentication**: Personal access tokens for API access
- **Danish UI**: Native Danish language interface
- **Responsive Design**: Works on desktop and mobile devices

## Tech Stack

- **Backend**: Django 5.x with Django REST Framework
- **Frontend**: HTMX 2.x + Tailwind CSS (CDN)
- **Database**: SQLite with WAL mode (PostgreSQL-ready)
- **Static Files**: WhiteNoise
- **WSGI Server**: Gunicorn
- **Containerization**: Docker with multi-stage builds

## Project Structure

```
watchtower/
├── apps/
│   ├── api/           # REST API endpoints
│   ├── core/          # Shared utilities
│   └── vagt/          # Main application (models, views)
├── config/
│   ├── settings/
│   │   ├── base.py        # Shared settings
│   │   ├── development.py # Dev settings (DEBUG=True)
│   │   └── production.py  # Production settings
│   ├── urls.py        # Root URL configuration
│   ├── wsgi.py        # WSGI entry point
│   └── asgi.py        # ASGI entry point
├── templates/
│   ├── base.html      # Base template with navigation
│   ├── registration/  # Login templates
│   └── vagt/          # Application templates
├── static/            # Static assets
├── scripts/
│   └── entrypoint.sh  # Docker entrypoint
├── docs/              # Documentation
├── Dockerfile         # Production Docker image
├── docker-compose.yml # Docker Compose configuration
├── requirements.txt   # Python dependencies
└── manage.py          # Django management script
```

## Local Development Setup

### Prerequisites

- Python 3.12+
- pip or pipx

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd watchtower
   ```

2. **Create and activate virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or
   .venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env as needed (defaults work for development)
   ```

5. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create superuser**:
   ```bash
   python manage.py createsuperuser
   ```

7. **Start development server**:
   ```bash
   export DJANGO_SETTINGS_MODULE=config.settings.development
   python manage.py runserver
   ```

8. **Access the application**:
   - Board: http://localhost:8000/
   - Admin: http://localhost:8000/admin/
   - API: http://localhost:8000/api/

## Docker Deployment

### Quick Start

1. **Create environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with production values:
   # - Generate a secure DJANGO_SECRET_KEY
   # - Set DJANGO_ALLOWED_HOSTS
   ```

2. **Generate secret key**:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

3. **Start the service**:
   ```bash
   docker-compose up -d
   ```

4. **Create superuser**:
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

5. **View logs**:
   ```bash
   docker-compose logs -f web
   ```

### Docker Volumes

- `vagt-sqlite-data`: Persistent database storage at `/data`
- `vagt-static-files`: Collected static files at `/app/staticfiles`

### Backup

```bash
# Backup database
docker cp vagt-web:/data/db.sqlite3 ./backup/db.sqlite3

# Restore database
docker cp ./backup/db.sqlite3 vagt-web:/data/db.sqlite3
docker-compose restart
```

## Usage

### Board View

The main board shows all active controllers with their current status. Click on a status circle to change a controller's status. The active status is highlighted with a larger, colored circle:

- **Red**: On duty (Modt)
- **Green**: Off duty (Gaet)
- **Amber**: Vacation or Sick (Ferie/Syg)

Hovering over the active status shows who made the last change and when.

### Change Log

Access the change log at `/log/` to view the history of all status changes, including:
- Timestamp
- Controller name and callsign
- Previous and new status
- User who made the change

### Controller Management

Manage controllers at `/controllers/`:
- Add new controllers with callsign, name, and optional note
- Edit existing controller details
- Delete controllers (with cascade delete of status logs)

### Admin Interface

The Django admin at `/admin/` provides full access to:
- User management
- Controller management with inline status logs
- Personal access token management

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health/` | GET | None | Health check |
| `/api/v1/controllers/` | GET | Required | List active controllers |
| `/api/v1/logs/` | GET | Required | List recent status changes |

See [docs/api.md](docs/api.md) for full API documentation.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | `insecure-...` | **Required in production** |
| `DJANGO_DEBUG` | `False` | Enable debug mode |
| `DJANGO_ALLOWED_HOSTS` | ` ` | Comma-separated allowed hosts |
| `DJANGO_SETTINGS_MODULE` | `config.settings.base` | Settings module path |
| `DATABASE_URL` | SQLite | Database connection URL |
| `DJANGO_LOG_LEVEL` | `INFO` | Logging level |

See `.env.example` for all available options.

## Documentation

- [Data Models](docs/models.md) - Database schema and model documentation
- [Views](docs/views.md) - View functions and templates
- [REST API](docs/api.md) - API endpoints and authentication
- [Deployment](docs/deployment.md) - Production deployment guide

## Security Considerations

- All board operations require authentication
- CSRF protection on all POST requests
- Passwords validated against common patterns
- Production settings enforce HTTPS and secure cookies
- API tokens are SHA-256 hashed in the database
- Non-root user in Docker container

## License

Copyright FynBus. Internal use only.
