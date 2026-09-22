(function () {
  const DATA = JSON.parse(document.getElementById('machine-data').textContent);
  const CAT = DATA.catalogue;
  const SAVED = DATA.saved;
  const WIDTHS = DATA.widths;
  // A board's form asks the model, the revision and the chips, and never draws
  // the two a case answers -- which is also how the save reads it back, since a
  // field that is not on the page posts nothing.
  const BOARD = DATA.board;
  const pick = document.querySelector('[data-machine-pick]');
  const box = document.querySelector('[data-machine-vars]');
  if (!pick || !box) return;
  const ramBox = document.getElementById(DATA.ramField);

  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  // What one group says: the answer it offered that is chosen, or what was typed
  // beside "custom". The same reading the server takes of the same fields.
  const groupValue = (name) => {
    const plain = box.querySelector(`input[type=text][name="${name}"]`);
    if (plain) return plain.value;
    const on = box.querySelector(`input[name="${name}"]:checked`);
    if (!on) return '';
    if (on.value !== 'custom') return on.value;
    const custom = box.querySelector(`input[name="${name}_custom"]`);
    return custom ? custom.value.trim() : '';
  };

  // What the fields hold now, so changing the model keeps the answers whose question
  // the new model also asks -- a C64 refiled as a C64C still has the SID it had.
  // Before they have been built once, that is whatever was last saved.
  const held = () => {
    if (!box.children.length) return SAVED;
    const now = {chips: {}, sockets: {}};
    for (const f of (BOARD ? ['issue'] : ['issue', 'style', 'region'])) {
      now[f] = groupValue(`mach_${f}`);
    }
    box.querySelectorAll('[data-role]').forEach(el => {
      now.chips[el.dataset.role] = groupValue(el.dataset.field);
      const tick = el.querySelector('input[type=checkbox]');
      if (tick) now.sockets[el.dataset.role] = tick.checked;
    });
    return now;
  };

  const radio = (name, value, checked, label) =>
    `<label class="check"><input type="radio" name="${esc(name)}" value="${esc(value)}"` +
    `${checked ? ' checked' : ''}> ${esc(label)}</label>`;

  // One question: what the catalogue offers, "not recorded" for the socket nobody
  // has looked in yet, and "custom" for the machine it has not met. An answer from
  // outside the list chooses custom and fills the box, so a form reopens on what it
  // saved.
  // The tickbox that rides with a chip: on for a chip in a socket, off for one
  // soldered to the board. It is only read for a socket that names a chip, so a
  // box left off beside "not recorded" answers nothing -- which is what keeps
  // saving a form from deciding that every chip nobody looked at is soldered.
  const socketBox = (name, held) =>
    `<label class="check socketed"><input type="checkbox" name="${esc(name)}:socketed"` +
    `${held ? ' checked' : ''}> in a socket <span class="muted">— rather than ` +
    `soldered to the board</span></label>`;

  const field = (name, label, hint, value, options, maxlen, role, socketed) => {
    const attrs = `class="field" data-field="${esc(name)}"${role ? ` data-role="${esc(role)}"` : ''}`;
    const head = `<label for="${esc(name)}">${esc(label)}</label>` +
      (hint ? `<p class="hint">${esc(hint)}</p>` : '');
    const foot = role ? socketBox(name, socketed) : '';
    if (!options.length) {
      return `<div ${attrs}>${head}
        <input class="input" type="text" id="${esc(name)}" name="${esc(name)}"
               value="${esc(value)}" ${maxlen ? `maxlength="${maxlen}"` : ''}
               autocomplete="off">${foot}</div>`;
    }
    const custom = value !== '' && !options.some(o => o === value);
    return `<div ${attrs}>${head}
      <div class="checks">
        ${radio(name, '', !value, 'not recorded')}
        ${options.map(o => radio(name, o, o === value, o)).join('')}
        ${radio(name, 'custom', custom, 'custom')}
      </div>
      <input class="input" name="${esc(name)}_custom" value="${esc(custom ? value : '')}"
             ${maxlen ? `maxlength="${maxlen}"` : ''} autocomplete="off"
             placeholder="as it is marked"${custom ? '' : ' hidden'}>${foot}</div>`;
  };

  // "custom" reveals the box it needs and takes the cursor there; every other answer
  // needs no box at all, and an empty one is not left on screen to be wondered about.
  box.addEventListener('change', (ev) => {
    const el = ev.target;
    if (el.type !== 'radio') return;
    const custom = box.querySelector(`input[name="${el.name}_custom"]`);
    if (!custom) return;
    custom.hidden = el.value !== 'custom';
    if (!custom.hidden) custom.focus();
  });

  // The boxes on the form that only a PC has an answer for -- the TopBench score
  // so far. Off screen for a catalogue machine, which cannot run a DOS benchmark,
  // and hidden rather than emptied: a hidden input still submits what it holds, so
  // a score on file survives a machine being filed against the catalogue by
  // mistake and put back.
  const x86 = document.querySelectorAll('[data-x86-only]');

  const build = () => {
    const model = CAT[pick.value];
    x86.forEach(el => { el.hidden = !!model; });
    const was = held();
    // Not a catalogue machine: nothing to ask about, and nothing left on screen for
    // a save to read.
    if (!model) { box.innerHTML = ''; return; }
    let html = '<input type="hidden" name="mach_fields" value="1">';
    html += field('mach_issue', 'Board issue / revision',
                  'as its make marked it: Sinclair and Acorn number an issue, ' +
                  'Commodore an ASSY, an Amiga a Rev, a Mega Drive a VA',
                  was.issue || '', model.issues, WIDTHS.issue);
    if (!BOARD && model.styles.length) {
      html += field('mach_style', 'Case / keyboard',
                    'what tells two of these apart from across the room',
                    was.style || '', model.styles, WIDTHS.style);
    }
    if (!BOARD && model.regions.length) {
      html += field('mach_region', 'Region',
                    'the market it was built for, which on some machines is also ' +
                    'which video chip is in it',
                    was.region || '', model.regions, WIDTHS.region);
    }
    if (model.chips.length) {
      html += '<div class="field"><span class="lbl">Chips fitted</span>' +
        '<p class="hint">the sockets worth writing down on this model, each ' +
        'offering the numbers that turn up in it. Leave one at <em>not ' +
        'recorded</em> until it has been looked at — a guess is worse than ' +
        'nothing. Use <em>custom</em> for a marking the list has not got; it ' +
        'joins the list next time. Tick the ones in a socket — a chip named with ' +
        'the box clear is recorded as soldered down.</p></div>';
      for (const chip of model.chips) {
        html += field(`chip:${chip.role}`, chip.label, chip.note,
                      was.chips[chip.role] || '', chip.variants,
                      WIDTHS.chip || 64, chip.role,
                      (was.sockets || {})[chip.role]);
      }
    }
    box.innerHTML = html;
  };

  // The sizes a model was sold with, offered on the memory box rather than written
  // into it: 16K or 48K is a question about the machine in front of you, and one a
  // RAM pack or an upgrade can have answered either way.
  const offerRam = () => {
    const model = CAT[pick.value];
    if (!ramBox) return;
    let dl = document.getElementById('dl_machine_ram');
    if (!model || !model.ram.length) {
      if (dl) { dl.remove(); ramBox.removeAttribute('list'); }
      return;
    }
    if (!dl) {
      dl = document.createElement('datalist');
      dl.id = 'dl_machine_ram';
      ramBox.after(dl);
      ramBox.setAttribute('list', 'dl_machine_ram');
    }
    dl.innerHTML = model.ram.map(r => `<option value="${esc(r)}">`).join('');
  };

  // Filling in what is true of every one of these, and only where the box is empty
  // or still holds what the model picked before it put there: the machine in front
  // of you is the authority and the catalogue is a starting point, so anything typed
  // by hand stands. Correcting a mis-pick therefore corrects the boxes that came
  // with it -- picking the C64 and then the Mega Drive must not leave a Mega Drive
  // called a Commodore 64 -- while a name someone wrote themselves is left alone.
  //
  // Only on a deliberate change of model, never on load, so re-opening a machine to
  // correct one field cannot quietly refill another.
  let last = pick.value;
  const prefill = () => {
    const was = (CAT[last] || {}).prefill || {};
    const now = (CAT[pick.value] || {}).prefill || {};
    for (const name of new Set([...Object.keys(was), ...Object.keys(now)])) {
      const el = document.getElementById(name);
      if (!el) continue;
      const mine = el.value.trim();
      if (mine && mine !== String(was[name] == null ? '' : was[name])) continue;
      el.value = now[name] == null ? '' : now[name];
    }
    last = pick.value;
  };

  pick.addEventListener('change', () => { build(); offerRam(); prefill(); });
  build();
  offerRam();
})();
