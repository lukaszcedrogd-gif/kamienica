from django.core.management.base import BaseCommand
from django.db import transaction
from core.services.transaction_processing import process_csv_file, AI_MODES


class Command(BaseCommand):
    help = "Compare Ollama AI categorization modes for a CSV file without persisting changes."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the CSV file to process")
        parser.add_argument(
            "--modes",
            nargs="+",
            default=AI_MODES,
            choices=AI_MODES,
            help="Which AI categorization modes to compare",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        modes = options["modes"]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Comparing AI modes: {', '.join(modes)}"
        ))

        for mode in modes:
            self.stdout.write(self.style.NOTICE(f"\nMode: {mode}"))
            with open(csv_path, "rb") as csv_file:
                with transaction.atomic():
                    summary = process_csv_file(csv_file, ai_mode=mode)
                    transaction.set_rollback(True)

                self.stdout.write(self.style.SUCCESS(
                    f"Processed: {summary['processed_count']}, "
                    f"Conflicts: {summary['conflict_count']}, "
                    f"Unprocessed: {summary['unprocessed_count']}, "
                    f"Manual work: {summary['has_manual_work']}, "
                    f"Skipped: {len(summary['skipped_rows'])}, "
                    f"Encoding warning: {summary['encoding_warning']}"
                ))

                if summary["skipped_rows"]:
                    self.stdout.write(self.style.WARNING(
                        f"Skipped rows: {summary['skipped_rows'][:5]}"
                    ))
