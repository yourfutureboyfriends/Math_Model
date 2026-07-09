
# Macro Terminal v8.0 — Celery Configuration (Phase 9C)
# Replaces APScheduler with distributed task queue


import os
from datetime import timedelta

from celery import Celery
from celery.signals import task_postrun, task_prerun

# Broker and backend configuration
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# Create Celery app
app = Celery(
    "macro_terminal",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "tasks.pipeline_tasks",
        "tasks.signal_tasks",
        "tasks.report_tasks",
        "tasks.alternative_data_tasks",
        "tasks.llm_tasks",
    ],
)

# Celery configuration
app.conf.update(
    # Task execution
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/New_York",
    enable_utc=True,

    # Task routing
    task_routes={
        "tasks.pipeline_tasks.*": {"queue": "pipeline"},
        "tasks.signal_tasks.*": {"queue": "signals"},
        "tasks.report_tasks.*": {"queue": "reports"},
        "tasks.alternative_data_tasks.*": {"queue": "pipeline"},
        "tasks.llm_tasks.*": {"queue": "reports"},
    },

    # Task defaults
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",

    # Result backend
    result_expires=timedelta(hours=24),
    result_extended=True,

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,

    # RedBeat scheduler (for dynamic scheduling)
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=BROKER_URL,
    redbeat_key_prefix="redbeat:",
    redbeat_lock_key="redbeat:lock",
    redbeat_lock_timeout=timedelta(minutes=5),
)


# Celery Beat Schedule (Replaces APScheduler)


app.conf.beat_schedule = {
    # Market data refresh (every 5 minutes during market hours)
    "refresh-market-data": {
        "task": "tasks.pipeline_tasks.refresh_market_data",
        "schedule": timedelta(minutes=5),
        "options": {"queue": "pipeline"},
    },

    # Economic indicators update (every hour)
    "update-economic-indicators": {
        "task": "tasks.pipeline_tasks.update_economic_indicators",
        "schedule": timedelta(hours=1),
        "options": {"queue": "pipeline"},
    },

    # COT data (weekly, Tuesdays after CFTC release)
    "update-cot-data": {
        "task": "tasks.pipeline_tasks.update_cot_data",
        "schedule": crontab(hour=16, minute=0, day_of_week="tue"),
        "options": {"queue": "pipeline"},
    },

    # Vol surface update (every 15 minutes)
    "update-vol-surface": {
        "task": "tasks.pipeline_tasks.update_vol_surface",
        "schedule": timedelta(minutes=15),
        "options": {"queue": "pipeline"},
    },

    # Signal generation (every 30 minutes)
    "generate-signals": {
        "task": "tasks.signal_tasks.generate_all_signals",
        "schedule": timedelta(minutes=30),
        "options": {"queue": "signals"},
    },

    # Regime classification (every hour)
    "classify-regime": {
        "task": "tasks.signal_tasks.classify_regime",
        "schedule": timedelta(hours=1),
        "options": {"queue": "signals"},
    },

    # Daily reports (8 AM ET)
    "generate-daily-report": {
        "task": "tasks.report_tasks.generate_daily_report",
        "schedule": crontab(hour=8, minute=0),
        "options": {"queue": "reports"},
    },

    # Weekly reports (Monday 9 AM ET)
    "generate-weekly-report": {
        "task": "tasks.report_tasks.generate_weekly_report",
        "schedule": crontab(hour=9, minute=0, day_of_week="mon"),
        "options": {"queue": "reports"},
    },

    # Alternative data (Google Trends - daily)
    "fetch-google-trends": {
        "task": "tasks.alternative_data_tasks.fetch_google_trends",
        "schedule": crontab(hour=10, minute=0),
        "options": {"queue": "pipeline"},
    },

    # News sentiment analysis (every 30 minutes)
    "analyze-news-sentiment": {
        "task": "tasks.llm_tasks.analyze_recent_news",
        "schedule": timedelta(minutes=30),
        "options": {"queue": "reports"},
    },

    # Regime transition forecasting (daily)
    "forecast-regime-transition": {
        "task": "tasks.signal_tasks.forecast_regime_transition",
        "schedule": crontab(hour=7, minute=0),
        "options": {"queue": "signals"},
    },

    # P&L snapshot (every 5 minutes during market hours)
    "snapshot-portfolio": {
        "task": "tasks.signal_tasks.snapshot_portfolio",
        "schedule": timedelta(minutes=5),
        "options": {"queue": "signals"},
    },

    # System health check (every minute)
    "check-system-health": {
        "task": "tasks.pipeline_tasks.check_system_health",
        "schedule": timedelta(minutes=1),
        "options": {"queue": "pipeline"},
    },
}


# Signal Handlers




@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kw):
    """Log task start"""
    import logging
    logger = logging.getLogger("celery")
    logger.info(f"Starting task: {task.name} [{task_id}]")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None,
                         kwargs=None, retval=None, state=None, **kw):
    """Log task completion"""
    import logging
    logger = logging.getLogger("celery")
    logger.info(f"Completed task: {task.name} [{task_id}] with state: {state}")


if __name__ == "__main__":
    app.start()
