// A second of a model already held (MANUAL §5, "A second of a model you already
// have"). A maker and model the collection already has almost always means another
// of the same machine, so the new machine's form offers to start from one: a link to
// the form again, filled in by the server from that machine, which nothing is saved
// by until Save. The part form's version of this is in part-form.js.
//
// The same model is what it is for files: the catalogue's key where one is picked,
// and otherwise the maker and model with the case and every space taken out.
(function () {
  'use strict';
  const data = document.getElementById('computer-form-data');
  const note = document.getElementById('samemake');
  const make = document.getElementById('manufacturer');
  const model = document.getElementById('model');
  if (!data || !note || !make || !model) return;
  const SAME = JSON.parse(data.textContent).same;
  const pick = document.querySelector('[data-machine-pick]');
  const fold = s => (s || '').replace(/\s+/g, '').toLowerCase();
  // The machine this form was started from is not offered back to itself.
  const from = new URLSearchParams(location.search).get('from') || '';

  function look() {
    const key = pick ? pick.value : '';
    const m = fold(make.value), d = fold(model.value);
    let hit = (key && SAME.catalogue[key]) || ((m && d) ? SAME.named[`${m}|${d}`] : '');
    if (hit && hit.toUpperCase() === from.toUpperCase()) hit = '';
    if (!hit) {
      note.hidden = true;
      note.replaceChildren();
      return;
    }
    const a = document.createElement('a');
    a.href = `/computers/new?from=${encodeURIComponent(hit)}`;
    a.textContent = `${hit} is the same model — start from it`;
    note.replaceChildren(a, ' to copy its memory, drives and the rest.');
    note.hidden = false;
  }

  make.addEventListener('input', look);
  model.addEventListener('input', look);
  // Picking a catalogue model fills the maker and model in by script (machine.js),
  // which fires no input event; and its own handler may run after this one, so the
  // look waits for it.
  if (pick) pick.addEventListener('change', () => setTimeout(look, 0));
  look();
})();
