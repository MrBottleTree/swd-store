import os

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.helper import compress_image_bytes
from core.models import Image


class Command(BaseCommand):
    help = (
        "Resize and recompress every Image row's file in place. "
        "Use --dry-run to preview savings without writing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Compute savings but do not write any files or update DB rows.",
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help="Process at most N images (useful for sanity-check runs).",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        total_before = 0
        total_after = 0
        processed = 0
        skipped_missing = 0
        skipped_no_gain = 0
        failed = 0

        qs = Image.objects.all().order_by('id')
        for image in qs.iterator(chunk_size=100):
            if limit is not None and processed >= limit:
                break

            field = image.image
            try:
                old_path = field.path
            except (ValueError, NotImplementedError):
                skipped_missing += 1
                continue

            if not os.path.exists(old_path):
                self.stdout.write(self.style.WARNING(
                    f"[skip] Image#{image.id}: file missing at {field.name}"
                ))
                skipped_missing += 1
                continue

            old_size = os.path.getsize(old_path)

            try:
                with open(old_path, 'rb') as fh:
                    new_bytes = compress_image_bytes(fh)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f"[fail] Image#{image.id} ({field.name}): {exc}"
                ))
                failed += 1
                continue

            new_size = len(new_bytes)
            old_ext = os.path.splitext(old_path)[1].lower()
            ext_changes = old_ext not in ('.jpg', '.jpeg')

            if new_size >= old_size and not ext_changes:
                skipped_no_gain += 1
                continue

            total_before += old_size
            total_after += new_size
            processed += 1

            saved_pct = (1 - new_size / old_size) * 100 if old_size else 0
            tag = '[dry]' if dry_run else '[ok ]'
            self.stdout.write(
                f"{tag} Image#{image.id} {field.name}: "
                f"{_fmt_bytes(old_size)} -> {_fmt_bytes(new_size)} "
                f"({saved_pct:+.1f}%)"
            )

            if dry_run:
                continue

            if ext_changes:
                base_dir = os.path.dirname(field.name) or ''
                stem = os.path.splitext(os.path.basename(field.name))[0] or 'image'
                new_name = os.path.join(base_dir, f'{stem}.jpg').replace('\\', '/')
                saved_name = field.storage.save(new_name, ContentFile(new_bytes))
                old_name = field.name
                image.image.name = saved_name
                image.save(update_fields=['image'])
                try:
                    field.storage.delete(old_name)
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(
                        f"      could not delete old {old_name}: {exc}"
                    ))
            else:
                tmp_path = old_path + '.tmp'
                with open(tmp_path, 'wb') as out:
                    out.write(new_bytes)
                os.replace(tmp_path, old_path)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"Done. processed={processed} skipped_no_gain={skipped_no_gain} "
            f"skipped_missing={skipped_missing} failed={failed}"
        ))
        if processed:
            saved = total_before - total_after
            pct = (saved / total_before * 100) if total_before else 0
            mode = 'would save' if dry_run else 'saved'
            self.stdout.write(self.style.SUCCESS(
                f"{mode} {_fmt_bytes(saved)} "
                f"({_fmt_bytes(total_before)} -> {_fmt_bytes(total_after)}, {pct:.1f}%)"
            ))


def _fmt_bytes(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f"{n:.1f}{unit}" if unit != 'B' else f"{n}{unit}"
        n /= 1024
    return f"{n:.1f}GB"
