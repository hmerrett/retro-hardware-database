// One paragraph open at a time: opening a model's summary shuts whichever was
// already open, so the page never has two of them pushing the list about.
//
// Done here rather than with the `name` attribute, which is exactly this
// behaviour in HTML and needs Safari 17.2. These folds have already been
// silently broken once in an older Safari, and the failure modes are not
// equal -- without this script two summaries can be open at once, which is
// untidy; a fold that would not open at all is the feature missing.
//
// `toggle` does not bubble, so this listens in the capture phase, which still
// reaches an ancestor on the way down to the target. One listener for four
// hundred folds rather than four hundred listeners.
(function () {
  var cat = document.querySelector('.cat');
  if (!cat) return;
  cat.addEventListener('toggle', function (e) {
    var just = e.target;
    // Only ever act on an opening. Closing the others below fires this again
    // for each of them, and those arrive already shut -- which is what stops
    // it going round in circles.
    if (!just.open || !just.matches || !just.matches('details.mrow')) return;
    var open = cat.querySelectorAll('details.mrow[open]');
    for (var i = 0; i < open.length; i++) {
      if (open[i] !== just) open[i].open = false;
    }
  }, true);
})();
