# Deployment Guide

This document covers deploying the Watchtower (Vagt) application to production.

## Overview

The application is designed for containerized deployment using Docker. It can also be deployed directly on a Linux server with Python and a WSGI server.

## Deployment Options

1. **Docker Compose** (recommended for single-server deployments)
2. **Docker with external orchestration** (Kubernetes, Docker Swarm)
3. **Direct deployment** (systemd service)

---

## Docker Compose Deployment

### Prerequisites

- Docker Engine 24.0+
- Docker Compose v2.0+
- Domain name with DNS configured

### Step-by-Step

1. **Clone the repository**:
   ```bash
   git clone <repository-url> /opt/watchtower
   cd /opt/watchtower
   ```

2. **Create environment file**:
   ```bash
   cp .env.example .env
   ```

3. **Configure environment variables**:
   ```bash
   # Generate a secure secret key
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"

   # Edit .env
   nano .env
   ```

   Required settings:
   ```ini
   DJANGO_SECRET_KEY=<generated-secret-key>
   DJANGO_ALLOWED_HOSTS=vagt.fynbus.net,localhost
   DJANGO_SETTINGS_MODULE=config.settings.production
   DJANGO_DEBUG=False
   ```

4. **Build and start**:
   ```bash
   docker-compose up -d --build
   ```

5. **Run migrations** (first time only):
   ```bash
   docker-compose exec web python manage.py migrate
   ```

6. **Create superuser**:
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

7. **Verify deployment**:
   ```bash
   # Check container status
   docker-compose ps

   # Check logs
   docker-compose logs -f web

   # Test health endpoint
   curl http://localhost:8000/api/health/
   ```

### Docker Volumes

| Volume | Mount Point | Description |
|--------|-------------|-------------|
| `vagt-sqlite-data` | `/data` | SQLite database |
| `vagt-static-files` | `/app/staticfiles` | Collected static files |

### Updating

```bash
cd /opt/watchtower
git pull
docker-compose build
docker-compose up -d
docker-compose exec web python manage.py migrate
```

---

## Reverse Proxy Configuration

### Nginx

Place behind nginx for SSL termination and static file serving:

```nginx
upstream watchtower {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name vagt.fynbus.net;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name vagt.fynbus.net;

    ssl_certificate /etc/letsencrypt/live/vagt.fynbus.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vagt.fynbus.net/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Static files (optional - WhiteNoise handles this)
    # location /static/ {
    #     alias /opt/watchtower/staticfiles/;
    #     expires 30d;
    #     add_header Cache-Control "public, immutable";
    # }

    location / {
        proxy_pass http://watchtower;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Traefik

If using Traefik, add labels to docker-compose.yml:

```yaml
services:
  web:
    # ... existing config ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.watchtower.rule=Host(`vagt.fynbus.net`)"
      - "traefik.http.routers.watchtower.entrypoints=websecure"
      - "traefik.http.routers.watchtower.tls.certresolver=letsencrypt"
      - "traefik.http.services.watchtower.loadbalancer.server.port=8000"
```

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Cryptographic secret (50+ characters) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated list of valid hosts |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_DEBUG` | `False` | Never enable in production |
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` | Settings module |
| `DATABASE_URL` | SQLite | Database connection URL |
| `DJANGO_SECURE_SSL_REDIRECT` | `True` | Redirect HTTP to HTTPS |
| `DJANGO_SECURE_HSTS_SECONDS` | `31536000` | HSTS max-age (1 year) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | ` ` | Origins for CSRF |
| `DJANGO_LOG_LEVEL` | `WARNING` | Logging verbosity |

### Email (Optional)

| Variable | Description |
|----------|-------------|
| `EMAIL_HOST` | SMTP server hostname |
| `EMAIL_PORT` | SMTP port (587 for TLS) |
| `EMAIL_USE_TLS` | Enable STARTTLS |
| `EMAIL_HOST_USER` | SMTP username |
| `EMAIL_HOST_PASSWORD` | SMTP password |
| `DEFAULT_FROM_EMAIL` | Sender address |

---

## Database Options

### SQLite (Default)

Suitable for low to medium traffic (< 100 concurrent users).

- Persistent storage via Docker volume
- WAL mode for better concurrency
- Simple backup (copy file)

**Backup**:
```bash
docker cp vagt-web:/data/db.sqlite3 ./backup/db.sqlite3
```

### PostgreSQL (Recommended for High Traffic)

For high-traffic deployments, use PostgreSQL:

1. **Add PostgreSQL to docker-compose.yml**:
   ```yaml
   services:
     db:
       image: postgres:16-alpine
       volumes:
         - postgres_data:/var/lib/postgresql/data
       environment:
         POSTGRES_DB: watchtower
         POSTGRES_USER: watchtower
         POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

     web:
       depends_on:
         - db
       environment:
         DATABASE_URL: postgres://watchtower:${POSTGRES_PASSWORD}@db:5432/watchtower

   volumes:
     postgres_data:
   ```

2. **Install psycopg**:
   Add to requirements.txt:
   ```
   psycopg[binary]>=3.1
   dj-database-url>=2.1
   ```

3. **Update settings**:
   Uncomment the PostgreSQL configuration in `config/settings/production.py`.

---

## Security Checklist

Before going live:

- [ ] `DJANGO_SECRET_KEY` is unique and secure (50+ chars)
- [ ] `DJANGO_DEBUG` is `False`
- [ ] `DJANGO_ALLOWED_HOSTS` is set correctly
- [ ] HTTPS is configured with valid certificate
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` includes your domain
- [ ] Database is not exposed to public network
- [ ] Admin password is strong
- [ ] Firewall allows only necessary ports (80, 443)
- [ ] Docker containers run as non-root user
- [ ] Logs do not contain sensitive data
- [ ] Backup strategy is in place and tested

---

## Monitoring

### Health Check

The `/api/health/` endpoint returns:
```json
{"status": "healthy", "service": "watchtower"}
```

Use this for:
- Load balancer health checks
- Uptime monitoring (Uptime Robot, Pingdom, etc.)
- Docker health checks (configured in docker-compose.yml)

### Logging

Logs are written to stdout/stderr and captured by Docker:

```bash
# View logs
docker-compose logs -f web

# View last 100 lines
docker-compose logs --tail=100 web
```

In production, configure log aggregation (ELK, Loki, etc.) or forward to syslog.

### Metrics

Consider adding:
- **django-prometheus** for application metrics
- **Sentry** for error tracking

---

## Backup Strategy

### Database

**Daily backup with retention**:

```bash
#!/bin/bash
# /opt/watchtower/scripts/backup.sh

BACKUP_DIR="/opt/backups/watchtower"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup
docker cp vagt-web:/data/db.sqlite3 "$BACKUP_DIR/db_$DATE.sqlite3"

# Compress
gzip "$BACKUP_DIR/db_$DATE.sqlite3"

# Remove old backups
find "$BACKUP_DIR" -name "db_*.sqlite3.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $BACKUP_DIR/db_$DATE.sqlite3.gz"
```

**Cron job**:
```cron
0 2 * * * /opt/watchtower/scripts/backup.sh >> /var/log/watchtower-backup.log 2>&1
```

### Restore

```bash
# Stop container
docker-compose down

# Restore backup
gunzip < backup/db_20260204.sqlite3.gz > /tmp/db.sqlite3
docker cp /tmp/db.sqlite3 vagt-web:/data/db.sqlite3

# Start container
docker-compose up -d
```

---

## Scaling

### Horizontal Scaling

For multiple application instances:

1. Switch to PostgreSQL (SQLite doesn't support concurrent writes from multiple processes)
2. Use shared session storage (Redis, database)
3. Use a load balancer

### Gunicorn Workers

Adjust workers in Dockerfile CMD:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", ...]
```

Rule of thumb: `workers = (2 * CPU cores) + 1`

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs web

# Check if port is in use
sudo lsof -i :8000

# Verify environment
docker-compose config
```

### Static files not loading

```bash
# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Check static files directory
docker-compose exec web ls -la /app/staticfiles/
```

### Database locked (SQLite)

This occurs with multiple concurrent writes. Solutions:
- Reduce worker count to 1-2
- Enable WAL mode (default)
- Switch to PostgreSQL

### CSRF errors

Ensure `DJANGO_CSRF_TRUSTED_ORIGINS` includes your domain:
```ini
DJANGO_CSRF_TRUSTED_ORIGINS=https://vagt.fynbus.net
```

---

## Direct Deployment (No Docker)

For deployment without Docker:

1. **Install system dependencies**:
   ```bash
   sudo apt update
   sudo apt install python3.12 python3.12-venv nginx
   ```

2. **Create application user**:
   ```bash
   sudo useradd -m -s /bin/bash watchtower
   sudo su - watchtower
   ```

3. **Setup application**:
   ```bash
   git clone <repository-url> ~/watchtower
   cd ~/watchtower
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install gunicorn
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   nano .env  # Set production values
   ```

5. **Run migrations**:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py createsuperuser
   ```

6. **Create systemd service** (`/etc/systemd/system/watchtower.service`):
   ```ini
   [Unit]
   Description=Watchtower (Vagt) Application
   After=network.target

   [Service]
   User=watchtower
   Group=watchtower
   WorkingDirectory=/home/watchtower/watchtower
   Environment="PATH=/home/watchtower/watchtower/venv/bin"
   EnvironmentFile=/home/watchtower/watchtower/.env
   ExecStart=/home/watchtower/watchtower/venv/bin/gunicorn \
       --bind 127.0.0.1:8000 \
       --workers 2 \
       --threads 2 \
       config.wsgi:application
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

7. **Enable and start**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable watchtower
   sudo systemctl start watchtower
   ```

8. **Configure nginx** as reverse proxy (see above).
