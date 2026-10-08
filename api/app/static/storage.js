// The audit (MANUAL §14, "Audit"). The page works without this: the scan box is a form,
// and every scan is a post the server answers by redrawing the page. What this adds
// is what makes a scanner fast to use -- the box put away and the scanner listened
// for, a whole tag sent without waiting for Enter, no reload between scans, the
// question a round starts with, and a sound for each answer -- and none of it
// decides anything: what a scan did is the server's to say, and this only shows it.
(function () {
  'use strict';
  const page = document.getElementById('storage');
  const form = document.getElementById('storage-form');
  const box = document.getElementById('scan-code');
  const panel = document.getElementById('storage-panel');
  const list = document.getElementById('scan-list');
  const start = document.getElementById('storage-start');
  const prompted = document.getElementById('storage-prompt');
  const step = document.getElementById('storage-step');
  const where = document.getElementById('storage-where');
  const path = document.getElementById('storage-path');
  const ready = document.getElementById('storage-ready');
  const change = document.getElementById('storage-change');
  const typing = document.getElementById('storage-type');
  const sound = document.getElementById('storage-sound');
  if (!page || !form || !box || !panel || !list) return;
  const sendIt = form.querySelector('[type="submit"]');

  // --- what this browser remembers ------------------------------------------------
  // Wrapped: storage can be refused (a private window), and a page that stopped
  // working because it could not remember a preference would be the wrong way round.
  function recall(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function remember(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* kept for this visit */ }
  }

  // --- the sound switch -------------------------------------------------------------
  const KEY = 'rhdb.storage.sound';
  let beeping = recall(KEY) !== 'off';
  function showSound() {
    if (!sound) return;
    sound.setAttribute('aria-pressed', beeping ? 'true' : 'false');
    sound.textContent = beeping ? 'Sound on' : 'Sound off';
  }
  showSound();
  if (sound) {
    sound.addEventListener('click', function () {
      beeping = !beeping;
      remember(KEY, beeping ? 'on' : 'off');
      showSound();
      keep();
    });
  }

  // --- what a scan sounds like ---------------------------------------------------
  // Made here rather than played from a file: three tones are a few lines of Web
  // Audio, and a sound file is a request the content policy would have to allow.
  // The context is made on the first scan, because a browser will not start one
  // before somebody has done something on the page.
  let audio = null;
  function tone(freq, start, length, type) {
    const o = audio.createOscillator();
    const g = audio.createGain();
    o.type = type || 'sine';
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, audio.currentTime + start);
    g.gain.exponentialRampToValueAtTime(0.25, audio.currentTime + start + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + start + length);
    o.connect(g);
    g.connect(audio.destination);
    o.start(audio.currentTime + start);
    o.stop(audio.currentTime + start + length + 0.02);
  }
  function sounds(kind) {
    if (kind === 'refused' && navigator.vibrate) navigator.vibrate(200);
    if (!beeping) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (kind === 'refused') tone(180, 0, 0.3, 'square');
      else if (kind === 'moved') { tone(880, 0, 0.09); tone(1320, 0.11, 0.09); }
      else tone(1500, 0, 0.08);
    } catch (e) { /* no sound to be had; the panel still says it */ }
  }

  // --- the box, put away -------------------------------------------------------------
  // It stays on the page, because a scanner types into whatever has the focus, and
  // it keeps that focus without bringing up the on-screen keyboard. It is only out
  // of sight -- still read by a screen reader and still reached by Tab -- until
  // "type a tag" brings it back with the keyboard, for the one scan it is wanted for.
  function quiet(on) {
    form.classList.toggle('sr-only', on);
    if (sendIt) sendIt.hidden = on;
    if (ready) ready.hidden = !on;
    box.setAttribute('inputmode', on ? 'none' : 'text');
    if (typing) typing.setAttribute('aria-pressed', on ? 'false' : 'true');
    box.blur();
    keep();
  }
  if (typing) typing.addEventListener('click', function () {
    quiet(typing.getAttribute('aria-pressed') === 'true');
  });

  // --- the focus, which stays in the box -----------------------------------------
  // After every scan, after every button here, and when a tap lands on nothing in
  // particular. Only then -- a keyboard user tabbing to Next or Finish has put
  // the focus somewhere on purpose, and a box that snatched it back would make every
  // control after it unreachable from the keyboard. With the box out of sight the
  // ready button says which it is, and pressing it puts the focus back.
  function keep() { box.focus({ preventScroll: true }); }
  function listening() {
    if (!ready) return;
    const on = document.activeElement === box;
    ready.classList.toggle('on', on);
    ready.textContent = on ? ready.dataset.on : ready.dataset.off;
  }
  box.addEventListener('focus', listening);
  box.addEventListener('blur', function () {
    listening();
    setTimeout(function () {
      const at = document.activeElement;
      const scanner = document.getElementById('scanner');
      if (scanner && !scanner.hidden) return;
      if (document.hidden) return;
      if (!at || at === document.body) keep();
    }, 250);
  });
  if (ready) ready.addEventListener('click', keep);

  // --- the question a round starts with ---------------------------------------------
  // Asked only before the round's first scan, with last time's answer picked out.
  // Camera is answered by app.js as well, which opens it (it is a scan-open button);
  // a label scanned instead of answering is an answer too.
  const WITH = 'rhdb.storage.with';
  function chose(how) {
    remember(WITH, how);
    if (start) start.hidden = true;
    if (how === 'scanner') keep();
  }
  if (start && !page.dataset.started) {
    const last = recall(WITH) || 'scanner';
    start.querySelectorAll('[data-scan-with]').forEach(function (b) {
      b.classList.toggle('primary', b.dataset.scanWith === last);
      b.addEventListener('click', function () { chose(b.dataset.scanWith); });
    });
    start.hidden = false;
  }

  // --- the prompt and the panel, redrawn from an answer ---------------------------
  function prompt(said) {
    if (!prompted) return;
    const open = said.open;
    if (step) step.hidden = !open;
    if (where) {
      where.textContent = '';
      if (open) {
        const a = document.createElement('a');
        a.href = '/items/' + open;
        a.textContent = said.open_name || open;
        where.appendChild(a);
      } else {
        where.textContent = prompted.dataset.idleWhere;
      }
    }
    if (path) path.textContent = open ? said.open_path || '' : prompted.dataset.idlePath;
    if (change) change.hidden = !open;
  }

  // The camera covers the page, so what the panel says is said under the picture as
  // well, with what to scan next.
  function tellCamera(said) {
    const scanner = document.getElementById('scanner');
    const note = document.getElementById('scan-note');
    if (!scanner || scanner.hidden || !note) return;
    const next = said.open
      ? 'Next: scan things into ' + (said.open_name || said.open) + '.'
      : 'Next: scan a location.';
    note.textContent = said.icon + ' ' + said.head + ' — ' + said.words + ' ' + next;
  }

  function tell(said) {
    panel.className = 'storagepanel tone-' + said.tone + ' fresh';
    panel.querySelector('.ic').textContent = said.icon;
    panel.querySelector('.head').textContent = said.head;
    panel.querySelector('.words').textContent = said.words;
    // The class that flashes is taken off and put back so the same answer twice
    // flashes twice; the stylesheet only animates it for somebody who has not asked
    // for less motion.
    void panel.offsetWidth;
    sounds(said.tone);
  }

  function show(said) {
    tell(said);
    if (said.row) {
      const holder = document.createElement('ol');
      holder.innerHTML = said.row;
      const line = holder.firstElementChild;
      if (line) {
        const old = list.querySelector('[data-scan="' + line.dataset.scan + '"]');
        if (old) old.replaceWith(line); else list.prepend(line);
      }
    }
    page.dataset.started = '1';
    prompt(said);
    tellCamera(said);
  }
  // Said in the panel and nowhere else: the register did not hear it, so what is
  // open is still what the prompt says.
  function failed() {
    tell({ tone: 'refused', icon: '✕', head: 'Not sent',
           words: 'The scan did not reach the register. Scan it again.' });
  }

  function send(url, body) {
    return fetch(url, {
      method: 'POST',
      body: body,
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin',
    }).then(function (r) {
      if (!r.ok) throw new Error('refused ' + r.status);
      return r.json();
    });
  }

  // --- a scan, sent ------------------------------------------------------------------
  // A code goes the moment it is whole: the seven characters a barcode holds, or the
  // whole address a QR code holds, which every label has printed ending in a slash.
  // Waiting for that slash rather than for the tag inside it is what lets a scanner
  // that pauses between characters finish, where a scan sent at the tag would leave
  // the slash to start the next one. Anything else waits for Enter, as it always has;
  // an Enter after a code already sent arrives in an empty box and does nothing.
  const WHOLE = /^\s*(?:RH-[0-9A-Z]{4}|\S*\/items\/RH-[0-9A-Z]{4}\/)\s*$/i;
  box.addEventListener('input', function () {
    if (WHOLE.test(box.value)) form.requestSubmit();
  });

  // One at a time, in the order they were scanned: a scanner fired twice in quick
  // succession must not have its second code overtake the first, since the first
  // may be the location the second goes into.
  let queue = Promise.resolve();
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    const code = box.value;
    box.value = '';
    if (!code.trim()) { keep(); return; }
    if (start && !start.hidden) chose('scanner');
    const body = new FormData(form);
    body.set('code', code);
    queue = queue.then(function () {
      return send(form.action, body).then(show).catch(failed);
    });
    if (box.getAttribute('inputmode') === 'text') quiet(true); else keep();
  });

  if (change) change.addEventListener('submit', function (e) {
    e.preventDefault();
    queue = queue.then(function () {
      return send(change.action, new FormData(change)).then(show).catch(failed);
    });
    keep();
  });

  list.addEventListener('submit', function (e) {
    const undo = e.target.closest('form[data-undo]');
    if (!undo) return;
    e.preventDefault();
    queue = queue.then(function () {
      return send(undo.action, new FormData(undo)).then(show).catch(function () {});
    });
    keep();
  });

  // The camera's answer arrives here when this page is open (app.js): it is a scan
  // like any other, so it goes through the same form.
  document.addEventListener('rhdb:scanned', function (e) {
    box.value = e.detail;
    form.requestSubmit();
  });

  quiet(true);
})();
