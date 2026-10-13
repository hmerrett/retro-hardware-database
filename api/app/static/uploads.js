// Adding photographs from an item's Photographs panel (MANUAL §10). Loaded only
// where the owner has the panel's pickers. Without it the panel is a plain form
// with an Upload button; with it, choosing is the whole gesture, and each
// photograph goes on a request of its own with a row saying where it is.
//
// One at a time, in the order chosen. The server names a new photograph by reading
// the folder for the next free number, so two arriving together can be given the
// same name and the second silently replaces the first.
//
// XMLHttpRequest rather than fetch, because fetch says nothing about how far an
// upload has got.
(function () {
  const form = document.getElementById('photo-upload');
  const list = document.querySelector('.uploads');
  const tpl = document.getElementById('uprow');
  if (!form || !list || !tpl || !window.XMLHttpRequest || !window.FormData) return;
  const go = form.querySelector('[data-send-go]');
  if (go) go.hidden = true;

  const queue = [];
  let running = false;
  let added = 0;

  // Every picker belonging to the form, the tile's included, which sits in the
  // thumbnails and names the form with `form=`. Emptied once read, so that choosing
  // the same photograph again is a change, and nothing is left for a later post.
  for (const input of document.querySelectorAll('input[type=file][name=photos]')) {
    if (input.form !== form) continue;
    input.addEventListener('change', () => {
      const files = [...(input.files || [])];
      input.value = '';
      take(files);
    });
  }

  // The tile takes a drop as well. A convenience only: nothing depends on dragging.
  const tile = document.querySelector('[data-drop]');
  if (tile) {
    tile.addEventListener('dragover', e => {
      e.preventDefault();
      tile.classList.add('is-over');
    });
    tile.addEventListener('dragleave', () => tile.classList.remove('is-over'));
    tile.addEventListener('drop', e => {
      e.preventDefault();
      tile.classList.remove('is-over');
      take([...e.dataTransfer.files]);
    });
  }

  function take(files) {
    for (const file of files) {
      const row = tpl.content.firstElementChild.cloneNode(true);
      const job = { file: file, row: row };
      row.querySelector('.nm').textContent = file.name;
      row.querySelector('.meter').setAttribute('aria-label', file.name);
      row.querySelector('button').addEventListener('click', () => {
        queue.push(job);
        progress(job, 0);
        next();
      });
      draw(row.querySelector('canvas'), file);
      list.appendChild(row);
      progress(job, 0);
      queue.push(job);
    }
    next();
  }

  function next() {
    if (running) return;
    const job = queue.shift();
    if (!job) { finished(); return; }
    running = true;
    const xhr = new XMLHttpRequest();
    xhr.open('POST', form.action);
    // Asked for, the route answers for this one photograph in JSON. Anything else
    // that comes back -- the login page the gate redirects to, most of all -- is
    // not an answer that it was added.
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.timeout = 300000;
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) progress(job, Math.round(e.loaded / e.total * 100));
    };
    xhr.onload = () => {
      const status = xhr.status;
      const answer = json(xhr);
      if (status === 200 && answer && answer.added) { added += 1; done(job); }
      else if (status === 400 && answer && answer.reason) fail(job, answer.reason, false);
      else if (status >= 500) fail(job, 'the server did not answer', true);
      else fail(job, 'log in again, then add it', false);
    };
    // Try again is for what trying again could mend. A refusal would only be
    // refused again, so it is not offered one.
    xhr.onerror = () => fail(job, 'the connection dropped', true);
    xhr.ontimeout = () => fail(job, 'the server did not answer', true);
    xhr.onloadend = () => { running = false; next(); };
    const fd = new FormData();
    fd.append('photos', job.file, job.file.name);
    xhr.send(fd);
  }

  function json(xhr) {
    if (!/^application\/json/.test(xhr.getResponseHeader('Content-Type') || '')) return null;
    try { return JSON.parse(xhr.responseText); } catch (e) { return null; }
  }

  // Once nothing is left to send: every one added, and the page reloads to show
  // them in the panel and the line in the history. If any was not, its row stays,
  // and the page is asked to look for a change rather than reloading under it --
  // live.js counts a row not added as something a reload would take away, and
  // offers Reload instead.
  function finished() {
    if (!added) return;
    if (!list.querySelector('.up:not(.is-done)')) location.reload();
    else document.dispatchEvent(new Event('rhdb:look'));
  }

  function state(job, words, pct) {
    const st = job.row.querySelector('.st');
    st.firstElementChild.textContent = words;
    st.querySelector('.pc').textContent = pct === null ? '' : ' — ' + pct + '%';
    const meter = job.row.querySelector('.meter');
    meter.hidden = pct === null;
    if (pct !== null) {
      meter.setAttribute('aria-valuenow', String(pct));
      meter.firstElementChild.style.width = pct + '%';
    }
  }

  function progress(job, pct) {
    job.row.classList.remove('is-done', 'is-failed');
    job.row.querySelector('button').hidden = true;
    state(job, 'Uploading', pct);
  }

  function done(job) {
    job.row.classList.add('is-done');
    state(job, 'Added', null);
  }

  function fail(job, why, again) {
    job.row.classList.add('is-failed');
    job.row.querySelector('button').hidden = !again;
    state(job, 'Not added — ' + why, null);
  }

  // The picture is drawn on a canvas from the file itself. The content policy keeps
  // images to the site's own address, which a blob: URL in an <img> is not, and a
  // canvas is not an image; a row that fails keeps its picture. A kind the browser
  // cannot draw -- a HEIC, often -- keeps the plain ground.
  function draw(canvas, file) {
    if (!window.createImageBitmap) return;
    createImageBitmap(file).then(bmp => {
      const ctx = canvas.getContext('2d');
      const s = Math.max(canvas.width / bmp.width, canvas.height / bmp.height);
      const w = bmp.width * s;
      const h = bmp.height * s;
      ctx.drawImage(bmp, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
      if (bmp.close) bmp.close();
    }).catch(() => {});
  }
})();
