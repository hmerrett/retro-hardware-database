// The device half of the settings page.
//
// Nothing here reaches the server. The theme a device is reading in lives in
// localStorage, written by the ... menu's button and read before paint by
// head.js, and this says what it currently amounts to and offers to hand the
// choice back -- which is the one thing that button cannot do, since it only ever
// flips between the two (ADR-0023).
(function () {
  var box = document.getElementById('devicetheme');
  if (!box) return;
  var state = document.getElementById('theme-state');
  var clear = document.getElementById('theme-clear');
  var fallback = box.dataset.default || 'system';

  function chosen() {
    try {
      var t = localStorage.getItem('theme');
      return t === 'dark' || t === 'light' ? t : '';
    } catch (e) {
      return '';
    }
  }

  var mine = chosen();
  if (mine) {
    state.textContent =
      'This browser is set to the ' + mine + ' theme, which it was told from the ⋯ menu.';
    clear.hidden = false;
  } else if (fallback === 'system') {
    state.textContent =
      'This browser follows your system setting, which is what the site opens in. '
      + 'The ⋯ menu, on any page, chooses for this browser alone.';
  } else {
    state.textContent =
      'This browser follows the site, which opens in the ' + fallback + ' theme. '
      + 'The ⋯ menu, on any page, chooses for this browser alone.';
  }

  clear.addEventListener('click', function () {
    try {
      localStorage.removeItem('theme');
    } catch (e) {}
    // Reload rather than put the attribute back by hand: the ... button's label
    // is decided in a closure of its own when the page loads, so a theme changed
    // underneath it would leave it offering the theme you are already reading in.
    location.reload();
  });
})();
