from django.core.management.base import BaseCommand

from core.analytics.ingest import ingest_all


class Command(BaseCommand):
    help = "Parse logs/access.log* and upsert rows into the PageView table (idempotent)."

    def handle(self, *args, **options):
        created = ingest_all()
        self.stdout.write(self.style.SUCCESS(f"Ingested {created} new row(s)."))
