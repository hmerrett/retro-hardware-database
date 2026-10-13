// The bar that says a record has changed under you. Loaded only by the pages that
// have one, and reads which record it is watching from the element itself rather
// than from a value written into the script -- which is what lets this be a file
// the browser can cache instead of markup rebuilt on every request.
(function () {
  const bar0 = document.getElementById('changed');
  if (!bar0) return;
  const AID = bar0.dataset.aid;
  const BUILT = bar0.dataset.built;
  const EVERY = 15000;
  const bar = document.getElementById('changed');
  const go = document.getElementById('changed-go');
  if (go) go.addEventListener('click', () => location.reload());

  // Anything a reload would take away from you. The lightbox, because a crop is
  // set up inside it. A control you are in the middle of using. And any box with
  // something typed in it that is not saved anywhere yet -- a note half written,
  // a search half typed -- whether or not the cursor is still in it, because
  // walking away from the keyboard is not abandoning the sentence.
  //
  // Compared against defaultValue rather than emptiness: a box the page rendered
  // with something already in it is not something you typed.
  const TYPED = 'input:not([type=hidden]):not([type=file]):not([type=radio])'
              + ':not([type=checkbox]), textarea';
  //
  // And photographs being added from the panel, or one that was not and is waiting
  // on the owner: the first to land changes the record, and a reload then would
  // take away the rest and the row saying why one failed (uploads.js).
  function busy() {
    if (document.querySelector('#lightbox[open]')) return true;
    if (document.querySelector('.uploads .up:not(.is-done)')) return true;
    const on = document.activeElement;
    if (on && /^(INPUT|TEXTAREA|SELECT)$/.test(on.tagName) && on.type !== 'hidden') {
      return true;
    }
    return [...document.querySelectorAll(TYPED)]
      .some(el => (el.value || '') !== (el.defaultValue || ''));
  }

  // Photographs still going up: the panel reloads the page itself when they are
  // all added, and asks again when one is not, so the bar would only be news of
  // the owner's own uploads.
  const UPLOADING = '.uploads .up:not(.is-done):not(.is-failed)';

  let stale = false;
  async function look() {
    if (document.visibilityState !== 'visible') return;
    if (!stale) {
      let now;
      try {
        const r = await fetch(`/items/${encodeURIComponent(AID)}/version`,
                              { cache: 'no-store' });
        if (!r.ok) return;
        now = (await r.json()).v;
      } catch (e) { return; }      // offline, or the server restarting: try later
      if (!now || now === BUILT) return;
      stale = true;                // stop asking; the answer will not change back
    }
    if (document.querySelector(UPLOADING)) return;
    if (!busy()) { location.reload(); return; }
    if (bar && bar.hidden) {
      bar.hidden = false;
      say(bar.querySelector('span').textContent);
    }
  }

  // Said as well as shown: the bar appears at the foot of the page, which is not
  // where a screen reader is (base.html, #said).
  function say(words) {
    const said = document.getElementById('said');
    if (said) said.textContent = words;
  }

  setInterval(look, EVERY);
  // The one that does the real work: back from the phone, and it has already run.
  document.addEventListener('visibilitychange', look);
  window.addEventListener('focus', look);
  // The panel's uploads have finished with one not added (uploads.js).
  document.addEventListener('rhdb:look', look);
  // And if the page went stale while you were busy, take the first moment you
  // are not -- clicking away from the box you were typing in is that moment.
  document.addEventListener('click', () => {
    if (stale && bar && !bar.hidden && !busy()) location.reload();
  });
})();
