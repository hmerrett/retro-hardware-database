// The gallery's toolbar is a GET form and the server does the sorting, filtering
// and paging, so what is left here is the two things a page cannot do for itself.
const form = document.getElementById('toolbar');
const sortSel = document.getElementById('sort');
const PAGE = JSON.parse(document.getElementById('index-data').textContent);

// A menu that changes redraws the page, rather than waiting for Apply -- which is
// still in the markup for a browser running no script.
form.addEventListener('change', function (e) {
  // The sort you chose, remembered for the next visit that names none. Written
  // here rather than by the server, because a link somebody sent you names a sort
  // too, and opening it is not choosing one.
  if (e.target === sortSel) window.rhdbCookie.write(PAGE.sortCookie, sortSel.value);
  if (form.requestSubmit) form.requestSubmit(); else form.submit();
});
