import re
from datetime import datetime
from django.utils import timezone

LINE_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) '
    r'(?P<status>\d+) (?P<method>\S+) (?P<path>\S+) \| '
    r'user="(?P<name>[^"]*)" <(?P<email>[^>]*)> id=(?P<pid>\S+) campus=(?P<campus>\S+) \| '
    r'(?P<browser>.*?) \| os=(?P<os>.*?) device=(?P<device>.*?) \| ip=(?P<ip>\S+)$'
)

ITEM_RE = re.compile(r'^/item/(\d+)')


def parse_line(raw):
    raw = raw.rstrip('\n').rstrip('\r')
    if not raw:
        return None
    m = LINE_RE.match(raw)
    if not m:
        return None
    d = m.groupdict()
    try:
        naive = datetime.strptime(d['ts'], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    ts = timezone.make_aware(naive, timezone.get_current_timezone())

    pid = d['pid']
    person_id_ref = int(pid) if pid.isdigit() else None

    email = d['email'] if d['email'] != 'anonymous' else ''
    name = d['name'] if d['name'] != '-' else ''
    campus = d['campus'] if d['campus'] != '-' else ''

    return {
        'timestamp': ts,
        'status': int(d['status']),
        'method': d['method'][:8],
        'path': d['path'][:500],
        'email': email[:254],
        'name': name[:100],
        'person_id_ref': person_id_ref,
        'campus': campus[:5],
        'browser': d['browser'].strip()[:100],
        'os': d['os'].strip()[:100],
        'device': d['device'].strip()[:100],
        'ip': d['ip'][:64],
        'item_id_ref': extract_item_id(d['path']),
    }


def extract_item_id(path):
    m = ITEM_RE.match(path)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (ValueError, TypeError):
        return None
