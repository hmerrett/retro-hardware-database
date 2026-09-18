(function () {
  // The swatch classes, mixed once in Python and generated into /style/data.css;
  // this only picks which of them the dot is wearing.
  const CSS = JSON.parse(
    document.getElementById('colours-data').textContent).swatches;
  document.querySelectorAll('.bezel-cell').forEach(cell => {
    const dot = cell.querySelector('.swatch');
    const menus = cell.querySelectorAll('select[data-bezel]');
    const val = part => {
      const el = [...menus].find(m => m.dataset.bezel === part);
      return el ? el.value : '';
    };
    const paint = () => {
      const cls = CSS[`${val('colour')}|${val('yellowing')}`] || '';
      // Nothing recorded, or a value from outside the chart: a hatch rather than
      // a swatch, so an empty menu does not read as a colour of its own.
      dot.className = cls ? `swatch ${cls}` : 'swatch none';
    };
    menus.forEach(m => m.addEventListener('change', paint));
    paint();
  });
})();
