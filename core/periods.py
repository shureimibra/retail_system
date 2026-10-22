"""The period picker used by Home and Reports: a few plain choices plus a safe custom range."""
from datetime import date, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date

EARLIEST = date(2020, 1, 1)
PERIODS = [
    ('all', 'All time'),
    ('today', 'Today'),
    ('7d', 'Last 7 days'),
    ('30d', 'Last 30 days'),
    ('month', 'This month'),
    ('custom', 'Custom range'),
]


def _safe_date(value, today):
    """A date between 1 Jan 2020 and today, or None. Typos like year 275760 are ignored."""
    try:
        parsed = parse_date(value or '')
    except ValueError:
        return None
    if parsed is None:
        return None
    return min(max(parsed, EARLIEST), today)


def resolve_period(params, default='all'):
    """Read ?period=…&start_date=…&end_date=… and return what the page and the queries need."""
    today = timezone.localdate()
    key = params.get('period') or ('custom' if params.get('start_date') or params.get('end_date') else default)
    if key not in dict(PERIODS):
        key = default
    start = end = None
    if key == 'today':
        start = end = today
    elif key == '7d':
        start, end = today - timedelta(days=6), today
    elif key == '30d':
        start, end = today - timedelta(days=29), today
    elif key == 'month':
        start, end = today.replace(day=1), today
    elif key == 'custom':
        start, end = _safe_date(params.get('start_date'), today), _safe_date(params.get('end_date'), today)
        if start and end and start > end:
            start, end = end, start
        if not start and not end:
            key = 'all'
    return {
        'key': key,
        'label': dict(PERIODS)[key],
        'start': start,
        'end': end,
        'start_str': start.isoformat() if start else '',
        'end_str': end.isoformat() if end else '',
        'choices': PERIODS,
        'min': EARLIEST.isoformat(),
        'max': today.isoformat(),
    }
