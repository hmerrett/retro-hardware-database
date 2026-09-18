(function () {
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
      const css = CSS[`${val('colour')}|${val('yellowing')}`] || '';
      dot.style.background = css;
      // Nothing recorded, or a value from outside the chart: a hatch rather than
      // a swatch, so an empty menu does not read as a colour of its own.
      dot.classList.toggle('none', !css);
    };
    menus.forEach(m => m.addEventListener('change', paint));
    paint();
  });
})();
