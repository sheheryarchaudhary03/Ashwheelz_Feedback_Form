// Customer feedback form. Questions come from the server (/api/form), so
// they are changed in the database, not in this file.
(function () {
  'use strict';

  var STAR_WORDS = ['', 'Very poor', 'Poor', 'Average', 'Good', 'Excellent'];
  var FORM = null;

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text != null) e.textContent = text;
    return e;
  }

  function radioGroup(cls, name, values, labelFor) {
    var g = el('div', { 'class': cls, role: 'radiogroup' });
    values.forEach(function (v, i) {
      var id = name + '_' + i;
      g.appendChild(el('input', { type: 'radio', name: name, id: id, value: String(v) }));
      var lab = labelFor(v, id);
      g.appendChild(lab);
    });
    return g;
  }

  function buildQuestion(q) {
    var card = el('fieldset', { 'class': 'card q', id: 'q_' + q.code });
    card.appendChild(el('legend', { 'class': 'sr' }, q.prompt));
    var h = el('h3', null, q.prompt);
    if (q.required) { h.appendChild(document.createTextNode(' ')); h.appendChild(el('span', { 'class': 'req' }, '*')); }
    card.appendChild(h);
    card.appendChild(q.hint ? el('p', { 'class': 'hint' }, q.hint) : el('div', { 'class': 'spacer' }));

    if (q.type === 'stars') {
      var row = el('div', { 'class': 'rate-row' });
      var stars = radioGroup('stars', q.code, [5, 4, 3, 2, 1], function (v, id) {
        return el('label', { 'for': id, title: v + ' – ' + STAR_WORDS[v], 'aria-label': v + ' star, ' + STAR_WORDS[v] }, '★');
      });
      stars.setAttribute('aria-label', q.prompt);
      row.appendChild(stars);
      row.appendChild(el('span', { 'class': 'rate-word', id: q.code + '_word' }));
      card.appendChild(row);
      if (q.detail_options.length) {
        card.appendChild(radioGroup('chips', q.code + '__detail', q.detail_options, function (v, id) {
          return el('label', { 'for': id }, v);
        }));
      }
    } else if (q.type === 'choice') {
      card.appendChild(radioGroup('chips', q.code, q.options, function (v, id) {
        return el('label', { 'for': id }, v);
      }));
    } else if (q.type === 'nps') {
      var nums = []; for (var n = 0; n <= 10; n++) nums.push(n);
      var nps = radioGroup('nps', q.code, nums, function (v, id) { return el('label', { 'for': id }, String(v)); });
      nps.setAttribute('aria-label', q.prompt);
      card.appendChild(nps);
      var ends = el('div', { 'class': 'nps-ends' });
      ends.appendChild(el('span', null, 'Not likely'));
      ends.appendChild(el('span', null, 'Very likely'));
      card.appendChild(ends);
    }

    var sg = el('label', { 'class': 'f sugg' });
    sg.appendChild(el('span', null, 'Suggestion or comment (optional)'));
    sg.appendChild(el('textarea', { id: q.code + '__sugg', rows: '2', maxlength: '2000', placeholder: 'Tell us more, or how we can improve…' }));
    card.appendChild(sg);

    card.addEventListener('change', function (ev) {
      if (ev.target.name !== q.code) return;
      card.classList.add('done');
      card.classList.remove('missing');
      var w = document.getElementById(q.code + '_word');
      if (w) w.textContent = STAR_WORDS[+ev.target.value];
    });
    return card;
  }

  function render(form) {
    FORM = form;
    document.getElementById('formTitle').textContent = form.title;
    var sel = document.getElementById('c_service');
    form.services.forEach(function (s) { sel.appendChild(el('option', { value: String(s.id) }, s.name)); });

    var root = document.getElementById('sections');
    root.textContent = '';
    form.sections.forEach(function (sec) {
      root.appendChild(el('div', { 'class': 'section-title' }, sec.title));
      var route = el('div', { 'class': 'route' });
      sec.questions.forEach(function (q) { route.appendChild(buildQuestion(q)); });
      root.appendChild(route);
    });
    root.appendChild(el('div', { 'class': 'section-title' }, 'Anything else?'));
    var last = el('div', { 'class': 'card' });
    var lab = el('label', { 'class': 'f' }, 'Any other suggestions for Ashwheelz?');
    lab.appendChild(el('textarea', { id: 'final_sugg', rows: '4', maxlength: '4000', placeholder: 'Ideas, complaints or compliments. We read every one.' }));
    last.appendChild(lab);
    root.appendChild(last);
    document.getElementById('goBtn').disabled = false;
  }

  function picked(name) {
    var r = document.querySelector('input[name="' + name + '"]:checked');
    return r ? r.value : null;
  }
  function val(id) { return document.getElementById(id).value.trim(); }

  function collect() {
    var answers = [];
    FORM.sections.forEach(function (sec) {
      sec.questions.forEach(function (q) {
        var v = picked(q.code);
        if (v !== null && q.type !== 'choice') v = Number(v);
        var a = { question_code: q.code, value: v, detail: picked(q.code + '__detail'), suggestion: val(q.code + '__sugg') || null };
        if (a.value !== null || a.detail !== null || a.suggestion !== null) answers.push(a);
      });
    });
    return {
      customer: { name: val('c_name'), company: val('c_company') || null, phone: val('c_phone') || null, email: val('c_email') || null },
      service_type_id: val('c_service') ? Number(val('c_service')) : null,
      answers: answers,
      other_suggestions: val('final_sugg') || null,
      website: val('website') || null
    };
  }

  function validate() {
    var problems = [];
    var name = document.getElementById('c_name');
    if (!name.value.trim()) problems.push(name);
    var email = document.getElementById('c_email');
    if (email.value.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) problems.push(email);
    FORM.sections.forEach(function (sec) {
      sec.questions.forEach(function (q) {
        if (q.required && picked(q.code) === null) {
          var c = document.getElementById('q_' + q.code);
          c.classList.add('missing');
          problems.push(c);
        }
      });
    });
    return problems;
  }

  function showError(text) {
    document.getElementById('msg').textContent = text;
  }

  document.getElementById('fb').addEventListener('submit', function (e) {
    e.preventDefault();
    if (!FORM) return;
    showError('');
    var problems = validate();
    if (problems.length) {
      showError('Please add your name and an overall rating (and check your email, if you entered one).');
      problems[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (problems[0].focus) problems[0].focus({ preventScroll: true });
      return;
    }
    var btn = document.getElementById('goBtn');
    btn.disabled = true;
    btn.textContent = 'Submitting…';
    fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collect())
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        if (!res.ok) throw new Error(body.detail || 'Your feedback could not be sent. Please try again.');
        return body;
      });
    }).then(function (body) {
      document.getElementById('fb').hidden = true;
      document.getElementById('refId').textContent = body.reference;
      document.getElementById('thanks').hidden = false;
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }).catch(function (err) {
      btn.disabled = false;
      btn.textContent = 'Submit feedback';
      showError(err.message && err.message !== 'Failed to fetch' ? err.message
        : 'Your feedback could not be sent. Check your internet connection and press Submit again.');
    });
  });

  fetch('/api/form').then(function (r) {
    if (!r.ok) throw new Error();
    return r.json();
  }).then(render).catch(function () {
    document.getElementById('sections').textContent = '';
    showError('The form could not load. Please refresh the page.');
  });
})();
