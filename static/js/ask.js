/* The Ask panel: opens from the top bar, answers questions about the shop from its own records. */
(function () {
  var panel = document.getElementById('askPanel'), opener = document.querySelector('[data-ask-open]');
  if (!panel || !opener) return;
  var scrim = document.querySelector('[data-ask-scrim]'), thread = panel.querySelector('[data-ask-thread]');
  var examples = panel.querySelector('[data-ask-examples]'), form = panel.querySelector('[data-ask-form]');
  var input = form.querySelector('input[name=q]'), url = panel.dataset.askUrl, loaded = false, busy = false;

  function open() {
    panel.hidden = false; scrim.hidden = false; opener.setAttribute('aria-expanded', 'true');
    document.body.classList.add('ask-is-open');
    input.focus();
    if (!loaded) {
      loaded = true;
      fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.text() : ''; })
        .then(function (html) { examples.innerHTML = html; }).catch(function () { loaded = false; });
    }
  }
  function close() {
    panel.hidden = true; scrim.hidden = true; opener.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('ask-is-open');
    opener.focus();
  }
  var queue = [];
  function ask(question) {
    question = (question || '').trim();
    if (!question) return;
    if (busy) { queue.push(question); input.value = ''; return; }  // asked while an answer is loading: next in line
    busy = true;
    var data = new FormData(form);
    data.set('q', question);
    input.value = '';
    fetch(url, { method: 'POST', body: data, credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : '<p class="ask-a">Something went wrong. Try again.</p>'; })
      .catch(function () { return '<p class="ask-a">No connection. Ask again when you\'re back online.</p>'; })
      .then(function (html) {
        thread.insertAdjacentHTML('beforeend', html);
        thread.scrollTop = thread.scrollHeight;
        busy = false; input.focus();
        if (queue.length) ask(queue.shift());
      });
  }

  opener.addEventListener('click', open);
  panel.querySelector('[data-ask-close]').addEventListener('click', close);
  scrim.addEventListener('click', close);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) close(); });
  form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); });
  panel.addEventListener('click', function (e) {
    var chip = e.target.closest('[data-ask]');
    if (chip) ask(chip.dataset.ask);
  });
})();
