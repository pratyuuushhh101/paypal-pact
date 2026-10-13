"""Celery application configuration for pact_core."""

import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pact_core.settings")

app: Celery = Celery("pact_core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
