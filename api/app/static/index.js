const q = document.getElementById('q');
const cat = document.getElementById('cat');
const sortSel = document.getElementById('sort');
const showd = document.getElementById('showdisposed');
const grid = document.getElementById('grid');
const count = document.getElementById('count');
const empty = document.getElementById('empty');
const cards = [...grid.children];

function val(el, attr) { return el.dataset[attr] || ''; }
function asc(a, b, attr) { return val(a, attr).localeCompare(val(b, attr)); }
function desc(a, b, attr) { return val(b, attr).localeCompare(val(a, attr)); }
function byName(a, b) { return asc(a, b, 'name'); }
function hasImg(el) { return el.dataset.img === '1' ? 1 : 0; }
// An undated item sorts to the end whichever way round the dated ones go, so
// oldest-first does not open on a wall of things with no year recorded.
function blanksLast(a, b, attr) { return (val(a, attr) ? 0 : 1) - (val(b, attr) ? 0 : 1); }

// One shuffle key per card, dealt once and then held: filtering and searching call
// the sort again on every keystroke, and a shuffle that re-dealt each time would
// throw the cards up in the air while you typed. A new hand comes from choosing
// Random again, which is handled in sortCards.
function deal() { cards.forEach(el => { el._shuffle = Math.random(); }); }
deal();

// Recency sorts keep items with photos ahead of those without; the rest are
// the order they say they are, with the name settling any tie.
const SORTS = {
  // Photos first here too, for the same reason the recency sorts do it: a
  // shuffle that opens on a screenful of items nobody has photographed yet looks
  // like a broken page rather than a random one.
  random: (a, b) => hasImg(b) - hasImg(a) || a._shuffle - b._shuffle,
  updated: (a, b) => hasImg(b) - hasImg(a) || desc(a, b, 'updated'),
  added: (a, b) => hasImg(b) - hasImg(a) || desc(a, b, 'added') || desc(a, b, 'updated'),
  acquired: (a, b) => blanksLast(a, b, 'acquired') || desc(a, b, 'acquired') || byName(a, b),
  yearnew: (a, b) => blanksLast(a, b, 'year') || desc(a, b, 'year') || byName(a, b),
  yearold: (a, b) => blanksLast(a, b, 'year') || asc(a, b, 'year') || byName(a, b),
  name: byName,
  maker: (a, b) => blanksLast(a, b, 'maker') || asc(a, b, 'maker') || byName(a, b),
  cat: (a, b) => (+val(a, 'catsort')) - (+val(b, 'catsort')) || byName(a, b),
  aid: (a, b) => asc(a, b, 'aid'),
};

// What you chose last time, if you ever chose. Absent on a first visit, which is
// what leaves the menu on its first option and opens the shelf shuffled; present,
// and the page opens the way you left it. Checked against SORTS rather than
// trusted, so a stale or hand-edited cookie naming a sort that no longer exists
// falls back to the default instead of sorting by nothing.
const PAGE = JSON.parse(document.getElementById('index-data').textContent);
const saved = window.rhdbCookie.read(PAGE.sortCookie);
if (saved && SORTS[saved]) sortSel.value = saved;
// Written on the sort's own change event, not from apply(): apply() also runs on
// every keystroke in the search box, and the sort has not changed then.
sortSel.addEventListener('change', function () {
  window.rhdbCookie.write(PAGE.sortCookie, sortSel.value);
});

let lastMode = null;
function sortCards(mode) {
  // Choosing Random -- on arrival, or after being somewhere else -- deals again.
  // Staying on it while you filter does not.
  if (mode === 'random' && mode !== lastMode) deal();
  lastMode = mode;
  const arr = cards.slice();
  arr.sort(SORTS[mode] || SORTS.random);
  arr.forEach(el => grid.appendChild(el));
}
// What the server already searched for. While the box still holds it, the rows
// on the page are the server's answer -- filtering them again here would hide
// the ones that matched on a summary or a history entry, which this blob does
// not carry. Edit the box and instant filtering takes over again.
const serverQuery = PAGE.query;

function terms(value) {
  const out = [];
  value.toLowerCase().split('"').forEach((chunk, i) => {
    if (i % 2) { if (chunk.trim()) out.push(chunk.trim()); }
    else { out.push(...chunk.split(/\s+/).filter(Boolean)); }
  });
  return out;
}

function apply() {
  sortCards(sortSel.value);
  const raw = q.value.trim();
  const words = (raw === serverQuery) ? [] : terms(raw);
  const c = cat.value;
  let shown = 0;
  for (const el of cards) {
    const ok = words.every(w => el.dataset.search.includes(w))
      && (!c || el.dataset.cat === c)
      && (showd.checked || el.dataset.disposed === '0');
    el.style.display = ok ? '' : 'none';
    if (ok) shown++;
  }
  // Silent while everything is showing: the line beside the heading already
  // says how many there are, and a second figure agreeing with it is a figure
  // to read and reconcile for nothing. It speaks only when the filters are
  // holding something back, which is the only time the number is news -- and
  // it says so as a fraction, because "383 items" under "23 computers · 387
  // parts" was 383 against 410 with nothing on the page explaining the gap.
  // Bracketed rather than led by a separator: on a phone this wraps to a line
  // of its own, and a leading bullet then sits orphaned at the start of it.
  count.textContent = shown === cards.length
    ? '' : '(showing ' + shown + ' of ' + cards.length + ')';
  empty.style.display = shown ? 'none' : '';
  remember();
}

// Hand the order over to the item pages, so their prev/next buttons walk the list
// as it stands here -- this sort, this filter -- rather than plain register order.
// sessionStorage, because it describes this session's browsing and nothing else.
function remember() {
  try {
    // The grid's own children, not the `cards` array: that one keeps the order the
    // page arrived in, and sorting moves the elements rather than that list.
    const order = [...grid.children]
      .filter(el => el.style.display !== 'none')
      // The name as it reads on the card, not the lowercased sort key beside it.
      .map(el => [new URL(el.href).pathname,
                  (el.querySelector('.nm') || {}).textContent.trim()]);
    sessionStorage.setItem('rhdb-order', JSON.stringify(order));
  } catch (e) {}
}
[q, cat, sortSel, showd].forEach(el => el.addEventListener('input', apply));
apply();
