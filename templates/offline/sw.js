/* Retail OS offline helper. Only Log missed sale works offline; every other page always comes from the network. */
importScripts('{{ db_js }}');

var CACHE = 'retail-os-{{ version }}';
var FLOOR = '{{ floor_url }}';
var ESSENTIALS = {{ essentials|safe }};

self.addEventListener('install', function (event) {
  // One file failing to download must not stop the others (or the copy of Log missed sale) from being kept.
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return Promise.all(ESSENTIALS.map(function (url) { return cache.add(url).catch(function () {}); }))
      .then(function () { return keepFloorCopy(cache); });
  }).catch(function () {}).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf('retail-os-') === 0 && k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

// A clean copy of Log missed sale (no one-off messages or typed values in it) for when there's no internet.
function keepFloorCopy(cache) {
  return fetch(FLOOR, { credentials: 'same-origin' }).then(function (response) {
    if (response.ok && !response.redirected && response.headers.get('X-Offline-Copy') === 'yes') return cache.put(FLOOR, response);
  }).catch(function () {});
}

function offlinePage(url) {
  // Move to Log missed sale's own address, so its forms and links behave exactly as online.
  if (url.pathname !== FLOOR) return caches.match(FLOOR).then(function (copy) {
    return copy ? Response.redirect(FLOOR, 302) : offlinePage(new URL(FLOOR, url));
  });
  return caches.match(FLOOR).then(function (copy) {
    return copy || new Response('<!doctype html><meta name="viewport" content="width=device-width"><title>Offline</title>' +
      '<body style="font:16px system-ui;padding:24px">You\'re offline. Open Retail OS once while online, and Log missed sale will then work offline too.</body>',
      { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
  });
}

self.addEventListener('fetch', function (event) {
  var request = event.request, url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Saving on Log missed sale: straight to the server; if there's no connection, keep it on the phone.
  if (request.method === 'POST' && url.pathname === FLOOR && request.mode === 'navigate') {
    var copy = request.clone();
    event.respondWith(fetch(request).catch(function () {
      return copy.formData().then(function (form) {
        var fields = {};
        form.forEach(function (value, key) { fields[key] = value; });
        var record = OfflineQueue.fromFields(fields);
        return OfflineQueue.add(record).then(function () {
          var next = FLOOR + '?queued=' + (record.kind === 'bought' ? 'bought' : 'missed');
          if (fields.then === 'another') next += '&another=' + encodeURIComponent(record.client_ref);
          return Response.redirect(next, 303);
        });
      });
    }));
    return;
  }
  if (request.method !== 'GET') return;

  // Styles, scripts, fonts and icons: from the network, with a copy kept for offline.
  if (url.pathname.indexOf('{{ static_url }}') === 0) {
    event.respondWith(fetch(request).then(function (response) {
      if (response.ok) { var keep = response.clone(); caches.open(CACHE).then(function (c) { c.put(request, keep); }); }
      return response;
    }).catch(function () { return caches.match(request, { ignoreSearch: true }); }));
    return;
  }

  // Pages: always from the network. Without a connection, any page opens Log missed sale from the phone's copy.
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then(function (response) {
      if (url.pathname === FLOOR && response.headers.get('X-Offline-Copy') === 'yes') {
        var keep = response.clone();
        caches.open(CACHE).then(function (c) { c.put(FLOOR, keep); });
      }
      return response;
    }).catch(function () { return offlinePage(url); }));
  }
});

self.addEventListener('message', function (event) {
  if (event.data === 'signed-out') {
    event.waitUntil(caches.keys().then(function (keys) { return Promise.all(keys.map(function (k) { return caches.delete(k); })); }));
  }
});
