
import os
import logging
import smtplib
import requests

from email.message import EmailMessage
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)


class NotificationService:

    def __init__(self):

        # Telegram configuration
        self.telegram_enabled = (
            os.getenv("TELEGRAM_ENABLED", "false").lower()
            == "true"
        )

        self.telegram_bot_token = os.getenv(
            "TELEGRAM_BOT_TOKEN"
        )

        self.telegram_chat_id = os.getenv(
            "TELEGRAM_CHAT_ID"
        )

        # Email configuration
        self.email_enabled = (
            os.getenv("EMAIL_ENABLED", "false").lower()
            == "true"
        )

        self.smtp_host = os.getenv(
            "SMTP_HOST", "smtp.gmail.com"
        )

        self.smtp_port = int(
            os.getenv("SMTP_PORT", "587")
        )

        self.smtp_use_ssl = (
            os.getenv("SMTP_USE_SSL", "false").lower()
            == "true"
        )

        self.smtp_username = os.getenv(
            "SMTP_USERNAME"
        )

        self.smtp_password = os.getenv(
            "SMTP_PASSWORD"
        )

        self.email_from = os.getenv(
            "EMAIL_FROM"
        )

        self.email_to = os.getenv(
            "EMAIL_TO"
        )

    # ------------------------------------------
    # TELEGRAM NOTIFICATION
    # ------------------------------------------

    def send_telegram(self, message: str) -> bool:

        if not self.telegram_enabled:
            logger.info("Telegram notifications disabled.")
            return False

        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.error("Telegram credentials are missing.")
            return False

        url = (
            f"https://api.telegram.org/"
            f"bot{self.telegram_bot_token}/sendMessage"
        )

        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message
        }

        try:

            response = requests.post(
                url,
                json=payload,
                timeout=15
            )

            response.raise_for_status()

            result = response.json()

            if not result.get("ok"):
                logger.error(
                    "Telegram API rejected message: %s",
                    result
                )
                return False

            logger.info("Telegram notification sent.")
            return True

        except requests.RequestException:

            logger.exception(
                "Failed to send Telegram notification."
            )

            return False

    # ------------------------------------------
    # EMAIL NOTIFICATION
    # ------------------------------------------

    def send_email(
        self,
        subject: str,
        message: str
    ) -> bool:

        if not self.email_enabled:
            logger.info("Email notifications disabled.")
            return False

        required_values = [
            self.smtp_username,
            self.smtp_password,
            self.email_from,
            self.email_to
        ]

        if not all(required_values):

            logger.error(
                "Email configuration is incomplete."
            )

            return False

        email = EmailMessage()

        email["Subject"] = subject
        email["From"] = self.email_from
        email["To"] = self.email_to

        email.set_content(message)

        try:

            if self.smtp_use_ssl:

                with smtplib.SMTP_SSL(
                    self.smtp_host,
                    self.smtp_port,
                    timeout=15
                ) as server:

                    server.login(
                        self.smtp_username,
                        self.smtp_password
                    )

                    server.send_message(email)

            else:

                with smtplib.SMTP(
                    self.smtp_host,
                    self.smtp_port,
                    timeout=15
                ) as server:

                    server.ehlo()
                    server.starttls()
                    server.ehlo()

                    server.login(
                        self.smtp_username,
                        self.smtp_password
                    )

                    server.send_message(email)

            logger.info("Email notification sent.")
            return True

        except (smtplib.SMTPException, OSError):

            logger.exception(
                "Failed to send email notification."
            )

            return False

    # ------------------------------------------
    # FORMAT ALERT MESSAGE
    # ------------------------------------------

    def format_alert(self, alert: dict) -> str:

        severity = alert.get(
            "severity", "UNKNOWN"
        )

        category = alert.get(
            "category", "General"
        )

        message = alert.get(
            "message", "No details available."
        )

        return (
            "LLMOPS MONITORING ALERT\n"
            "------------------------------\n"
            f"Severity: {severity}\n"
            f"Category: {category}\n"
            f"Message: {message}\n"
            "------------------------------\n"
            "Check your LLMOps monitoring dashboard."
        )

    # ------------------------------------------
    # SEND TO BOTH CHANNELS
    # ------------------------------------------

    def send_alert(self, alert: dict) -> dict:

        message = self.format_alert(alert)

        severity = alert.get(
            "severity", "UNKNOWN"
        )

        category = alert.get(
            "category", "General"
        )

        subject = (
            f"[{severity}] LLMOps Alert - {category}"
        )

        telegram_result = None
        email_result = None

        if self.telegram_enabled:

            telegram_result = self.send_telegram(
                message
            )

        if self.email_enabled:

            email_result = self.send_email(
                subject,
                message
            )

        return {
            "telegram": telegram_result,
            "email": email_result
        }

    # ------------------------------------------
    # TEST NOTIFICATIONS
    # ------------------------------------------

    def send_test_notifications(self):

        test_alert = {
            "severity": "INFO",
            "category": "Notification Test",
            "message": (
                "Your LLMOps notification system "
                "is configured successfully."
            )
        }

        return self.send_alert(test_alert)
