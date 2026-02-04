#!/bin/bash
# =============================================================================
# Watchtower (Vagt) - Docker Entrypoint Script
# =============================================================================
# This script runs before the main application command.
# It handles database migrations and other startup tasks.

set -e

echo "========================================"
echo "Watchtower (Vagt) - Starting up..."
echo "========================================"

# Wait for database to be ready (SQLite should always be ready)
echo "Checking database..."

# Run migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Create cache table if using database cache
# python manage.py createcachetable --dry-run 2>/dev/null && python manage.py createcachetable

echo "========================================"
echo "Startup complete. Running command..."
echo "========================================"

# Execute the main command
exec "$@"
