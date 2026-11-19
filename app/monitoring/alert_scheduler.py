
import logging
import os
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.observability import (
    get_request_metrics,
    get_cost_metrics
)

from app.services.notification_service import NotificationService

from app.services.notification_queue import (
    initialize_notification_queue,
    enqueue_notification,
    mark_resolved_alerts,
    process_pending_notifications
)

from dashboard.alert_config import ALERT_THRESHOLDS

from dashboard.alert_service import evaluate_alerts


load_dotenv()


TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED")
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED")

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(
    timezone="UTC"
)

notification_service = NotificationService()


# ==================================================
# CHECK ALERTS AND ADD TO QUEUE
# ==================================================

def check_and_queue_alerts():

    metrics = get_request_metrics()
    costs = get_cost_metrics()

    alerts = evaluate_alerts(metrics, costs)

    active_alert_keys = set()

    for alert in alerts:

        alert_key = f"{alert['severity']}:{alert['category']}"
        active_alert_keys.add(alert_key)

        if TELEGRAM_ENABLED:
            enqueue_notification(
                alert_key,
                "telegram",
                alert
            )

        if EMAIL_ENABLED:
            enqueue_notification(
                alert_key,
                "email",
                alert
            )

    mark_resolved_alerts(active_alert_keys)


# ==================================================
# PROCESS NOTIFICATION QUEUE
# ==================================================

def process_notification_queue():

    try:

        count = process_pending_notifications()

        if count:

            logger.info(
                "Processed %s queued notifications.",
                count
            )

    except Exception:

        logger.exception(
            "Notification queue processing failed."
        )


# ==================================================
# START SCHEDULER
# ==================================================

def start_alert_scheduler():

    if scheduler.running:
        return

    initialize_notification_queue()

    alert_interval = max(
        30,
        int(
            os.getenv(
                "ALERT_CHECK_INTERVAL_SECONDS",
                "60"
            )
        )
    )

    scheduler.add_job(
        check_and_queue_alerts,
        trigger="interval",
        seconds=alert_interval,
        id="llmops_alert_checker",
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )

    scheduler.add_job(
        process_notification_queue,
        trigger="interval",
        seconds=15,
        id="llmops_notification_processor",
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )

    scheduler.start()

    # Run an initial check rather than waiting
    # for the first interval.

    check_and_queue_alerts()

    process_notification_queue()

    logger.info(
        "LLMOps alert scheduler started."
    )


# ==================================================
# STOP SCHEDULER
# ==================================================

def stop_alert_scheduler():

    if scheduler.running:

        scheduler.shutdown(
            wait=False
        )

        logger.info(
            "LLMOps alert scheduler stopped."
        )
