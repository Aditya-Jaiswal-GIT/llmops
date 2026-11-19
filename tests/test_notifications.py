
from app.services.notification_service import NotificationService


def main():

    service = NotificationService()

    print("\nTesting LLMOps notifications...")

    if not service.telegram_enabled and not service.email_enabled:

        print("ERROR: Both notification channels are disabled.")
        return

    results = service.send_test_notifications()

    print("\nNotification results:")

    for channel, result in results.items():

        if result is None:

            print(f"{channel}: DISABLED")

        elif result:

            print(f"{channel}: SUCCESS")

        else:

            print(f"{channel}: FAILED")

    print("\nNotification test completed.")


if __name__ == "__main__":

    main()
