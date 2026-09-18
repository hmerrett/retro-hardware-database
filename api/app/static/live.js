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
  function busy() {
    if (document.querySelector('#lightbox.open')) return true;
    const on = document.activeElement;
    if (on && /^(INPUT|TEXTAREA|SELECT)$/.test(on.tagName) && on.type !== 'hidden') {
      return true;
    }
    return [...document.querySelectorAll(TYPED)]
      .some(el => (el.value || '') !== (el.defaultValue || ''));
  }

  let stale = false;
  async function look() {
    if (stale || document.visibilityState !== 'visible') return;
    let now;
    try {
      const r = await fetch(`/items/${encodeURIComponent(AID)}/version`,
                            { cache: 'no-store' });
      if (!r.ok) return;
      now = (await r.json()).v;
    } catch (e) { return; }        // offline, or the server restarting: try later
    if (!now || now === BUILT) return;
    stale = true;                  // stop asking; the answer will not change back
    if (busy()) { if (bar) bar.hidden = false; } else { location.reload(); }
  }

  setInterval(look, EVERY);
  // The one that does the real work: back from the phone, and it has already run.
  document.addEventListener('visibilitychange', look);
  window.addEventListener('focus', look);
  // And if the page went stale while you were busy, take the first moment you
  // are not -- clicking away from the box you were typing in is that moment.
  document.addEventListener('click', () => {
    if (stale && bar && !bar.hidden && !busy()) location.reload();
  });
})();
