/* Log missed sale without internet: keep records on the phone, send them when back online. See docs/phases/phase-5b-design-note.md. */
(function () {
  var body = document.body;
  if (!body.dataset.user || !window.indexedDB || !window.OfflineQueue) return;
  var Q = window.OfflineQueue, sending = false;
  var tokenUrl = body.dataset.tokenUrl, syncUrl = body.dataset.syncUrl, floorUrl = body.dataset.floorUrl;

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register(body.dataset.swUrl, { scope: '/' }).catch(function () {});
  }

  // Every save gets an id made on this phone, so the server keeps it once however often it arrives.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches('[data-floor-form]')) return;
    set(form, 'client_ref', Q.newRef());
    set(form, 'logged_at', new Date().toISOString());
    set(form, 'logged_by', body.dataset.user);
    set(form, 'logged_by_name', body.dataset.userName || '');
  }, true);

  function set(form, name, value) {
    var input = form.querySelector('input[name="' + name + '"]');
    if (!input) { input = document.createElement('input'); input.type = 'hidden'; input.name = name; form.appendChild(input); }
    input.value = value;
  }

  // --- Status: the bar on Log missed sale and the badge in the top bar -------
  var bar = document.querySelector('[data-offline-bar]'), badges = document.querySelectorAll('[data-offline-badge]');
  var failedList = document.querySelector('[data-offline-failed]');

  function show(state) {
    Q.all().then(function (rows) {
      var waiting = rows.filter(function (r) { return r.status !== 'failed'; }), failed = rows.filter(function (r) { return r.status === 'failed'; });
      var n = waiting.length, text = '', tone = '';
      if (!navigator.onLine) {
        text = 'Offline: saving on this phone.' + (body.dataset.stockAt ? ' Stock as of ' + body.dataset.stockAt + '.' : '');
        tone = 'warn';
        if (n) text += ' ' + n + ' not sent yet.';
      } else if (state === 'signin' && n) {
        text = 'Sign in to send ' + n + ' record' + (n === 1 ? '' : 's') + ' saved on this phone.'; tone = 'warn';
      } else if (sending && n) {
        text = 'Sending ' + n + '…';
      } else if (n) {
        text = n + ' not sent yet. They send when the connection is back.'; tone = 'warn';
      } else if (state === 'sent') {
        text = 'All sent.'; tone = 'ok';
        var saved = document.querySelector('[data-offline-saved]');
        if (saved) saved.hidden = true;
      }
      if (bar) { bar.textContent = text; bar.hidden = !text; bar.dataset.tone = tone; }
      badges.forEach(function (b) { b.hidden = !n; b.textContent = n + ' not sent yet'; });
      if (failedList) renderFailed(failed);
    }).catch(function () {});
  }

  function renderFailed(rows) {
    failedList.hidden = !rows.length;
    if (!rows.length) return;
    failedList.innerHTML = '<b>' + rows.length + ' saved offline couldn\'t be added.</b> Log ' + (rows.length === 1 ? 'it' : 'them') + ' again:';
    var list = document.createElement('ul');
    rows.forEach(function (row) {
      var li = document.createElement('li'), remove = document.createElement('button');
      li.textContent = (row.fields.phone || 'No number') + ': ' + (row.problems || []).join(' ') + ' ';
      remove.type = 'button'; remove.className = 'btn btn-plain btn-sm'; remove.textContent = 'Remove';
      remove.addEventListener('click', function () { Q.remove(row.client_ref).then(show); });
      li.appendChild(remove); list.appendChild(li);
    });
    failedList.appendChild(list);
  }

  // --- Sending -------------------------------------------------------------
  function send() {
    if (sending || !navigator.onLine) return show();
    Q.all().then(function (rows) {
      rows = rows.filter(function (r) { return r.status !== 'failed'; });
      if (!rows.length) return show();
      sending = true; show();
      return fetch(tokenUrl, { credentials: 'same-origin', cache: 'no-store' }).then(function (r) {
        if (r.status === 401) throw new Error('signin');
        return r.json();
      }).then(function (me) {
        return rows.reduce(function (chain, row) {
          return chain.then(function () { return sendOne(row, me.token); });
        }, Promise.resolve());
      }).then(function () { sending = false; show('sent'); })
        .catch(function (error) { sending = false; show(error.message === 'signin' ? 'signin' : ''); });
    });
  }

  function sendOne(row, token) {
    return fetch(syncUrl, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ kind: row.kind, fields: row.fields })
    }).then(function (r) {
      if (r.status === 401) throw new Error('signin');
      if (r.status >= 500 || r.status === 403) throw new Error('later');
      return r.json();
    }).then(function (answer) {
      if (answer.status === 'saved' || answer.status === 'already') return Q.remove(row.client_ref);
      row.status = 'failed'; row.problems = answer.problems || [];
      return Q.add(row);
    });
  }

  window.addEventListener('online', send);
  window.addEventListener('offline', function () { show(); });
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') send(); });
  setInterval(function () { if (navigator.onLine) send(); }, 60000);

  // --- Log missed sale after a save that stayed on the phone -----------------
  var params = new URLSearchParams(location.search);
  var note = document.querySelector('[data-offline-saved]');
  if (note && params.get('queued')) {
    note.hidden = false;
    note.textContent = params.get('queued') === 'bought' ? 'Sale counted on this phone. It sends when you\'re back online.'
      : 'Saved on this phone. It sends when you\'re back online.';
  }
  var another = params.get('another'), capture = document.getElementById('capture');
  if (another && capture) {
    Q.get(another).then(function (row) {
      if (!row) return;
      ['phone', 'name', 'email'].forEach(function (k) { var i = capture.querySelector('[name=' + k + ']'); if (i) i.value = row.fields[k] || ''; });
      set(capture, 'visit_ref', row.fields.visit_ref || row.client_ref);
    });
  }

  // --- Sign out: warn about records not sent yet, then wipe them from the phone ---
  document.querySelectorAll('form[data-sign-out]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.confirmed) return;
      e.preventDefault();
      Q.all().then(function (rows) {
        if (rows.length && !confirm(rows.length + ' record' + (rows.length === 1 ? '' : 's') + ' saved on this phone ' +
            (rows.length === 1 ? 'hasn\'t' : 'haven\'t') + ' been sent. Signing out deletes ' + (rows.length === 1 ? 'it' : 'them') + '. Sign out anyway?')) return;
        return Q.clear().then(function () {
          if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage('signed-out');
          form.dataset.confirmed = '1';
          form.submit();
        });
      }).catch(function () { form.dataset.confirmed = '1'; form.submit(); });
    });
  });

  send();
})();
