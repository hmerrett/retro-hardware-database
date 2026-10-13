// Shuffle on Something to do today (MANUAL §12, "Something to do today"). The page works
// without this: Shuffle is a link, and following it reloads the page with another
// draw. What this adds is that only the panel changes -- the list below it stays
// where it was, and so does the place you were reading -- and that a keyboard is
// left on Shuffle, ready to press again.
(function () {
  'use strict';
  const said = document.getElementById('today-said');

  document.addEventListener('click', async (e) => {
    const go = e.target.closest('.today [data-shuffle]');
    if (!go || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const panel = go.closest('.today');
    const body = panel && panel.querySelector('.pbody');
    if (!body) return;
    e.preventDefault();
    if (panel.getAttribute('aria-busy') === 'true') return;
    panel.setAttribute('aria-busy', 'true');
    try {
      const r = await fetch(go.href, { cache: 'no-store', credentials: 'same-origin' });
      if (!r.ok) throw new Error(r.status);
      const next = new DOMParser().parseFromString(await r.text(), 'text/html')
        .querySelector('.today .pbody');
      // Nothing in hand any more -- the last one was finished in another tab, say.
      // The page has something to say about that, so let it say it.
      if (!next) throw new Error('no suggestion');
      body.replaceChildren(...next.childNodes);
      const again = body.querySelector('[data-shuffle]');
      if (again) again.focus();
      const name = body.querySelector('h4');
      if (said && name) said.textContent = name.textContent.trim();
    } catch (err) {
      // Offline, or the server restarting: the link still does what it says.
      location.href = go.href;
    } finally {
      panel.removeAttribute('aria-busy');
    }
  });
})();
