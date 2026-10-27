"""Install on the phone's home screen, and keep Log missed sale working without internet (see templates/offline/sw.js)."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse

STATIC_FILES = ['css/app.css', 'js/offline-db.js', 'js/offline.js', 'icons/favicon.svg', 'icons/app-192.png',
                'fonts/ibm-plex-sans-latin-400-normal.woff2', 'fonts/ibm-plex-sans-latin-500-normal.woff2',
                'fonts/ibm-plex-sans-latin-600-normal.woff2']


@lru_cache(maxsize=1)
def _version():
    """Changes whenever the offline helper, styles or scripts change, so phones pick up the new copy."""
    digest = hashlib.sha256()
    root = Path(settings.BASE_DIR)
    for path in [root / 'templates/offline/sw.js'] + [root / 'static' / name for name in STATIC_FILES]:
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def service_worker(request):
    body = render_to_string('offline/sw.js', {
        'version': _version(),
        'floor_url': reverse('floor'),
        'static_url': settings.STATIC_URL if settings.STATIC_URL.startswith('/') else '/' + settings.STATIC_URL,
        'db_js': static('js/offline-db.js'),
        'essentials': json.dumps([static(name) for name in STATIC_FILES]),
    })
    response = HttpResponse(body, content_type='application/javascript; charset=utf-8')
    response['Cache-Control'] = 'no-cache'
    response['Service-Worker-Allowed'] = '/'
    return response


def manifest(request):
    shop = getattr(request, 'shop', None)
    name = shop.name if shop else 'Retail OS'
    return JsonResponse({
        'name': name,
        'short_name': name[:12],
        'start_url': reverse('dashboard:home'),
        'scope': '/',
        'display': 'standalone',
        'background_color': '#121614',
        'theme_color': '#0B6670',
        'icons': [{'src': static('icons/app-192.png'), 'sizes': '192x192', 'type': 'image/png'},
                  {'src': static('icons/app-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any maskable'}],
    }, content_type='application/manifest+json')
