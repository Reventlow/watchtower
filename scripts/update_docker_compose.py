#!/usr/bin/env python3
"""
Update docker-compose.yml with the new image version.

Usage: python scripts/update_docker_compose.py <new_version>
"""

import re
import sys
from pathlib import Path


def update_compose_file(file_path: Path, new_version: str, image_name: str) -> bool:
    """
    Update image tags in a docker-compose file.

    Args:
        file_path: Path to the docker-compose file.
        new_version: The new version tag.
        image_name: The Docker image name (without tag).

    Returns:
        True if file was updated, False otherwise.
    """
    if not file_path.exists():
        print(f"Warning: {file_path} not found, skipping.")
        return False

    content = file_path.read_text()

    # Check if file uses build: instead of image:
    # If so, we need to add/update the image line
    if "build:" in content and f"image: {image_name}" not in content:
        # Add image line after build section
        # Find the build: section and add image after it
        pattern = r"(build:\s*\n\s+context:.*\n\s+dockerfile:.*\n)"
        replacement = rf"\g<1>    image: {image_name}:{new_version}\n"
        new_content, count = re.subn(pattern, replacement, content)

        if count == 0:
            # Simple build: . case
            pattern = r"(build:\s*\.?\n)"
            replacement = rf"\g<1>    image: {image_name}:{new_version}\n"
            new_content, count = re.subn(pattern, replacement, content)
    else:
        # Pattern to match image lines with our image name
        # Matches: image: elohite/watchtower:version or image: elohite/watchtower
        pattern = rf"(image:\s*{re.escape(image_name)})(:\S+)?"
        replacement = rf"\g<1>:{new_version}"
        new_content, count = re.subn(pattern, replacement, content)

    if count > 0:
        file_path.write_text(new_content)
        print(f"Updated {file_path}: {count} image reference(s) updated to {new_version}")
        return True
    else:
        print(f"Warning: No image references found in {file_path}")
        return False


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/update_docker_compose.py <new_version>")
        sys.exit(1)

    new_version = sys.argv[1]
    image_name = "elohite/watchtower"
    project_root = Path(__file__).parent.parent

    # Update compose files
    files_to_update = [
        project_root / "docker-compose.yml",
        project_root / "docker-compose.prod.yml",
    ]

    updated = False
    for file_path in files_to_update:
        if file_path.exists():
            if update_compose_file(file_path, new_version, image_name):
                updated = True

    if not updated:
        print("No files were updated.")
        sys.exit(1)


if __name__ == "__main__":
    main()
