// Admin dashboard: sign-in, filters, results table, response drawer, Excel export.
(function () {
  'use strict';

  var state = { page: 1, pageSize: 25, total: 0, services: [], openId: null };
  var $ = function (id) { return document.getElementById(id); };
  var STATUS = { 'new': 'New', reviewed: 'Reviewed', actioned: 'Actioned', archived: 'Archived' };

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text != null) e.textContent = text;
    return e;
  }

  function api(path, opts) {
    opts = opts || {};
    opts.credentials = 'same-origin';
    opts.headers = Object.assign({ 'Accept': 'application/json' }, opts.headers || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    return fetch(path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        if (res.status === 401 && path !== '/api/admin/login') { showLogin(); }
        if (!res.ok) {
          var e = new Error(body.detail || 'Something went wrong. Please try again.');
          e.status = res.status;
          throw e;
        }
        return body;
      });
    });
  }

  function toast(text) {
    var t = $('toast');
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.hidden = true; }, 2600);
  }

  var dateFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' });
  function fmtDate(iso) { return dateFmt.format(new Date(iso)); }

  function starsNode(n) {
    var s = el('span', { 'class': 'stars-s', 'aria-label': n ? n + ' of 5 stars' : 'No rating' });
    if (!n) { s.textContent = '—'; s.className = 'subtle'; return s; }
    s.appendChild(document.createTextNode('★'.repeat(n)));
    s.appendChild(el('span', { 'class': 'off' }, '★'.repeat(5 - n)));
    return s;
  }

  // ------------------------------------------------------------ views
  function showLogin() {
    $('appView').hidden = true;
    $('loginView').hidden = false;
    closeDrawer();
    $('lu').focus();
  }

  function showApp(me) {
    $('loginView').hidden = true;
    $('appView').hidden = false;
    $('who').textContent = 'Signed in as ' + me.username;
    $('pwBanner').hidden = !me.default_password;
    api('/api/admin/meta').then(function (m) {
      state.services = m.services;
      var sel = $('fservice');
      while (sel.options.length > 1) sel.remove(1);
      m.services.forEach(function (s) { sel.appendChild(el('option', { value: String(s.id) }, s.name)); });
    });
    refresh();
  }

  // ------------------------------------------------------------ filters
  function filterParams() {
    var p = new URLSearchParams();
    var q = $('fq').value.trim();
    if (q) p.set('q', q);
    if ($('ffrom').value) p.set('date_from', $('ffrom').value);
    if ($('fto').value) p.set('date_to', $('fto').value);
    if ($('fservice').value) p.set('service_id', $('fservice').value);
    if ($('frating').value) {
      var r = $('frating').value.split('-');
      p.set('rating_min', r[0]);
      p.set('rating_max', r[1]);
    }
    if ($('fstatus').value) p.set('status', $('fstatus').value);
    return p;
  }

  var refreshSeq = 0;
  function refresh() {
    var seq = ++refreshSeq;
    var p = filterParams();
    var lp = new URLSearchParams(p);
    lp.set('page', state.page);
    lp.set('page_size', state.pageSize);
    lp.set('sort', $('sort').value);
    api('/api/admin/feedback?' + lp).then(function (d) {
      if (seq === refreshSeq) renderRows(d);
    }).catch(function (e) { if (e.status !== 401) toast(e.message); });
    api('/api/admin/stats?' + p).then(function (s) {
      if (seq === refreshSeq) renderStats(s);
    }).catch(function () {});
  }

  function renderStats(s) {
    $('kTotal').textContent = s.total.toLocaleString();
    $('kNew').textContent = s.unreviewed ? s.unreviewed + ' not reviewed yet' : 'All reviewed';
    $('kAvg').textContent = s.avg_overall == null ? '–' : s.avg_overall.toFixed(1) + ' ★';
    $('kNps').textContent = s.nps == null ? '–' : (s.nps > 0 ? '+' : '') + s.nps;
    $('kNpsN').textContent = s.nps_count ? 'from ' + s.nps_count + ' answers' : 'No answers yet';
    $('kLow').textContent = s.low_rated;
    $('kLow').classList.toggle('bad', s.low_rated > 0);

    var bars = $('bars');
    bars.textContent = '';
    s.by_question.forEach(function (q) {
      var row = el('div', { 'class': 'bar-row' });
      var t = el('div', { 'class': 't' });
      t.appendChild(el('span', null, q.prompt));
      t.appendChild(el('b', null, q.avg == null ? '–' : q.avg.toFixed(1)));
      row.appendChild(t);
      var bar = el('div', { 'class': 'bar', title: q.n + ' answers' });
      var fill = el('i', q.avg != null && q.avg < 3 ? { 'class': 'low' } : null);
      fill.style.width = q.avg == null ? '0' : (q.avg / 5 * 100) + '%';
      bar.appendChild(fill);
      row.appendChild(bar);
      bars.appendChild(row);
    });
  }

  function renderRows(d) {
    state.total = d.total;
    var tb = $('rows');
    tb.textContent = '';
    d.items.forEach(function (r) {
      var tr = el('tr', { tabindex: '0', 'data-id': r.id });
      tr.appendChild(el('td', { 'class': 'num' }, fmtDate(r.submitted_at)));
      var c = el('td');
      c.appendChild(el('div', { 'class': 'cust' }, r.customer_name));
      var sub = [r.customer_company, r.customer_phone, r.customer_email].filter(Boolean).join(' · ');
      if (sub) c.appendChild(el('div', { 'class': 'subtle' }, sub));
      tr.appendChild(c);
      tr.appendChild(el('td', null, r.service || '—'));
      var o = el('td'); o.appendChild(starsNode(r.overall_rating)); tr.appendChild(o);
      tr.appendChild(el('td', { 'class': 'num' }, r.nps_score == null ? '—' : String(r.nps_score)));
      tr.appendChild(el('td', { 'class': 'num' }, r.comment_count ? r.comment_count + ' comment' + (r.comment_count > 1 ? 's' : '') : '—'));
      var st = el('td'); st.appendChild(el('span', { 'class': 'pill ' + r.status }, STATUS[r.status])); tr.appendChild(st);
      tb.appendChild(tr);
    });
    $('empty').hidden = d.items.length > 0;
    var from = d.total ? (d.page - 1) * d.page_size + 1 : 0;
    var to = Math.min(d.total, d.page * d.page_size);
    $('pageInfo').textContent = d.total ? 'Showing ' + from + '–' + to + ' of ' + d.total.toLocaleString() : '';
    $('resultTitle').textContent = d.total === 1 ? '1 response' : d.total.toLocaleString() + ' responses';
    $('prevBtn').disabled = d.page <= 1;
    $('nextBtn').disabled = to >= d.total;
  }

  // ------------------------------------------------------------ drawer
  function openDrawer(id) {
    state.openId = id;
    $('dTitle').textContent = 'Loading…';
    $('dSub').textContent = '';
    $('dBody').textContent = '';
    $('scrim').hidden = false;
    $('drawer').hidden = false;
    $('dClose').focus();
    api('/api/admin/feedback/' + encodeURIComponent(id)).then(renderDrawer).catch(function (e) {
      $('dTitle').textContent = e.message;
    });
  }

  function closeDrawer() {
    $('scrim').hidden = true;
    $('drawer').hidden = true;
    state.openId = null;
  }

  function renderDrawer(r) {
    if (r.id !== state.openId) return;
    $('dTitle').textContent = r.customer_name;
    $('dSub').textContent = r.reference_code + ' · ' + fmtDate(r.submitted_at);
    var b = $('dBody');
    b.textContent = '';

    var stLab = el('label', { 'class': 'subtle' }, 'Status ');
    var sel = el('select', { id: 'dStatus' });
    Object.keys(STATUS).forEach(function (k) {
      var o = el('option', { value: k }, STATUS[k]);
      if (k === r.status) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener('change', function () {
      api('/api/admin/feedback/' + r.id, { method: 'PATCH', body: { status: sel.value } }).then(function () {
        toast('Marked as ' + STATUS[sel.value].toLowerCase());
        refresh();
      }).catch(function (e) { toast(e.message); });
    });
    stLab.appendChild(sel);
    b.appendChild(stLab);

    var dl = el('dl', { 'class': 'facts' });
    [['Company', r.customer_company], ['Phone', r.customer_phone], ['Email', r.customer_email],
     ['Service', r.service], ['Overall', r.overall_rating ? r.overall_rating + ' / 5' : null],
     ['Recommend', r.nps_score != null ? r.nps_score + ' / 10' : null]].forEach(function (f) {
      dl.appendChild(el('dt', null, f[0]));
      dl.appendChild(el('dd', null, f[1] || '—'));
    });
    b.appendChild(dl);

    var lastSec = null;
    r.answers.forEach(function (a) {
      if (a.section !== lastSec) { b.appendChild(el('div', { 'class': 'sec-t' }, a.section)); lastSec = a.section; }
      var has = a.rating != null || a.choice_value || a.detail_value || a.suggestion;
      var box = el('div', { 'class': 'ans' + (has ? '' : ' blank') });
      box.appendChild(el('div', { 'class': 'p' }, a.prompt));
      var v = el('div', { 'class': 'v' });
      if (a.type === 'stars' && a.rating != null) v.appendChild(starsNode(a.rating));
      else if (a.type === 'nps' && a.rating != null) v.textContent = a.rating + ' / 10';
      else if (a.choice_value) v.textContent = a.choice_value;
      else v.textContent = 'Not answered';
      if (a.detail_value) v.appendChild(document.createTextNode('  ·  ' + a.detail_value));
      box.appendChild(v);
      if (a.suggestion) box.appendChild(el('div', { 'class': 's' }, a.suggestion));
      b.appendChild(box);
    });

    if (r.other_suggestions) {
      b.appendChild(el('div', { 'class': 'sec-t' }, 'Other suggestions'));
      var o = el('div', { 'class': 'ans' });
      o.appendChild(el('div', { 'class': 's' }, r.other_suggestions));
      b.appendChild(o);
    }
  }

  // ------------------------------------------------------------ events
  $('loginForm').addEventListener('submit', function (e) {
    e.preventDefault();
    $('loginErr').textContent = '';
    var btn = $('loginBtn');
    btn.disabled = true;
    api('/api/admin/login', { method: 'POST', body: { username: $('lu').value.trim(), password: $('lp').value } })
      .then(function () {
        $('lp').value = '';
        return api('/api/admin/me');
      })
      .then(showApp)
      .catch(function (err) { $('loginErr').textContent = err.message; })
      .then(function () { btn.disabled = false; });
  });

  $('logoutBtn').addEventListener('click', function () {
    api('/api/admin/logout', { method: 'POST' }).then(showLogin, showLogin);
  });

  var searchTimer;
  $('fq').addEventListener('input', function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { state.page = 1; refresh(); }, 300);
  });
  ['ffrom', 'fto', 'fservice', 'frating', 'fstatus', 'sort'].forEach(function (id) {
    $(id).addEventListener('change', function () { state.page = 1; refresh(); });
  });
  $('filters').addEventListener('submit', function (e) { e.preventDefault(); });
  $('resetBtn').addEventListener('click', function () {
    $('filters').reset();
    state.page = 1;
    refresh();
  });
  $('prevBtn').addEventListener('click', function () { if (state.page > 1) { state.page--; refresh(); } });
  $('nextBtn').addEventListener('click', function () { state.page++; refresh(); });

  $('exportBtn').addEventListener('click', function () {
    // A normal navigation: the browser downloads the file with the session cookie attached.
    window.location.href = '/api/admin/export.xlsx?' + filterParams();
    toast('Preparing Excel file…');
  });

  $('rows').addEventListener('click', function (e) {
    var tr = e.target.closest('tr[data-id]');
    if (tr) openDrawer(tr.getAttribute('data-id'));
  });
  $('rows').addEventListener('keydown', function (e) {
    var tr = e.target.closest('tr[data-id]');
    if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openDrawer(tr.getAttribute('data-id')); }
  });
  $('dClose').addEventListener('click', closeDrawer);
  $('scrim').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !$('drawer').hidden) closeDrawer(); });

  function openPw() {
    $('pwForm').reset();
    $('pwErr').textContent = '';
    $('pwDialog').showModal();
  }
  $('pwBtn').addEventListener('click', openPw);
  $('pwBanBtn').addEventListener('click', openPw);
  $('pwCancel').addEventListener('click', function () { $('pwDialog').close(); });
  $('pwForm').addEventListener('submit', function (e) {
    e.preventDefault();
    $('pwErr').textContent = '';
    api('/api/admin/password', { method: 'POST', body: { current_password: $('pwCur').value, new_password: $('pwNew').value } })
      .then(function () {
        $('pwDialog').close();
        $('pwBanner').hidden = true;
        toast('Password changed');
      })
      .catch(function (err) { $('pwErr').textContent = err.message; });
  });

  api('/api/admin/me').then(showApp).catch(function () { showLogin(); });
})();
