# =============================================================================
# Watchtower (Vagt) - Production Dockerfile
# =============================================================================
# Multi-stage build for a minimal, secure production image

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and use a non-root user for building
RUN useradd --create-home --shell /bin/bash builder
USER builder
WORKDIR /home/builder

# Create virtual environment
RUN python -m venv /home/builder/venv
ENV PATH="/home/builder/venv/bin:$PATH"

# Install Python dependencies
COPY --chown=builder:builder pyproject.toml requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Production
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS production

# Labels
LABEL maintainer="FynBus IT <it@fynbus.dk>" \
      description="Watchtower (Vagt) - Shift Management System" \
      version="1.0.0"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # App settings
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PORT=8000 \
    # Paths
    APP_HOME=/app \
    DATA_DIR=/data

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd --gid 1000 vagt && \
    useradd --uid 1000 --gid vagt --shell /bin/bash --create-home vagt

# Create application directories
RUN mkdir -p ${APP_HOME} ${DATA_DIR} && \
    chown -R vagt:vagt ${APP_HOME} ${DATA_DIR}

# Copy virtual environment from builder
COPY --from=builder --chown=vagt:vagt /home/builder/venv /home/vagt/venv
ENV PATH="/home/vagt/venv/bin:$PATH"

# Set working directory
WORKDIR ${APP_HOME}

# Copy application code
COPY --chown=vagt:vagt . .

# Switch to non-root user
USER vagt

# Collect static files (will be done at build time with a dummy secret)
RUN DJANGO_SECRET_KEY=build-time-secret \
    DJANGO_DEBUG=False \
    DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

# Expose port
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health/ || exit 1

# Entry point
COPY --chown=vagt:vagt scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Default command: run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", \
     "--worker-class", "gthread", "--worker-tmp-dir", "/dev/shm", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "--capture-output", "--enable-stdio-inheritance", \
     "config.wsgi:application"]
