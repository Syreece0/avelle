#!/usr/bin/env bash
# Render build step: install, fetch GSAP (optional), collect static files, migrate.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Self-host GSAP. If the download fails the site falls back to the CDN, so this never fails the build.
python manage.py fetch_vendor || echo "GSAP not self-hosted; the CDN copy will be used."

python manage.py collectstatic --no-input
python manage.py migrate --no-input
