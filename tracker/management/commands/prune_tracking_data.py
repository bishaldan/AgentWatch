from django.core.management.base import BaseCommand

from tracker.ingest import prune_old_data


class Command(BaseCommand):
    help = "Prune raw tracking data older than retention settings and anonymize stale identities."

    def handle(self, *args, **options):
        result = prune_old_data()
        self.stdout.write(
            "Prune complete: "
            f"{result['request_events_deleted']} request rows, "
            f"{result['resource_events_deleted']} resource rows, "
            f"{result['sessions_deleted']} sessions."
        )
