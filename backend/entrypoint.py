#!/usr/bin/env python3
import os
import sys
import subprocess


def main():
    service = os.getenv("SERVICE", "gunicorn")

    if service == "runserver":
        cmd = [
            "python", "manage.py", "runserver",
            f"0.0.0.0:{os.getenv('PORT', '8000')}"
        ]
    elif service == "scheduler":
        from saa_collector.scheduler import Scheduler
        Scheduler().start()
    else:
        cmd = [
            "gunicorn",
            "--bind", f"0.0.0.0:{os.getenv('PORT', '8000')}",
            "--workers", os.getenv("GUNICORN_WORKERS", "1"),
            "--threads", os.getenv("GUNICORN_THREADS", "4"),
            "--access-logfile", "-",
            "--error-logfile", "-",
            "config.wsgi:application",
        ]

    print(f"Starting: {' '.join(cmd)}")
    sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
