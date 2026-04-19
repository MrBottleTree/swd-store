import hashlib
import os
import threading
from pathlib import Path

from django.conf import settings

from .parser import parse_line

LOGS_DIR = Path(settings.BASE_DIR) / 'logs'
LOCK_FILE = Path(settings.BASE_DIR) / '.cache' / 'ingest.lock'
BATCH_SIZE = 1000

_ingest_lock = threading.Lock()
_ingest_running = False


def _file_signature(path):
    st = os.stat(path)
    with open(path, 'rb') as f:
        head = f.read(1024)
    head_hash = hashlib.md5(head).hexdigest() if head else 'empty'
    try:
        inode = st.st_ino
    except AttributeError:
        inode = 0
    return f"{inode}:{head_hash}"[:64]


def _iter_log_files():
    if not LOGS_DIR.exists():
        return
    for p in sorted(LOGS_DIR.glob('access.log*')):
        if p.is_file():
            yield p


def ingest_all():
    from core.models import PageView, LogIngestState

    created_total = 0
    for path in _iter_log_files():
        try:
            sig = _file_signature(path)
        except OSError:
            continue

        state, _ = LogIngestState.objects.get_or_create(
            signature=sig,
            defaults={'filename': path.name, 'byte_offset': 0},
        )
        try:
            size = path.stat().st_size
        except OSError:
            continue

        if state.byte_offset > size:
            state.byte_offset = 0

        if state.byte_offset >= size:
            if state.filename != path.name:
                state.filename = path.name
                state.save(update_fields=['filename'])
            continue

        buffer = []
        new_offset = state.byte_offset
        try:
            with open(path, 'rb') as f:
                f.seek(state.byte_offset)
                for raw in f:
                    new_offset += len(raw)
                    try:
                        line = raw.decode('utf-8', errors='replace')
                    except Exception:
                        continue
                    parsed = parse_line(line)
                    if not parsed:
                        continue
                    line_hash = hashlib.md5(line.strip().encode('utf-8')).hexdigest()
                    buffer.append(PageView(
                        source_file=path.name[:64],
                        line_hash=line_hash,
                        **parsed,
                    ))
                    if len(buffer) >= BATCH_SIZE:
                        PageView.objects.bulk_create(buffer, ignore_conflicts=True, batch_size=BATCH_SIZE)
                        created_total += len(buffer)
                        buffer = []
        except OSError:
            continue

        if buffer:
            PageView.objects.bulk_create(buffer, ignore_conflicts=True, batch_size=BATCH_SIZE)
            created_total += len(buffer)

        state.filename = path.name
        state.byte_offset = new_offset
        state.save(update_fields=['filename', 'byte_offset', 'last_ingested'])

    return created_total


def _background_runner():
    global _ingest_running
    import django.db
    try:
        ingest_all()
    except Exception:
        pass
    finally:
        django.db.connection.close()
        with _ingest_lock:
            _ingest_running = False


def run_ingest_in_background():
    global _ingest_running
    with _ingest_lock:
        if _ingest_running:
            return False
        _ingest_running = True
    threading.Thread(target=_background_runner, daemon=True).start()
    return True
