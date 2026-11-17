"""Download the pinned GSAP build into static/vendor/gsap/ so pages don't depend on a third-party CDN.

Run during the Render build (see build.sh). Failure is not fatal: without the files the templates use the
pinned CDN copy instead. Files are sanity-checked (size and a GSAP marker) before being written.
"""
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

VERSION = "3.12.5"
BASE = f"https://cdnjs.cloudflare.com/ajax/libs/gsap/{VERSION}/"
FILES = {"gsap.min.js": 50_000, "ScrollTrigger.min.js": 20_000}  # name -> minimum plausible bytes


class Command(BaseCommand):
    help = "Download GSAP and ScrollTrigger into static/vendor/gsap/."

    def handle(self, *args, **options):
        target = Path(settings.BASE_DIR) / "static" / "vendor" / "gsap"
        target.mkdir(parents=True, exist_ok=True)
        for name, minimum in FILES.items():
            try:
                response = requests.get(BASE + name, timeout=30)
                response.raise_for_status()
            except requests.RequestException as error:
                raise CommandError(f"Could not download {name}: {error}") from error
            body = response.content
            if len(body) < minimum or b"gsap" not in body.lower():
                raise CommandError(f"{name} did not look like GSAP ({len(body)} bytes); not saved.")
            (target / name).write_bytes(body)
            self.stdout.write(f"saved {name} ({len(body):,} bytes)")
