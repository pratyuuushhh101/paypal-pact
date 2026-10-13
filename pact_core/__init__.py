"""Initialize Celery application on Django startup."""

from .celery import app as celery_app

__all__: tuple[str, ...] = ("celery_app",)
