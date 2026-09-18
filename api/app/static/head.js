// Runs before the page is painted, which is the whole reason it is not deferred
// with the rest: the theme has to be on the document element before anything is
// drawn, or a reader who chose dark gets a white flash on every page.
//
// It also defines the cookie helpers, because the deferred script and the page
// scripts both want them and a cookie written two slightly different ways is a
// cookie that does not stay written.
try {
  var _t = localStorage.getItem('theme');
  if (_t === 'dark' || _t === 'light') document.documentElement.dataset.theme = _t;
} catch (e) {}

// Reading and writing this site's own cookies. Shared, because the sort order on
// the gallery and the notice at the foot of the page both want them, and a cookie
// written two slightly different ways is a cookie that does not stay written.
//
// A year, because a preference that expires by the weekend is not remembered. Lax
// rather than Strict so following a link in from anywhere still opens the way you
// left it, and secure wherever the page itself arrived over HTTPS.
window.rhdbCookie = {
  read: function (name) {
    var hit = document.cookie.split('; ').find(function (row) {
      return row.indexOf(name + '=') === 0;
    });
    return hit ? decodeURIComponent(hit.slice(name.length + 1)) : '';
  },
  write: function (name, value) {
    try {
      document.cookie = name + '=' + encodeURIComponent(value)
        + ';path=/;max-age=' + (365 * 24 * 60 * 60) + ';samesite=lax'
        + (location.protocol === 'https:' ? ';secure' : '');
    } catch (e) {}
  }
};
