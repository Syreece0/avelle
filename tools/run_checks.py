#!/usr/bin/env python3
"""Run every check that needs no database or Django install. Exit status 1 if any fails.

    python tools/run_checks.py

Django tests need a working install and are run separately:  python manage.py test
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = [
    ("Python syntax", [sys.executable, "-m", "compileall", "-q", "apps", "config", "manage.py", "tools"]),
    ("Static project check (urls, templates, ORM fields, settings)", [sys.executable, "tools/check_project.py"]),
    ("Colour contrast", [sys.executable, "tools/contrast.py"]),
    ("Dashboard rules", [sys.executable, "tests_standalone/test_dashboard_rules.py"]),
    ("Paystack client", [sys.executable, "tests_standalone/test_paystack_client.py"]),
    ("Image URL optimiser", [sys.executable, "tests_standalone/test_cdn.py"]),
]
failed = []
for label, cmd in STEPS:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    ok = result.returncode == 0
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        failed.append(label)
        print((result.stdout + result.stderr).strip()[-1500:])
print("\nAll checks passed." if not failed else f"\n{len(failed)} check(s) failed.")
sys.exit(1 if failed else 0)
