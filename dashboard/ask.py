"""
The Ask panel: plain questions about the shop, answered from its own data. No AI service, nothing leaves Retail OS.
It recognises a set list of questions (QUESTIONS) and the details in them (size, colour, item, customer, period).
Anything it doesn't recognise gets the list, never a guess.
"""
import re
from datetime import timedelta

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from analytics.selectors import get_to_order
from core.phones import normalize_phone
from customers.models import Customer
from intents.models import BlockedPurchaseIntent as Intent
from products.models import Product, ProductVariation
from ui.templatetags.ui import money
from . import selectors

# (key, example shown in the panel). Order matters only for display.
QUESTIONS = [
    ('order', 'What should I order?'),
    ('who_waits', "Who's waiting for size 42?"),
    ('recovered', 'How much did we recover this month?'),
    ('money_waiting', 'How much money is waiting?'),
    ('reasons', "Why aren't people buying?"),
    ('top_asked', 'Which items are asked for most?'),
    ('my_answer', "Who's waiting for my answer?"),
    ('reserved', "What's reserved?"),
    ('stock', 'How many Adidas 42 do we have?'),
    ('customer', 'Tell me about Wanjiku'),
    ('doing', 'How are we doing this week?'),
    ('link', 'What came in through the shop link?'),
]

# Words that point to each question, in English and common Swahili/Sheng. Checked in this order: the first match wins.
RULES = [
    ('my_answer', r'my (answer|reply)|waiting for (an? )?(answer|reply)|unanswered|not answered|haven.?t (answered|replied)|wanangoja jibu|jibu'),
    ('link', r'shop link|the link|\blink\b|\bqr\b'),
    ('reserved', r'reserv|pick ?up|deposit|collect|amana'),
    ('order', r'\border\b|\bto buy\b|what (should|do) (i|we) buy|restock|nunua|agiza'),
    ('recovered', r'recover|got back|earned|made (money)?|paid in full|tumepata'),
    ('money_waiting', r'(money|how much|value|pesa).*(waiting|wait|pending|inangoja)'),
    ('reasons', r'\bwhy\b|reason|not buy|don.?t buy|aren.?t buy|hawanunui|sababu'),
    ('top_asked', r'\bmost\b|popular|top (items|sizes)|asked for|wanauliza'),
    ('doing', r'how are we doing|how is (the )?(shop|business)|doing|summary|performance|tunaendeleaje'),
    ('stock', r'how many|in stock|do we have|\bstock\b|ngapi|tuko na'),
    ('who_waits', r'\bwho\b.*(wait|want|ask)|waiting for|wants|wanangoja|anataka|wanataka'),
    ('customer', r'tell me about|about |customer|\bwho is\b|ni nani'),
]

PERIOD_WORDS = [
    (r'\btoday\b|\bleo\b', 'today'),
    (r'\byesterday\b|\bjana\b', 'yesterday'),
    (r'last week|wiki iliyopita', 'last_week'),
    (r'this week|wiki hii|\bweek\b', 'this_week'),
    (r'last month|mwezi uliopita', 'last_month'),
    (r'this month|mwezi huu|\bmonth\b', 'this_month'),
]


def period_for(text, default):
    today = timezone.localdate()
    key = next((k for pattern, k in PERIOD_WORDS if re.search(pattern, text)), default)
    monday = today - timedelta(days=today.weekday())
    first = today.replace(day=1)
    last_month_end = first - timedelta(days=1)
    spans = {
        'today': (today, today, 'today'),
        'yesterday': (today - timedelta(days=1), today - timedelta(days=1), 'yesterday'),
        'this_week': (monday, today, 'this week'),
        'last_week': (monday - timedelta(days=7), monday - timedelta(days=1), 'last week'),
        'this_month': (first, today, 'this month'),
        'last_month': (last_month_end.replace(day=1), last_month_end, 'last month'),
    }
    start, end, label = spans[key]
    return {'start': start, 'end': end, 'label': label}


def _words(text):
    return set(re.findall(r'[a-z0-9]+', text))


def find_products(shop, text):
    """Items named in the question: whole words from the item's name (e.g. "adidas", "ultraboost")."""
    words = _words(text)
    scored = []
    for product in Product.objects.filter(shop=shop):
        name_words = {w for w in _words(product.name.lower()) if len(w) >= 3}
        hits = len(name_words & words)
        if hits:
            scored.append((hits, product))
    if not scored:
        return []
    best = max(h for h, _ in scored)
    return [p for h, p in scored if h == best]


def find_options(shop, text):
    """Sizes and colours named in the question, as the shop spells them."""
    words = _words(text)
    values = set()
    for o1, o2 in ProductVariation.objects.filter(product__shop=shop).values_list('option1', 'option2'):
        for value in (o1, o2):
            if value and value.lower() in words and (value.isdigit() or len(value) >= 2):
                values.add(value.lower())
    return values


def find_customers(shop, text):
    digits = re.search(r'\+?\d[\d ]{7,}\d', text)
    if digits:
        number = normalize_phone(digits.group(), shop.phone_region)
        return list(Customer.objects.filter(shop=shop, phone_number=number)) if number else []
    words = {w for w in _words(text) if len(w) >= 3} - {'tell', 'about', 'customer', 'who', 'the', 'nani'}
    if not words:
        return []
    match = Q()
    for word in words:
        match |= Q(first_name__iexact=word) | Q(last_name__iexact=word)
    return list(Customer.objects.filter(shop=shop).filter(match)[:5])


def _matches(variation, options):
    labels = {(variation.option1 or '').lower(), (variation.option2 or '').lower()}
    return options <= labels


def _waited(today, created_at):
    days = (today - timezone.localdate(created_at)).days
    return 'since today' if days == 0 else f'waiting {days} day{"s" if days != 1 else ""}'


def _line(text, sub='', url=''):
    return {'text': text, 'sub': sub, 'url': url}


def answer(shop, question):
    """{'understood', 'title', 'lines': [{'text', 'sub', 'url'}], 'more': {'label', 'url'} or None, 'empty'}."""
    text = ' '.join(question.lower().split())[:300]
    key = next((k for k, pattern in RULES if re.search(pattern, text)), None)
    if key is None and find_customers(shop, text) and not find_products(shop, text):
        key = 'customer'
    if key is None:
        return {'understood': False, 'title': "I can't answer that one yet. I can answer these:",
                'lines': [], 'more': None, 'empty': '', 'examples': [q for _, q in QUESTIONS]}
    return {'understood': True, 'more': None, 'empty': '', **ANSWERS[key](shop, text)}


def _order(shop, text):
    rows = [r for r in get_to_order(shop) if r['suggested'] > 0]
    products = find_products(shop, text)
    if products:
        rows = [r for r in rows if r['product_id'] in {p.pk for p in products}]
    lines = [_line(f"{r['product_name']} {r['variation_label']}: order {r['suggested']}", r['why'],
                   reverse('intents:to_order')) for r in rows[:8]]
    return {'title': f'Order these ({len(rows)} item{"s" if len(rows) != 1 else ""})' if rows else '',
            'lines': lines, 'empty': 'Nothing to order: no one is waiting for anything that isn\'t in stock.',
            'more': {'label': 'Open To order', 'url': reverse('intents:to_order')}}


def _who_waits(shop, text):
    qs = (Intent.objects.filter(shop=shop).exclude(status__in=Intent.CLOSED_STATUSES)
          .select_related('customer', 'product', 'variation').order_by('created_at'))
    products, options = find_products(shop, text), find_options(shop, text)
    if products:
        qs = qs.filter(product__in=products)
    rows = [i for i in qs if not options or (i.variation and _matches(i.variation, options))]
    what = ' '.join(filter(None, [', '.join(p.name for p in products) if products else '',
                                  ('size/colour ' + ' '.join(sorted(options))) if options else '']))
    today = timezone.localdate()
    lines = [_line(f'{i.customer.first_name or i.customer.phone_number}: {i.product.name}'
                   f'{" " + i.variation.label if i.variation else ""}',
                   f'{i.get_status_display()} · {_waited(today, i.created_at)}',
                   reverse('intents:update', args=[i.pk])) for i in rows[:10]]
    return {'title': f'{len(rows)} waiting{" for " + what if what else ""}' if rows else '',
            'lines': lines, 'empty': f'No one is waiting{" for " + what if what else ""}.',
            'more': {'label': 'Open Waiting', 'url': reverse('intents:list')}}


def _recovered(shop, text):
    period = period_for(text, 'this_month')
    money_now, count = selectors.recovered_in(shop, period['start'], period['end'])
    length = (period['end'] - period['start']).days + 1
    before, _ = selectors.recovered_in(shop, period['start'] - timedelta(days=length), period['start'] - timedelta(days=1))
    sub = f'Before that: {money(before, shop)}' if before else ''
    return {'title': f'{money(money_now, shop)} recovered {period["label"]}',
            'lines': [_line(f'{count} sale{"s" if count != 1 else ""} paid in full', sub)],
            'more': {'label': 'Open Reports', 'url': reverse('reports:index')}}


def _money_waiting(shop, text):
    numbers = selectors.key_numbers(shop, period_for(text, 'this_month'))
    return {'title': f'{money(numbers["waiting_money"], shop)} waiting',
            'lines': [_line(f'{numbers["waiting_customers"]} customer{"s" if numbers["waiting_customers"] != 1 else ""} '
                            'waiting for something', f'{numbers["due_this_week"]} needed within a week'),
                      _line(f'{numbers["reserved"]} reserved', f'{money(numbers["deposits"], shop)} in deposits')],
            'more': {'label': 'Open Waiting', 'url': reverse('intents:list')}}


def _reasons(shop, text):
    period = period_for(text, 'this_month')
    rows = selectors.reasons(shop, period)
    return {'title': f"Why they didn't buy, {period['label']}" if rows else '',
            'lines': [_line(r['label'], f"{r['count']} · {r['percent']}%") for r in rows],
            'empty': f"No missed sales logged {period['label']}.",
            'more': {'label': 'Open Reports', 'url': reverse('reports:index')}}


def _top_asked(shop, text):
    period = period_for(text, 'this_month')
    qs = selectors._in_period(Intent.objects.filter(shop=shop), 'created_at', period)
    rows = (qs.values('product__name', 'variation__option1', 'variation__option2')
            .annotate(n=Count('id')).order_by('-n')[:8])
    lines = [_line(f"{r['product__name']} {' / '.join(v for v in (r['variation__option1'], r['variation__option2']) if v)}".strip(),
                   f"asked {r['n']} time{'s' if r['n'] != 1 else ''}") for r in rows]
    return {'title': f"Asked for most, {period['label']}" if lines else '', 'lines': lines,
            'empty': f"No missed sales logged {period['label']}."}


def _my_answer(shop, text):
    rows = [r for r in selectors.needs_you(shop) if r['kind'] == 'reply']
    return {'title': f'{len(rows)} waiting for your answer' if rows else '',
            'lines': [_line(r['title'].replace(' is waiting for your answer', ''), r['sub'], r['url']) for r in rows[:10]],
            'empty': 'No one is waiting for an answer.',
            'more': {'label': 'Open Conversations', 'url': reverse('notifications:list')}}


def _reserved(shop, text):
    today = timezone.localdate()
    rows = list(Intent.objects.filter(shop=shop, status=Intent.RESERVED).select_related('customer', 'product', 'variation')
                .order_by('pickup_by'))
    lines = []
    for i in rows[:10]:
        when = ''
        if i.pickup_by:
            when = f'pickup overdue since {i.pickup_by:%a %d %b}' if i.pickup_by < today else f'pickup by {i.pickup_by:%a %d %b}'
        lines.append(_line(f'{i.customer.first_name or i.customer.phone_number}: {i.product.name}'
                           f'{" " + i.variation.label if i.variation else ""}',
                           ' · '.join(filter(None, [when, f'balance {money(i.balance, shop)}'])),
                           reverse('intents:update', args=[i.pk])))
    return {'title': f'{len(rows)} reserved' if rows else '', 'lines': lines, 'empty': 'Nothing is reserved.'}


def _stock(shop, text):
    products, options = find_products(shop, text), find_options(shop, text)
    if not products:
        return {'title': 'Which item? For example: "How many Adidas 42 do we have?"', 'lines': []}
    variations = ProductVariation.objects.filter(product__in=products).select_related('product').prefetch_related('holds')
    rows = [v for v in variations if not options or _matches(v, options)]
    lines = [_line(f'{v.product.name} {v.label}: {v.available_quantity} free',
                   f'{v.stock_quantity} in the shop · {v.held_quantity} put aside for customers',
                   reverse('products:detail', args=[v.product_id])) for v in rows[:12]]
    return {'title': '', 'lines': lines, 'empty': 'That size or colour isn\'t listed for this item.',
            'more': {'label': f'Open {products[0].name}', 'url': reverse('products:detail', args=[products[0].pk])}}


def _customer(shop, text):
    customers = find_customers(shop, text)
    if not customers:
        return {'title': 'Which customer? Give a first name or a phone number.', 'lines': []}
    customer = customers[0]
    open_items = customer.intents.exclude(status__in=Intent.CLOSED_STATUSES).select_related('product', 'variation')
    lines = [_line(f'{i.product.name}{" " + i.variation.label if i.variation else ""}', i.get_status_display(),
                   reverse('intents:update', args=[i.pk])) for i in open_items]
    conversation = customer.conversations.first()
    last = conversation.messages.order_by('-created_at').first() if conversation else None
    if last:
        lines.append(_line(f'Last message: {last.body[:100]}', f'{last.get_direction_display()} · {last.created_at:%d %b %H:%M}',
                           reverse('notifications:conversation', args=[conversation.pk])))
    others = f' ({len(customers) - 1} more with that name)' if len(customers) > 1 else ''
    return {'title': f'{customer.first_name} {customer.last_name}'.strip() + f' · {customer.phone_number}{others}',
            'lines': lines, 'empty': 'Nothing open for this customer.',
            'more': {'label': 'Open customer', 'url': reverse('customers:detail', args=[customer.pk])}}


def _doing(shop, text):
    period = period_for(text, 'this_week')
    numbers = selectors.key_numbers(shop, period)
    conversion = selectors.conversion(shop, period)
    change = numbers['recovered_change']
    return {'title': f'{period["label"].capitalize()}',
            'lines': [_line(f'{money(numbers["recovered_money"], shop)} recovered',
                            f'{"+" if (change or 0) >= 0 else ""}{change}% on the period before' if change is not None else ''),
                      _line(f'{money(numbers["waiting_money"], shop)} waiting',
                            f'{numbers["waiting_customers"]} customers'),
                      _line(f'Walk-in conversion {conversion["percent"]}%' if conversion['enough']
                            else 'Walk-in conversion: not enough visits logged yet',
                            f'{conversion["bought"]} of {conversion["total"]} visits bought')],
            'more': {'label': 'Open Reports', 'url': reverse('reports:index')}}


def _link(shop, text):
    period = period_for(text, 'this_month')
    qs = selectors._in_period(Intent.objects.filter(shop=shop, source=Intent.FROM_LINK), 'created_at', period)
    rows = list(qs.select_related('customer', 'product', 'variation').order_by('-created_at'))
    lines = [_line(f'{i.customer.first_name or i.customer.phone_number}: {i.product.name}'
                   f'{" " + i.variation.label if i.variation else ""}', i.get_status_display(),
                   reverse('intents:update', args=[i.pk])) for i in rows[:10]]
    return {'title': f'{len(rows)} through the shop link, {period["label"]}' if rows else '', 'lines': lines,
            'empty': f'No requests through the shop link {period["label"]}.'}


ANSWERS = {'order': _order, 'who_waits': _who_waits, 'recovered': _recovered, 'money_waiting': _money_waiting,
           'reasons': _reasons, 'top_asked': _top_asked, 'my_answer': _my_answer, 'reserved': _reserved,
           'stock': _stock, 'customer': _customer, 'doing': _doing, 'link': _link}


def examples(shop):
    """Four questions to tap, starting with what matters right now."""
    picks = []
    if any(r['kind'] == 'reply' for r in selectors.needs_you(shop)):
        picks.append("Who's waiting for my answer?")
    if any(r['suggested'] > 0 for r in get_to_order(shop)):
        picks.append('What should I order?')
    picks += ['How are we doing this week?', "Why aren't people buying?", 'Which items are asked for most?']
    return picks[:4]
