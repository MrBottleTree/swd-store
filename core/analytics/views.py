import json
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from core.models import PageView, Item, Person, Reaction, Feedback

from .ingest import run_ingest_in_background

RANGE_DAYS = {'7d': 7, '30d': 30, '90d': 90, 'all': 3650}

CAMPUS_LABELS = {
    'GOA': 'Goa',
    'HYD': 'Hyderabad',
    'PIL': 'Pilani',
    'DUB': 'Dubai',
    'OTH': 'Others',
    'GMAIL': 'Gmail',
    '': 'Anonymous',
}


def _bucket_status(code):
    if 200 <= code < 300:
        return '2xx'
    if 300 <= code < 400:
        return '3xx'
    if 400 <= code < 500:
        return '4xx'
    if 500 <= code < 600:
        return '5xx'
    return 'other'


def _top_dimension(qs, field, limit=8):
    rows = (
        qs.exclude(**{field: ''})
        .values(field)
        .annotate(c=Count('id'))
        .order_by('-c')[:limit]
    )
    return {
        'labels': [r[field] or '—' for r in rows],
        'data': [r['c'] for r in rows],
    }


def _unique_users_by_day(qs):
    rows = (
        qs.exclude(email='')
        .annotate(day=TruncDate('timestamp'))
        .values('day', 'email')
        .distinct()
    )
    by_day = {}
    for r in rows:
        by_day[r['day']] = by_day.get(r['day'], 0) + 1
    return by_day


@staff_member_required
def analytics_view(request):
    run_ingest_in_background()

    range_key = request.GET.get('range', '30d')
    if range_key not in RANGE_DAYS:
        range_key = '30d'
    days = RANGE_DAYS[range_key]
    now = timezone.now()
    since = now - timedelta(days=days)

    base_qs = PageView.objects.filter(timestamp__gte=since)

    total_views = base_qs.count()
    unique_emails = base_qs.exclude(email='').values('email').distinct().count()
    unique_ips = base_qs.exclude(ip='').values('ip').distinct().count()
    latest_pv = PageView.objects.order_by('-timestamp').values('timestamp').first()
    latest_ts = latest_pv['timestamp'] if latest_pv else None

    authed_filter = ~Q(email='')
    daily = (
        base_qs
        .annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(
            total=Count('id'),
            authed=Count('id', filter=authed_filter),
        )
        .order_by('day')
    )
    unique_by_day = _unique_users_by_day(base_qs)
    daily_labels, daily_total, daily_authed, daily_anon, daily_unique = [], [], [], [], []
    for row in daily:
        day = row['day']
        daily_labels.append(day.strftime('%b %d') if day else '—')
        daily_total.append(row['total'])
        daily_authed.append(row['authed'])
        daily_anon.append(row['total'] - row['authed'])
        daily_unique.append(unique_by_day.get(day, 0))

    campus_rows = base_qs.values('campus').annotate(c=Count('id')).order_by('-c')
    campus_labels = [CAMPUS_LABELS.get(r['campus'], r['campus'] or 'Anonymous') for r in campus_rows]
    campus_counts = [r['c'] for r in campus_rows]

    browser_rows = _top_dimension(base_qs, 'browser', limit=8)
    os_rows = _top_dimension(base_qs, 'os', limit=8)
    device_rows = _top_dimension(base_qs, 'device', limit=8)

    top_pages = list(
        base_qs.values('path')
        .annotate(views=Count('id'), uniques=Count('email', distinct=True))
        .order_by('-views')[:10]
    )

    top_item_rows = list(
        base_qs.filter(item_id_ref__isnull=False)
        .values('item_id_ref')
        .annotate(views=Count('id'))
        .order_by('-views')[:10]
    )
    item_ids = [r['item_id_ref'] for r in top_item_rows]
    item_map = {
        i.id: i for i in Item.objects.filter(id__in=item_ids).select_related('seller', 'category')
    }
    top_items = []
    for row in top_item_rows:
        item = item_map.get(row['item_id_ref'])
        if item:
            top_items.append({
                'id': item.id,
                'name': item.name,
                'seller': item.seller.name if item.seller_id else '—',
                'category': item.category.name if item.category_id else '—',
                'is_sold': item.is_sold,
                'views': row['views'],
            })
        else:
            top_items.append({
                'id': row['item_id_ref'],
                'name': f"(deleted #{row['item_id_ref']})",
                'seller': '—',
                'category': '—',
                'is_sold': False,
                'views': row['views'],
            })

    all_item_rows = list(
        base_qs.filter(item_id_ref__isnull=False)
        .values('item_id_ref')
        .annotate(views=Count('id'))
    )
    seller_agg = {}
    if all_item_rows:
        item_seller = dict(
            Item.objects.filter(id__in=[r['item_id_ref'] for r in all_item_rows])
            .values_list('id', 'seller__name')
        )
        for row in all_item_rows:
            name = item_seller.get(row['item_id_ref'])
            if not name:
                continue
            seller_agg[name] = seller_agg.get(name, 0) + row['views']
    top_sellers = sorted(seller_agg.items(), key=lambda x: -x[1])[:10]

    status_counts = {'2xx': 0, '3xx': 0, '4xx': 0, '5xx': 0, 'other': 0}
    for row in base_qs.values('status').annotate(c=Count('id')):
        status_counts[_bucket_status(row['status'])] += row['c']

    new_persons = Person.objects.filter(registered_at__gte=since).count()
    new_items = Item.objects.filter(added_at__gte=since).count()
    new_reactions = Reaction.objects.filter(created_at__gte=since).count()
    new_feedback = Feedback.objects.filter(added_at__gte=since).count()

    context = {
        'title': 'Analytics',
        'range_key': range_key,
        'ranges': [
            ('7d', 'Last 7 days'),
            ('30d', 'Last 30 days'),
            ('90d', 'Last 90 days'),
            ('all', 'All time'),
        ],
        'kpi': {
            'pageviews': total_views,
            'unique_emails': unique_emails,
            'unique_ips': unique_ips,
            'latest_ts': latest_ts,
            'new_persons': new_persons,
            'new_items': new_items,
            'new_reactions': new_reactions,
            'new_feedback': new_feedback,
        },
        'chart_daily': json.dumps({
            'labels': daily_labels,
            'total': daily_total,
            'authed': daily_authed,
            'anon': daily_anon,
            'unique': daily_unique,
        }),
        'chart_campus': json.dumps({
            'labels': campus_labels,
            'data': campus_counts,
        }),
        'chart_browser': json.dumps(browser_rows),
        'chart_os': json.dumps(os_rows),
        'chart_device': json.dumps(device_rows),
        'chart_status': json.dumps(status_counts),
        'top_pages': top_pages,
        'top_items': top_items,
        'top_sellers': top_sellers,
    }
    return render(request, 'admin/analytics.html', context)


@staff_member_required
def analytics_recent_json(request):
    rows = list(
        PageView.objects.order_by('-timestamp').values(
            'timestamp', 'method', 'path', 'status', 'name', 'email', 'campus', 'ip'
        )[:50]
    )
    for r in rows:
        r['timestamp'] = r['timestamp'].isoformat() if r['timestamp'] else None
        r['campus_label'] = CAMPUS_LABELS.get(r['campus'], r['campus'] or 'Anon')
    return JsonResponse({'rows': rows})
