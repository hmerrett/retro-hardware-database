(function () {
  // The swatch classes, mixed once in Python and generated into /style/data.css;
  // this only picks which of them the swatches are wearing. `levels` is the
  // ladder's order, as made first -- the same list _colours.html draws from.
  const DATA = JSON.parse(document.getElementById('colours-data').textContent);
  const CSS = DATA.swatches;
  const LEVELS = DATA.levels;
  const span = (cls) => {
    const el = document.createElement('span');
    el.className = cls;
    return el;
  };
  document.querySelectorAll('.bezel-cell').forEach(cell => {
    const menus = cell.querySelectorAll('select[data-bezel]');
    const val = part => {
      const el = [...menus].find(m => m.dataset.bezel === part);
      return el ? el.value : '';
    };
    // The same two shapes the template draws (_colours.swatches): a shade the chart
    // knows is a ladder of it at every stage with the chosen one outlined, and
    // anything else is one swatch -- hatched for nothing, or a value from outside
    // the chart, so an empty menu does not read as a colour of its own.
    const paint = () => {
      const shade = val('colour'), level = val('yellowing');
      let drawn;
      if (shade && CSS[`${shade}|`]) {
        drawn = span('ladder');
        LEVELS.forEach(lvl => {
          drawn.appendChild(span(`bezel sm ${CSS[`${shade}|${lvl}`] || 'none'}` +
                                 (lvl === level ? ' is-chosen' : '')));
        });
      } else {
        drawn = span(`bezel sm ${CSS[`|${level}`] || 'none'}`);
      }
      drawn.setAttribute('aria-hidden', 'true');
      cell.firstElementChild.replaceWith(drawn);
    };
    menus.forEach(m => m.addEventListener('change', paint));
  });
})();
