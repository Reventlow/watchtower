# REST API Documentation

This document describes the REST API endpoints provided by the Watchtower (Vagt) application.

## Overview

The API provides read-only access to controller and status log data for integration with external systems. All endpoints (except health check) require authentication.

### Base URL

```
/api/
```

### API Version

Current version: `v1`

Versioned endpoints are prefixed with `/api/v1/`.

---

## Authentication

### Methods

The API supports two authentication methods:

1. **Personal Access Token** (recommended for integrations)
2. **Session Authentication** (for browser-based access)

### Personal Access Token

Tokens are passed in the `Authorization` header using the Bearer scheme:

```http
Authorization: Bearer <token>
```

**Example**:

```bash
curl -H "Authorization: Bearer abc123..." https://vagt.fynbus.net/api/v1/controllers/
```

### Creating Tokens

Tokens can be created via the Django admin or programmatically:

```python
from apps.vagt.models import PersonalAccessToken

# Create a token that expires in 30 days
token_obj, raw_token = PersonalAccessToken.issue(
    user=user,
    label="Integration Script",
    ttl_hours=24 * 30
)

# Store raw_token securely - it cannot be retrieved later
print(f"Your token: {raw_token}")
```

### Token Security

- Tokens are stored as SHA-256 hashes
- Raw tokens are only shown once at creation
- Tokens can be revoked without deletion
- Optional expiration dates are supported
- `last_used_at` is updated on each successful authentication

### Session Authentication

For browser-based API access (e.g., using the browsable API in development), standard Django session authentication is supported. Login via the web interface first.

---

## Endpoints

### Health Check

Check if the service is running.

```http
GET /api/health/
```

**Authentication**: None required

**Response**:

```json
{
    "status": "healthy",
    "service": "watchtower"
}
```

**Status Codes**:
- `200 OK`: Service is healthy

**Use Case**: Load balancer health checks, monitoring systems.

---

### List Controllers

Get all active controllers with their current status.

```http
GET /api/v1/controllers/
```

**Authentication**: Required

**Response**:

```json
{
    "count": 3,
    "results": [
        {
            "id": 1,
            "number": "01",
            "name": "Theis",
            "employee_id": "E001",
            "status": "MOEDT",
            "status_display": "Modt"
        },
        {
            "id": 2,
            "number": "02",
            "name": "Casper",
            "employee_id": "E002",
            "status": "GAAET",
            "status_display": "Gaet"
        }
    ]
}
```

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique identifier |
| `number` | string | Callsign/radio number |
| `name` | string | Controller's name |
| `employee_id` | string | Employee identifier |
| `status` | string | Current status code |
| `status_display` | string | Human-readable status |

**Status Codes**:
- `200 OK`: Success
- `401 Unauthorized`: Invalid or missing authentication

**Note**: Only active controllers (`is_active=True`) are returned.

---

### List Status Logs

Get recent status changes.

```http
GET /api/v1/logs/
```

**Authentication**: Required

**Query Parameters**:

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `limit` | integer | 50 | 200 | Number of logs to return |

**Response**:

```json
{
    "count": 2,
    "results": [
        {
            "id": 42,
            "controller": "01 Theis",
            "old_status": "GAAET",
            "new_status": "MOEDT",
            "changed_by": "admin",
            "changed_at": "2026-02-04T08:15:30+01:00"
        },
        {
            "id": 41,
            "controller": "02 Casper",
            "old_status": "MOEDT",
            "new_status": "GAAET",
            "changed_by": "admin",
            "changed_at": "2026-02-04T08:10:15+01:00"
        }
    ]
}
```

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Log entry identifier |
| `controller` | string | Controller callsign and name |
| `old_status` | string | Previous status code |
| `new_status` | string | New status code |
| `changed_by` | string | Username who made the change (null if system) |
| `changed_at` | string | ISO 8601 timestamp |

**Status Codes**:
- `200 OK`: Success
- `401 Unauthorized`: Invalid or missing authentication

**Example with limit**:

```bash
curl -H "Authorization: Bearer abc123..." \
     "https://vagt.fynbus.net/api/v1/logs/?limit=10"
```

---

## Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request succeeded |
| 400 | Bad Request | Invalid request parameters |
| 401 | Unauthorized | Authentication required or failed |
| 403 | Forbidden | Authenticated but not authorized |
| 404 | Not Found | Resource not found |
| 405 | Method Not Allowed | HTTP method not supported |
| 500 | Internal Server Error | Server error |

---

## Error Responses

Errors are returned as JSON with a descriptive message:

```json
{
    "detail": "Invalid or expired token"
}
```

For validation errors:

```json
{
    "field_name": ["Error message 1", "Error message 2"]
}
```

---

## Rate Limiting

Currently, no rate limiting is implemented. For production deployments, consider implementing rate limiting at the reverse proxy level (nginx, Cloudflare, etc.).

---

## CORS

Cross-Origin Resource Sharing (CORS) is not configured by default. If you need to access the API from a browser on a different domain, configure CORS headers:

1. Install django-cors-headers:
   ```bash
   pip install django-cors-headers
   ```

2. Add to settings:
   ```python
   INSTALLED_APPS = [
       ...
       "corsheaders",
   ]

   MIDDLEWARE = [
       "corsheaders.middleware.CorsMiddleware",
       ...
   ]

   CORS_ALLOWED_ORIGINS = [
       "https://your-frontend-domain.com",
   ]
   ```

---

## Browsable API

In development mode (`DEBUG=True`), the Django REST Framework browsable API is enabled. Access any endpoint in a browser to see an interactive HTML interface for exploring the API.

In production, only JSON responses are returned.

---

## Code Examples

### Python (requests)

```python
import requests

API_URL = "https://vagt.fynbus.net/api/v1"
TOKEN = "your-token-here"

headers = {"Authorization": f"Bearer {TOKEN}"}

# Get all controllers
response = requests.get(f"{API_URL}/controllers/", headers=headers)
controllers = response.json()["results"]

for c in controllers:
    print(f"{c['number']} {c['name']}: {c['status_display']}")

# Get recent logs
response = requests.get(f"{API_URL}/logs/?limit=10", headers=headers)
logs = response.json()["results"]

for log in logs:
    print(f"{log['changed_at']}: {log['controller']} {log['old_status']} -> {log['new_status']}")
```

### JavaScript (fetch)

```javascript
const API_URL = 'https://vagt.fynbus.net/api/v1';
const TOKEN = 'your-token-here';

async function getControllers() {
    const response = await fetch(`${API_URL}/controllers/`, {
        headers: {
            'Authorization': `Bearer ${TOKEN}`,
            'Content-Type': 'application/json'
        }
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data.results;
}

// Usage
getControllers()
    .then(controllers => {
        controllers.forEach(c => {
            console.log(`${c.number} ${c.name}: ${c.status_display}`);
        });
    })
    .catch(error => console.error('Error:', error));
```

### cURL

```bash
# Health check (no auth required)
curl https://vagt.fynbus.net/api/health/

# List controllers
curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://vagt.fynbus.net/api/v1/controllers/

# List logs with limit
curl -H "Authorization: Bearer YOUR_TOKEN" \
     "https://vagt.fynbus.net/api/v1/logs/?limit=20"
```

---

## Serializers

The API uses Django REST Framework serializers located in `/home/gorm/projects/watchtower/apps/api/serializers.py`.

Additional serializers are defined for more complex responses (shift management, etc.) but are not currently exposed via endpoints.

---

## Future Endpoints

Planned but not yet implemented:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/controllers/<id>/` | GET | Single controller details |
| `/api/v1/controllers/<id>/status/` | PUT | Update controller status |
| `/api/v1/shifts/` | GET | List shifts |
| `/api/v1/shifts/current/` | GET | Current active shift |

Contact the development team if you need these endpoints prioritized.
