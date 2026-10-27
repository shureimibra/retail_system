/* Records saved on this phone while offline, waiting to be sent. Used by the page and by sw.js. */
(function (scope) {
  var NAME = 'retail-os-offline', STORE = 'queue', KEEP_DAYS = 7;

  function open() {
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open(NAME, 1);
      request.onupgradeneeded = function () { request.result.createObjectStore(STORE, { keyPath: 'client_ref' }); };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }

  function run(mode, work) {
    return open().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, mode), result;
        Promise.resolve(work(tx.objectStore(STORE))).then(function (r) { result = r; });
        tx.oncomplete = function () { db.close(); resolve(result); };
        tx.onerror = function () { db.close(); reject(tx.error); };
      });
    });
  }

  function request(r) {
    return new Promise(function (resolve, reject) { r.onsuccess = function () { resolve(r.result); }; r.onerror = function () { reject(r.error); }; });
  }

  function newRef() {
    if (scope.crypto && scope.crypto.randomUUID) return scope.crypto.randomUUID();
    return 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  scope.OfflineQueue = {
    newRef: newRef,
    add: function (record) { return run('readwrite', function (s) { return request(s.put(record)); }); },
    get: function (ref) { return run('readonly', function (s) { return request(s.get(ref)); }); },
    remove: function (ref) { return run('readwrite', function (s) { return request(s.delete(ref)); }); },
    all: function () {
      // Never keep customer numbers on the phone for long: anything older than a week is dropped.
      var cutoff = Date.now() - KEEP_DAYS * 24 * 3600 * 1000;
      return run('readwrite', function (s) {
        return request(s.getAll()).then(function (rows) {
          return rows.filter(function (row) {
            if (Date.parse(row.logged_at) < cutoff) { s.delete(row.client_ref); return false; }
            return true;
          }).sort(function (a, b) { return a.logged_at < b.logged_at ? -1 : 1; });  // the order they were typed
        });
      });
    },
    clear: function () { return run('readwrite', function (s) { return request(s.clear()); }); },
    // A record from the fields of a Log missed sale form.
    fromFields: function (fields) {
      var ref = fields.client_ref || newRef();
      delete fields.csrfmiddlewaretoken;
      fields.client_ref = ref;
      fields.logged_at = fields.logged_at || new Date().toISOString();
      return { client_ref: ref, logged_at: fields.logged_at, logged_by: fields.logged_by || '',
               logged_by_name: fields.logged_by_name || '', kind: fields.action === 'bought' ? 'bought' : 'missed',
               fields: fields, status: 'waiting', problems: [] };
    }
  };
})(typeof self !== 'undefined' ? self : window);
