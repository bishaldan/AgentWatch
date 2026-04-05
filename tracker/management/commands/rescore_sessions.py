from django.core.management.base import BaseCommand

from tracker.ingest import persist_scoring
from tracker.models import Session


class Command(BaseCommand):
    help = "Recompute session scores and signals for all tracked sessions."

    def handle(self, *args, **options):
        count = 0
        for session in Session.objects.select_related("visitor").prefetch_related("request_events", "resource_events"):
            persist_scoring(session)
            count += 1
        self.stdout.write(f"Rescored {count} sessions.")
