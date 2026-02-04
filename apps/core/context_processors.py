"""
Context processors for the Watchtower project.
"""

from datetime import datetime
from pathlib import Path

from django.conf import settings


def version_info(request):
    """
    Add version information to template context.

    Returns:
        dict with 'version' and 'version_date' keys
    """
    version_file = Path(settings.BASE_DIR) / "version.txt"

    version = "0.0.0"
    version_date = None

    if version_file.exists():
        version = version_file.read_text().strip()
        # Get file modification time as version date
        mtime = version_file.stat().st_mtime
        version_date = datetime.fromtimestamp(mtime)

    return {
        "app_version": version,
        "app_version_date": version_date,
    }
