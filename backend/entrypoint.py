#!/usr/bin/env python3
import os
import sys
import subprocess


def should_cleanup_interrupted_collect_tasks(service):
    if service != "celery-worker":
        return False
    if os.getenv("CLEANUP_INTERRUPTED_COLLECT_TASKS_ON_START", "true").lower() in ("0", "false", "no", "off"):
        return False
    return os.getenv("COLLECTOR_CELERY_QUEUE", "collector") == "collector"


def cleanup_interrupted_collect_tasks():
    cmd = ["python", "manage.py", "cleanup_interrupted_collect_tasks"]
    print(f"Starting: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    service = os.getenv("SERVICE", "gunicorn")

    if service == "runserver":
        cmd = [
            "python", "manage.py", "runserver",
            f"0.0.0.0:{os.getenv('PORT', '8000')}"
        ]
    elif service == "celery-worker":
        cmd = [
            "celery",
            "-A", "config",
            "worker",
            "--loglevel", os.getenv("CELERY_LOG_LEVEL", "INFO"),
            "--concurrency", os.getenv("CELERY_WORKER_CONCURRENCY", "1"),
            "--queues", os.getenv("COLLECTOR_CELERY_QUEUE", "collector"),
        ]
        max_tasks_per_child = os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD")
        if max_tasks_per_child:
            cmd.extend(["--max-tasks-per-child", max_tasks_per_child])
        max_memory_per_child = os.getenv("CELERY_WORKER_MAX_MEMORY_PER_CHILD")
        if max_memory_per_child:
            cmd.extend(["--max-memory-per-child", max_memory_per_child])
    elif service == "celery-beat":
        cmd = [
            "celery",
            "-A", "config",
            "beat",
            "--loglevel", os.getenv("CELERY_LOG_LEVEL", "INFO"),
        ]
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

    if should_cleanup_interrupted_collect_tasks(service):
        cleanup_interrupted_collect_tasks()

    print(f"Starting: {' '.join(cmd)}")
    sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
