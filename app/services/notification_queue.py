
import logging
import sqlite3

from datetime import datetime, timezone, timedelta

from app.core.observability import get_connection
from app.services.notification_service import NotificationService


logger = logging.getLogger(__name__)

notification_service = NotificationService()

MAX_ATTEMPTS = 5
BASE_RETRY_SECONDS = 60
MAX_RETRY_SECONDS = 3600


def utc_now():
    return datetime.now(timezone.utc)


def initialize_notification_queue():

    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_state (
                alert_key TEXT NOT NULL,
                channel TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                last_sent_at TEXT,
                PRIMARY KEY (alert_key, channel)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_key TEXT NOT NULL,
                channel TEXT NOT NULL,
                severity TEXT,
                category TEXT,
                message TEXT,
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                next_retry_at TEXT,
                sent_at TEXT,
                last_error TEXT
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_notification_status_retry
            ON notification_logs(status, next_retry_at)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_notification_created
            ON notification_logs(created_at)
        """)

    logger.info("Notification queue initialized.")


# ==================================================
# ADD NOTIFICATION TO QUEUE
# ==================================================

def enqueue_notification(
    alert_key: str,
    channel: str,
    alert: dict
) -> bool:

    now = utc_now().isoformat()

    message = notification_service.format_alert(alert)

    try:

        with get_connection() as conn:

            # Check whether this alert is already active
            # for this notification channel.

            row = conn.execute(
                """
                SELECT is_active
                FROM notification_state
                WHERE alert_key = ? AND channel = ?
                """,
                (alert_key, channel)
            ).fetchone()

            if row and row[0]:

                return False

            # Add the notification to the queue.

            conn.execute(
                """
                INSERT INTO notification_logs (
                    alert_key,
                    channel,
                    severity,
                    category,
                    message,
                    status,
                    attempts,
                    max_attempts,
                    created_at,
                    updated_at,
                    next_retry_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                """,
                (
                    alert_key,
                    channel,
                    alert.get("severity"),
                    alert.get("category"),
                    message,
                    MAX_ATTEMPTS,
                    now,
                    now,
                    now
                )
            )

            # Mark this alert as active immediately.
            # This prevents duplicate queue entries.

            conn.execute(
                """
                INSERT INTO notification_state (
                    alert_key,
                    channel,
                    is_active,
                    last_sent_at
                )
                VALUES (?, ?, 1, NULL)
                ON CONFLICT(alert_key, channel)
                DO UPDATE SET is_active = 1
                """,
                (alert_key, channel)
            )

        logger.info(
            "Notification queued: %s via %s",
            alert_key,
            channel
        )

        return True

    except Exception:

        logger.exception(
            "Could not enqueue notification: %s",
            alert_key
        )

        return False


# ==================================================
# MARK RESOLVED ALERTS
# ==================================================

def mark_resolved_alerts(active_alert_keys):

    with get_connection() as conn:

        rows = conn.execute(
            """
            SELECT alert_key, channel
            FROM notification_state
            WHERE is_active = 1
            """
        ).fetchall()

        for row in rows:

            alert_key = row[0]
            channel = row[1]

            if alert_key not in active_alert_keys:

                conn.execute(
                    """
                    UPDATE notification_state
                    SET is_active = 0
                    WHERE alert_key = ? AND channel = ?
                    """,
                    (alert_key, channel)
                )

                logger.info(
                    "Alert resolved: %s",
                    alert_key
                )


# ==================================================
# GET PENDING NOTIFICATIONS
# ==================================================

def get_pending_notifications(limit=50):

    now = utc_now().isoformat()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT *
            FROM notification_logs
            WHERE status = 'pending'
              AND next_retry_at <= ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (now, limit)
        ).fetchall()

    return [dict(row) for row in rows]


# ==================================================
# UPDATE DELIVERY RESULT
# ==================================================

def update_notification_result(
    notification_id: int,
    success: bool,
    attempts: int,
    error: str = None
):

    now = utc_now()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT *
            FROM notification_logs
            WHERE id = ?
            """,
            (notification_id,)
        ).fetchone()

        if not row:
            return

        if success:

            conn.execute(
                """
                UPDATE notification_logs
                SET status = 'sent',
                    attempts = ?,
                    updated_at = ?,
                    sent_at = ?,
                    next_retry_at = NULL,
                    last_error = NULL
                WHERE id = ?
                """,
                (
                    attempts,
                    now.isoformat(),
                    now.isoformat(),
                    notification_id
                )
            )

            conn.execute(
                """
                UPDATE notification_state
                SET last_sent_at = ?
                WHERE alert_key = ? AND channel = ?
                """,
                (
                    now.isoformat(),
                    row["alert_key"],
                    row["channel"]
                )
            )

            logger.info(
                "Notification %s sent successfully.",
                notification_id
            )

            return

        max_attempts = row["max_attempts"]

        if attempts >= max_attempts:

            conn.execute(
                """
                UPDATE notification_logs
                SET status = 'failed',
                    attempts = ?,
                    updated_at = ?,
                    next_retry_at = NULL,
                    last_error = ?
                WHERE id = ?
                """,
                (
                    attempts,
                    now.isoformat(),
                    error,
                    notification_id
                )
            )

            logger.error(
                "Notification %s permanently failed.",
                notification_id
            )

        else:

            # Exponential backoff:
            # 60, 120, 240, 480 seconds...

            delay = min(
                BASE_RETRY_SECONDS * (2 ** (attempts - 1)),
                MAX_RETRY_SECONDS
            )

            next_retry = (
                now + timedelta(seconds=delay)
            ).isoformat()

            conn.execute(
                """
                UPDATE notification_logs
                SET status = 'pending',
                    attempts = ?,
                    updated_at = ?,
                    next_retry_at = ?,
                    last_error = ?
                WHERE id = ?
                """,
                (
                    attempts,
                    now.isoformat(),
                    next_retry,
                    error,
                    notification_id
                )
            )

            logger.warning(
                "Notification %s failed. Retry scheduled in %s seconds.",
                notification_id,
                delay
            )


# ==================================================
# PROCESS PENDING NOTIFICATIONS
# ==================================================

def process_pending_notifications():

    notifications = get_pending_notifications()

    for notification in notifications:

        notification_id = notification["id"]

        channel = notification["channel"]

        message = notification["message"]

        attempts = notification["attempts"] + 1

        success = False

        error = "Notification delivery failed."

        try:

            if channel == "telegram":

                success = notification_service.send_telegram(
                    message
                )

            elif channel == "email":

                subject = (
                    f"[{notification['severity']}] "
                    f"LLMOps Alert - {notification['category']}"
                )

                success = notification_service.send_email(
                    subject,
                    message
                )

            else:

                error = f"Unsupported channel: {channel}"

                logger.error(error)

        except Exception as exc:

            error = str(exc)

            logger.exception(
                "Unexpected notification delivery error."
            )

        update_notification_result(
            notification_id=notification_id,
            success=success,
            attempts=attempts,
            error=None if success else error
        )

    return len(notifications)


# ==================================================
# NOTIFICATION HISTORY
# ==================================================

def get_notification_history(limit=50):

    limit = max(1, min(limit, 500))

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT
                id,
                alert_key,
                channel,
                severity,
                category,
                status,
                attempts,
                max_attempts,
                created_at,
                updated_at,
                next_retry_at,
                sent_at,
                last_error
            FROM notification_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    return [dict(row) for row in rows]
