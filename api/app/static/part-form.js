// Changing the type fetches the form again with that type's fields, on an
// existing part as on a new one. It has to: what a part is asked depends on its
// type, and the fields for the new one are not on the page to be shown. Before
// this, the menu did nothing at all on an existing part -- so retyping an old
// monitor to Display left the free-text box on screen and no way to reach the
// groups that had replaced it.
//
// The path is whatever is already in the address bar, so the same handler serves
// the new form, the edit form, and the new form started from another part -- and
// whatever else is in the query (computer_id, parent_id, from) rides along.
// What the server knew when it rendered this form: the storage kinds that fold
// into a machine's drives row, whether this form routes to a machine at all, the
// floppy and optical vocabularies, and the parts already in the collection.
// Read once, at module scope, because two separate blocks below want it -- it
// began life inside the first of them, where the second could not see it and
// threw a ReferenceError on every part form (ADR-0021's browser check found it).
const FORM = JSON.parse(document.getElementById('part-form-data').textContent);

const pt = document.getElementById('ptype');
if (pt) {
  // What the menu was on, so declining can put it back where it was.
  let was = pt.value;
  // Anything typed, ticked or chosen since the form was opened. Fetching the form
  // again means asking the server, and the server cannot know what is in the
  // boxes -- so it is worth saying so before it goes. Compared against what the
  // page was rendered with rather than against being empty: a field that arrived
  // filled in is not something you typed.
  const edited = () => [...document.querySelectorAll('form.edit input, ' +
                              'form.edit select, form.edit textarea')]
    .some(el => {
      if (el === pt || el.disabled) return false;
      if (el.type === 'file') return el.files && el.files.length;
      if (el.type === 'radio' || el.type === 'checkbox') {
        return el.checked !== el.defaultChecked;
      }
      if (el.tagName === 'SELECT') {
        // Against the option the markup marked, not against defaultSelected on
        // each one: a menu whose markup marks nothing still shows its first
        // option, and that option's defaultSelected stays false -- so every
        // untouched "not recorded" menu on the form read as edited.
        const def = [...el.options].find(o => o.defaultSelected) || el.options[0];
        return el.value !== (def ? def.value : '');
      }
      return (el.value || '') !== (el.defaultValue || '');
    });

  pt.addEventListener('change', () => {
    if (edited() && !window.confirm(
          'Changing the type builds this form again with that type\'s fields. '
          + 'Anything you have entered since opening it will be lost.')) {
      pt.value = was;
      return;
    }
    was = pt.value;
    const u = new URL(window.location.href);
    u.searchParams.set('type', pt.value);
    window.location.href = window.location.pathname + u.search;
  });
}
// Storage: two questions, kept apart because answering them as one went wrong
// twice. What is asked comes from the kind -- entry.STORAGE_ASKS says which kinds
// each group belongs to, and the server reads each back on the same condition, so
// a group on screen and a group read are the same set. Where the answers land --
// a row on a machine, or a part's own specs -- turns on there being a machine to
// fold the drive into, and decides only whether the part-only groups are asked at
// all: a folded drive has columns for four of them and nowhere to put the rest.
const kind = document.getElementById('kind');
if (kind) {
  // The kinds that fold into a machine's drives field rather than becoming a part.
  const ROW_KINDS = FORM.rowKinds;
  // Whether there is a machine to fold one into, which is what gui_create_part
  // routes on. An edit is always of a part that already exists.
  const routes = FORM.routes;
  const asks = [...document.querySelectorAll('#fs-storage .ask')];
  const driveBezel = document.getElementById('drive-bezel');
  const partBezel = document.getElementById('part-bezel');
  const descRow = document.getElementById('drive-desc-row');
  const descBox = document.getElementById('drive_desc');
  const FLOPPY = FORM.floppy;
  const OPTICAL = FORM.optical;

  const folds = () => routes && ROW_KINDS.includes(kind.value);

  // Whether any group on screen is sitting on "custom", which is the one case a
  // drive still needs prose: the box beside it says what the list could not.
  const anyCustom = () => asks.some(function (ask) {
    if (ask.hidden) return false;
    const on = ask.querySelector('input[type=radio]:checked');
    return on && on.value === 'custom';
  });

  // A group's box and its required flag follow its own visibility: a required
  // control inside a hidden block would refuse to submit and give the browser
  // nothing to focus, and a box for a "custom" nobody can see is no use either.
  function syncGroup(ask, focus) {
    const shown = !ask.hidden;
    ask.querySelectorAll('div[data-kind]').forEach(function (g) {
      g.hidden = g.dataset.kind !== kind.value;
      // A radio left checked from a kind since changed is not an answer to what is
      // being asked now: the groups share a field name, so it would otherwise still
      // be the one posted. The server refuses it against this kind's list either
      // way; clearing it here is so the form says the same thing.
      if (g.hidden) {
        g.querySelectorAll('input[type=radio]:checked').forEach(function (r) {
          r.checked = false;
        });
      }
    });
    ask.querySelectorAll('input[type=radio]').forEach(function (r) {
      const live = shown && !(r.closest('div[data-kind]') || {hidden: false}).hidden;
      r.required = live && ask.dataset.required === '1';
    });
    ask.querySelectorAll('input[type=text], input:not([type])').forEach(function (box) {
      if (!box.id.endsWith('_custom')) return;
      const group = box.closest('div[data-kind]');
      const live = shown && !(group ? group.hidden : false);
      const on = ask.querySelector('input[type=radio][value=custom]:checked');
      box.hidden = !(live && on);
      box.required = !box.hidden && ask.dataset.required === '1';
      if (focus && !box.hidden) box.focus();
    });
  }

  function toggle() {
    const folded = folds();
    asks.forEach(function (ask) {
      const kinds = (ask.dataset.kinds || '').split('|');
      // Asked for this kind at all, and -- once folded into a machine -- only if
      // the drive row has a column to keep the answer in.
      ask.hidden = !kinds.includes(kind.value)
                   || (folded && ask.dataset.row !== '1');
      syncGroup(ask, false);
    });
    // One bezel on screen, never two: the drive row's where the drive becomes a
    // row, the part's own where it becomes a part.
    if (driveBezel) driveBezel.hidden = !folded;
    if (partBezel) partBezel.hidden = folded;
    // The description, only where it still has something to say. Never hidden with
    // text in it -- the box still submits what it holds, so hiding a full one would
    // leave writing on the record that nobody can see or reach.
    if (descRow) {
      descRow.hidden = (kind.value === FLOPPY || kind.value === OPTICAL)
                       && !anyCustom() && !(descBox && descBox.value.trim());
    }
  }
  kind.addEventListener('change', toggle);

  // "custom" reveals the box it needs and takes the cursor there; choosing any
  // answer also decides whether the description still has a job, so the two are
  // settled together.
  asks.forEach(function (ask) {
    ask.querySelectorAll('input[type=radio]').forEach(function (r) {
      r.addEventListener('change', function () { syncGroup(ask, true); toggle(); });
    });
  });
  toggle();
}

// A screen's groups: "custom" reveals the box it needs and takes the cursor
// there. The same gesture the drive form has, without the rest of that form's
// machinery -- what a screen is asked does not depend on the answers, so there is
// nothing here to show and hide but the boxes themselves.
document.querySelectorAll('#fs-display .ask').forEach(function (ask) {
  const box = ask.querySelector('input[id$=_custom]');
  const radios = ask.querySelectorAll('input[type=radio]');
  if (!box || !radios.length) return;      // the checkbox group keeps its box
  const sync = function (focus) {
    const on = ask.querySelector('input[type=radio][value=custom]:checked');
    box.hidden = !on;
    if (focus && on) box.focus();
  };
  radios.forEach(r => r.addEventListener('change', () => sync(true)));
  sync(false);
});

// Entering a make and model already in the collection almost always means a
// second of the same thing, so offer to start from it rather than retyping its
// specs. Only offered on a new part, and only as a link: the existing record is
// never touched, and nothing is filled in until it is followed.
(function () {
  const known = FORM.known;
  const make = document.getElementById('manufacturer');
  const model = document.getElementById('model');
  const note = document.getElementById('samemake');
  const type = document.getElementById('ptype');
  if (!make || !model || !note) return;
  const norm = s => (s || '').trim().toLowerCase();

  // Narrow the model list to the chosen maker's models once one is picked.
  const models = document.getElementById('dl_models');
  function narrow() {
    if (!models) return;
    const m = norm(make.value);
    // With no maker chosen, offer every model. With one chosen, offer only its
    // models -- including none, when it is a maker nothing is recorded under:
    // suggesting another maker's models would be worse than suggesting nothing.
    const forMake = m ? known.filter(k => norm(k.m) === m) : known;
    const list = [...new Set(forMake.map(k => k.d))].sort();
    models.innerHTML = list.map(d => `<option value="${d.replace(/"/g, '&quot;')}">`).join('');
  }

  function look() {
    const m = norm(make.value), d = norm(model.value);
    const hit = (m && d) ? known.find(k => norm(k.m) === m && norm(k.d) === d) : null;
    if (!hit) { note.classList.add('is-hidden'); return; }
    const q = new URLSearchParams(location.search);
    const params = new URLSearchParams({from: hit.id});
    for (const k of ['computer_id', 'parent_id']) {
      if (q.get(k)) params.set(k, q.get(k));
    }
    note.innerHTML = `<a href="/parts/new?${params}">${hit.id} is the same make and `
      + `model — start from it</a> to copy its type, year and specs.`;
    // As in index.js: the note starts hidden by class, so it is the class that
    // has to go, not an inline display that was never there.
    note.classList.remove('is-hidden');
    if (type && hit.t && !q.get('type')) type.value = hit.t;
  }
  make.addEventListener('input', () => { narrow(); look(); });
  model.addEventListener('input', look);
  narrow();
})();
