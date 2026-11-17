#!/usr/bin/env bash
# Render build step: install, fetch GSAP (optional), collect static files, migrate.
set -o errexit

# manage.py defaults to the development settings; the build must use production settings so that
# collectstatic writes the fingerprinted files and manifest the live site expects.
export DJANGO_SETTINGS_MODULE=config.settings.prod

pip install --upgrade pip
pip install -r requirements.txt

# Self-host GSAP. If the download fails the site falls back to the CDN, so this never fails the build.
python manage.py fetch_vendor || echo "GSAP not self-hosted; the CDN copy will be used."

python manage.py collectstatic --no-input
python manage.py migrate --no-input
