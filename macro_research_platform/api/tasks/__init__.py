"""
Celery tasks module for background processing.

Task modules are loaded explicitly by the Celery app's `include` list (see celery_app.py);
nothing is imported here, so one task module's import error can't break the others.
"""
