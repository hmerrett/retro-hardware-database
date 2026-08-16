"""The catalogue of known home machines, and the variations each was built in.

A PC is described by what is fitted in it -- a board, a card, a drive -- and the
register asks for those one at a time, each with its own asset tag. A home
computer or a console is not that sort of object. A ZX Spectrum is a sealed
machine that was built in a handful of documented forms, and what a collector
records about one is which of those forms it is: which board issue, which ULA,
16K or 48K, rubber keys or moulded ones. None of that is a part to tag, and none
of it means much except against a list of what was made.

So there is a list. It is not in here: it is in **machines.yaml**, next to this
file, written so that adding a machine to the register's catalogue needs nothing
but a text editor and the patience to line up the indentation. That file has its
own instructions at the top of it, and is the place to add a model. This module
loads it, checks it, and answers questions about it -- no database, no HTTP -- the
way entry.py holds the guided-entry vocabularies; machinedb owns the storage, as
ramdb does for a machine's memory.

Two things to hold on to when adding to the catalogue:

  * Every list names what is commonly seen, not everything that exists. The form
    offers them as radio buttons with a "custom" box beside them -- the rule the
    drive pickers already follow -- because a catalogue that refused the odd
    machine would be wrong more often than the machine was. A late board nobody has
    written up, a chip replaced in a repair, a Spectrum+ converted from a rubber-key
    machine: all of those are recorded by typing them.

    And what is typed once is offered ever after: with_recorded() adds everything
    already on file to the lists this module holds, so discovering a ULA the
    catalogue has never heard of is a thing you do once. That is why these lists
    can afford to be the common cases rather than an inventory -- the register
    completes them as it is used, and what turns up often enough to be worth
    curating can be written into the file later.
  * `key` is the stable slug and is the only thing stored. A label, a note, a
    chip's part number and even a model's name can be corrected without orphaning
    a record; a key cannot be changed without a migration. This is the lesson
    migration 0011 wrote down about memory modules, applied before it can be
    learned twice.

What a machine's own record holds is in machinedb: the model key, the board
issue, the style, the region, and one chip variant per socket. The rest of what is
in the catalogue -- names, years, CPU, notes -- is the catalogue's, read fresh every
time, so correcting an entry corrects every machine filed under it.

A bad edit to machines.yaml stops the register from starting, on purpose and with
the family, the model and the field named in the message. The alternative is a
catalogue that half-loads and quietly offers a Spectrum no ULA.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

import yaml

from . import entry

CATALOGUE_FILE = Path(__file__).resolve().parent / "machines.yaml"

# What the columns behind these answers hold (see models.ComputerVariant and
# models.ComputerChip). Checked here as well as in the tests, because a suggestion
# too long for its column would fail on save rather than at the keyboard, and the
# person it would fail for is the one who edited the file.
_LIMITS = {"key": 64, "issues": 64, "styles": 64, "regions": 32, "socket": 32,
           "variants": 64}

_TOP_FIELDS = {"lists", "families"}
_FAMILY_FIELDS = {"key", "name", "manufacturer", "regions", "chips", "models"}
_MODEL_FIELDS = {"key", "model", "manufacturer", "year", "cpu", "chassis", "os",
                 "ram", "issues", "styles", "chips"}
_CHIP_FIELDS = {"socket", "label", "note", "variants"}


class CatalogueError(ValueError):
    """machines.yaml says something the catalogue cannot read. Raised at import,
    with where in the file to look."""


def _fault(where, message):
    raise CatalogueError(f"{CATALOGUE_FILE.name}: {where}: {message}")


def _named(raw, what, n):
    """Where in the file to look, by the key if there is one to go on. A message
    about "model 7" sends a person counting; one about 'zx-spectrum-48k' does not."""
    key = raw.get("key") if isinstance(raw, dict) else None
    key = str(key or "").strip()
    return f"{what} '{key}'" if key else f"{what} {n}"


def _fields(got, allowed, where):
    """Refuse a field the catalogue does not have, and say which was meant. A typo
    that is quietly ignored is worse than one that stops the register: 'styel:' with
    no complaint is a model that lost its styles and nobody the wiser."""
    if not isinstance(got, dict):
        _fault(where, f"expected a block of fields, got {type(got).__name__}")
    for name in got:
        if name not in allowed:
            near = difflib.get_close_matches(str(name), sorted(allowed), 1, 0.6)
            hint = f" -- did you mean '{near[0]}'?" if near else \
                f" -- the fields here are: {', '.join(sorted(allowed))}"
            _fault(where, f"unknown field '{name}'{hint}")


def _text(value, where, field, required=False):
    if value is None:
        if required:
            _fault(where, f"'{field}' is needed and is not there")
        return ""
    if isinstance(value, (list, dict)):
        _fault(where, f"'{field}' should be one line of text, not a list")
    return str(value).strip()


def _strings(value, lists, where, field):
    """A list of lines: either written out, or the name of one of the shared lists
    at the top of the file."""
    if value is None:
        return []
    if isinstance(value, str):
        name = value.strip()
        if name not in lists:
            near = difflib.get_close_matches(name, sorted(lists), 1, 0.6)
            hint = f" -- did you mean '{near[0]}'?" if near else \
                (f" -- the shared lists are: {', '.join(sorted(lists))}" if lists
                 else " -- there are no shared lists in this file")
            _fault(where, f"'{field}' names a shared list '{name}' that is not"
                          f" there{hint}")
        return list(lists[name])
    if not isinstance(value, list):
        _fault(where, f"'{field}' should be a list, or the name of a shared list")
    out = []
    for item in value:
        if isinstance(item, (list, dict)):
            _fault(where, f"'{field}' should be a list of lines, not of blocks")
        line = str(item).strip()
        limit = _LIMITS.get(field)
        if limit and len(line) > limit:
            _fault(where, f"'{field}' has an answer of {len(line)} characters, and"
                          f" the register stores {limit}: {line!r}")
        if line:
            out.append(line)
    if len(set(out)) != len(out):
        dupe = next(v for v in out if out.count(v) > 1)
        _fault(where, f"'{field}' offers {dupe!r} twice")
    return out


def _label_for(role):
    """What to call a socket nobody has named: the slug tidied up. A short one is an
    initialism ('cpu' -> 'CPU'), a longer one a word ('kernal' -> 'Kernal')."""
    role = (role or "").replace("-", " ")
    return role.upper() if len(role) <= 4 else role.capitalize()


def _chip(role, label, variants, note=""):
    """One socket a model's record can name a chip for. `role` is the stable slug
    that gets stored, `label` is what the form and the page call it."""
    return {"role": role, "label": label, "variants": list(variants), "note": note}


def _chips(raw, lists, where, inherited=None):
    """The sockets a family or a model names, in the order they are written -- which
    is the order a person reads a board in."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        _fault(where, "'chips' should be a list, one '- socket:' per socket")
    out, seen = [], set()
    for n, item in enumerate(raw, 1):
        at = f"{where}, chip {n}"
        _fields(item, _CHIP_FIELDS, at)
        role = _text(item.get("socket"), at, "socket", required=True)
        if len(role) > _LIMITS["socket"]:
            _fault(at, f"'socket' is {len(role)} characters and the register stores"
                       f" {_LIMITS['socket']}")
        if role in seen:
            _fault(where, f"the '{role}' socket is asked twice")
        seen.add(role)
        at = f"{where}, {role}"
        label = _text(item.get("label"), at, "label") \
            or (inherited or {}).get(role, {}).get("label") or _label_for(role)
        out.append(_chip(role, label,
                         _strings(item.get("variants"), lists, at, "variants"),
                         _text(item.get("note"), at, "note")))
    return out


def _ram(raw, lists, where):
    """The standard memory sizes a model was sold with, as [(label, KiB)]. The label
    is what the memory box shows and reads back, so a size it cannot read is a size
    that would file the machine wrongly, and is refused here."""
    out = []
    for label in _strings(raw, lists, where, "ram"):
        kb = entry.to_kb(label)
        if kb is None:
            _fault(where, f"'ram' has a size the register cannot read: {label!r}"
                          " -- write it as 48K, 128K, 1MiB")
        out.append((label, kb))
    return out


def load(path=None):
    """machines.yaml as the list of families this module answers from. Separate from
    the module-level load so a test -- or someone checking a file before deploying
    it -- can read one without importing it."""
    path = Path(path or CATALOGUE_FILE)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fault("the file", f"is not at {path}")
    except yaml.YAMLError as exc:
        _fault("the file", f"is not valid YAML -- {exc}")
    if not isinstance(raw, dict):
        _fault("the file", "should start with 'lists:' and 'families:'")
    _fields(raw, _TOP_FIELDS, "the file")

    lists = {}
    for name, items in (raw.get("lists") or {}).items():
        lists[str(name)] = _strings(items, {}, f"shared list '{name}'", "variants")

    families, keys = [], {}
    if not raw.get("families"):
        _fault("the file", "has no families in it")
    for n, fam in enumerate(raw["families"], 1):
        # Named before it is checked, so a misspelled field is reported against the
        # family it is in rather than against "family 7".
        at = _named(fam, "family", n)
        _fields(fam, _FAMILY_FIELDS, at)
        key = _text(fam.get("key"), at, "key", required=True)
        at = f"family '{key}'"
        family = {
            "key": key,
            "name": _text(fam.get("name"), at, "name", required=True),
            "manufacturer": _text(fam.get("manufacturer"), at, "manufacturer"),
            "regions": _strings(fam.get("regions"), lists, at, "regions"),
            "chips": _chips(fam.get("chips"), lists, at),
            "models": [],
        }
        inherited = {c["role"]: c for c in family["chips"]}
        if not fam.get("models"):
            _fault(at, "has no models in it")
        for mn, mod in enumerate(fam["models"], 1):
            mat = f"{at}, {_named(mod, 'model', mn)}"
            _fields(mod, _MODEL_FIELDS, mat)
            mkey = _text(mod.get("key"), mat, "key", required=True)
            mat = f"{at}, model '{mkey}'"
            if len(mkey) > _LIMITS["key"]:
                _fault(mat, f"the key is {len(mkey)} characters and the register"
                            f" stores {_LIMITS['key']}")
            if mkey in keys:
                _fault(mat, f"that key is already used, in {keys[mkey]} -- a key is"
                            " what a machine's record stores, so two models cannot"
                            " share one")
            keys[mkey] = at
            year = mod.get("year")
            if not isinstance(year, int):
                _fault(mat, f"'year' should be a plain year like 1982, not {year!r}")
            family["models"].append({
                "key": mkey,
                "model": _text(mod.get("model"), mat, "model", required=True),
                "year": year,
                "cpu": _text(mod.get("cpu"), mat, "cpu"),
                "chassis": _text(mod.get("chassis"), mat, "chassis"),
                "os": _text(mod.get("os"), mat, "os"),
                "ram": _ram(mod.get("ram"), lists, mat),
                "issues": _strings(mod.get("issues"), lists, mat, "issues"),
                "styles": _strings(mod.get("styles"), lists, mat, "styles"),
                "chips": _chips(mod.get("chips"), lists, mat, inherited),
                **({"manufacturer": _text(mod["manufacturer"], mat, "manufacturer")}
                   if mod.get("manufacturer") else {}),
            })
        # By name, whatever order they are written in -- the same reasoning as
        # sorting the families, and it keeps a machine slotted in next to the one it
        # was copied from from landing out of sequence.
        family["models"].sort(key=lambda m: _by_name(m["model"]))
        families.append(family)
    families.sort(key=_by_maker)
    return families


def _by_name(name):
    """A model name in the order a person means by alphabetical, which is not the
    order the characters are in: nearly every one of these names has a number in it,
    and comparing "1000" against "500" a character at a time files the Amiga 1000
    before the 500 and the 1040ST before the 520ST. So the digits are compared as
    numbers and everything else as letters, case ignored."""
    # Each chunk is (which kind, the number, the letters), so a name that starts
    # with a digit and one that starts with a letter can still be compared -- an
    # Atari 400 against an Atari Lynx. Numbers sort before letters.
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
            for part in re.split(r"(\d+)", name or "") if part != ""]


def _by_maker(family):
    """Families are offered in alphabetical order of who made them, whatever order
    the file happens to list them in.

    There are two dozen of them and there will be more, and a picker of that length
    is only usable if a person can guess where to look. Sorting here rather than
    asking the file to stay in order means someone adding a family can put it
    wherever they like -- at the end, next to the one they copied -- and it still
    lands in the right place. A family of several makers (MSX) sorts under its own
    name instead, which is what a person would look for it under.
    """
    maker = family["manufacturer"] or family["name"]
    return (maker.casefold(), family["name"].casefold())


# One entry per family, each holding what its models share (the maker, the regions
# it sold in, the chip sockets) and then the models themselves. A model's own
# fields win over its family's, and a chip it names replaces the family's chip for
# that socket rather than adding a second one. See machines.yaml for what each
# field means and how to add to it.
FAMILIES = load()


# --- lookups ----------------------------------------------------------------

def _merge(family, mod):
    """One model as everything known about it: the family's fields where the model
    is silent, and the family's chip sockets where it names none of its own.

    A chip the model names replaces the family's for that socket rather than
    joining it, keeping the family's place in the order -- which is the order a
    person reads a board in -- and anything it adds follows. A replacement with no
    variants removes the socket, which is how a VIC-20 says it has no SID and a
    ZX80 that it has no ULA, without either repeating the rest of its family.
    """
    out = {"family": family["name"], "family_key": family["key"],
           "manufacturer": family.get("manufacturer", ""),
           "regions": list(family.get("regions", [])),
           "ram": [], "issues": [], "styles": [], "cpu": "", "chassis": "",
           "os": "", "year": None}
    out.update({k: v for k, v in mod.items() if k != "chips"})
    own = {c["role"]: c for c in mod.get("chips", [])}
    chips = [own.pop(c["role"], c) for c in family.get("chips", [])]
    chips += [c for c in mod.get("chips", []) if c["role"] in own]
    out["chips"] = [c for c in chips if c["variants"]]
    # After the update, so a model that names its own maker -- the Amstrad-built
    # Spectrums -- is named after that one rather than its family's.
    #
    # A handful of machines were sold under a name their maker is already inside
    # of: a ColecoVision is not a "Coleco Vision" and cannot be split into the two
    # boxes the way a Commodore 64 can. Those keep the one name rather than
    # stuttering it.
    maker, name = out["manufacturer"], out["model"]
    doubled = maker and name.lower().startswith(maker.lower())
    out["full_name"] = name if doubled else \
        " ".join(p for p in (maker, name) if p)
    return out


_MODELS = {}
_ORDER = []
for _family in FAMILIES:
    for _model in _family["models"]:
        _MODELS[_model["key"]] = _merge(_family, _model)
        _ORDER.append(_model["key"])


def model(key):
    """One catalogue model by key, with its family's fields filled in, or None for
    a key the catalogue does not know -- which is what a machine filed under a key
    since removed comes back as."""
    return _MODELS.get((key or "").strip()) or None


def models():
    """Every model, in catalogue order."""
    return [_MODELS[k] for k in _ORDER]


def keys():
    return list(_ORDER)


def grouped():
    """[(family name, [model])] in catalogue order, for the picker's optgroups."""
    out = []
    for family in FAMILIES:
        out.append((family["name"],
                    [_MODELS[m["key"]] for m in family["models"]]))
    return out


def roles(key):
    """The chip sockets a model is asked about, in board-reading order."""
    m = model(key)
    return [c["role"] for c in m["chips"]] if m else []


def chip(key, role):
    """One socket of one model, or None if that model has no such socket."""
    m = model(key)
    if not m:
        return None
    return next((c for c in m["chips"] if c["role"] == role), None)


def chip_label(key, role):
    """What to call a socket on a page or a label. Falls back to the role slug
    tidied up, so a chip recorded against a model or a socket the catalogue no
    longer lists still says what it is rather than disappearing."""
    c = chip(key, role)
    return c["label"] if c else _label_for(role)


def prefill(key):
    """What picking a model can fill in on a machine's record: the fields that are
    true of every one of that model. The form only ever puts these into a box that
    is empty, because the machine in front of you is the authority and the
    catalogue is a starting point."""
    m = model(key)
    if not m:
        return {}
    return {"manufacturer": m.get("manufacturer", ""), "model": m.get("model", ""),
            "year": m.get("year"), "cpu": m.get("cpu", ""),
            "chassis": m.get("chassis", ""), "os": m.get("os", "")}


def full_name(key):
    """The name a model is known by, maker and all: "Commodore 64", "CPC 464".

    The catalogue stores the two apart, because that is how a machine's record
    holds them -- a model field that repeated the maker filed a C64 as "Commodore
    Commodore 64" the moment both boxes were prefilled by the same pick. This is
    for the one place a model is named with nothing beside it: the picker's menu,
    where "64 (1982)" says less than it should. Everywhere else -- the record, the
    label, the rendered variant line -- the manufacturer is already on the page,
    and repeating it there is the clunk this was split up to avoid.
    """
    m = model(key)
    return m["full_name"] if m else (key or "").strip()


def ram_labels(key):
    """The standard memory sizes a model was sold with, as the labels the memory
    box takes ('16K', '48K')."""
    m = model(key)
    return [label for label, _kb in m["ram"]] if m else []


# --- rendering --------------------------------------------------------------

# The keys the rendered line uses for the three answers that are not a chip. The
# chips use their own labels, so a line reads as the machine reads: the model, then
# what distinguishes this one, then the sockets in board order.
#
# "Board" rather than "Issue" because the value already says which word its make
# used for the same thing -- Sinclair and Acorn number an issue, Commodore an ASSY,
# Amiga a Rev and Sega a VA -- and one field holds all four rather than pretending
# they are different questions.
ISSUE_KEY = "Board"
STYLE_KEY = "Style"
REGION_KEY = "Region"


def render(model_key="", issue="", style="", region="", chips=()):
    """A machine's catalogue identity as one line, in the register's own
    'Key: value | Key: value' notation -- the model first, without a key, because
    it is the subject rather than an attribute of one.

        ZX Spectrum+ | Board: Issue 6A | Style: moulded keys | ULA: Ferranti 6C001E-7

    This is a rendering and never a store: it is what the machine page, the label,
    the search index and the wire format read, and it is written fresh from the
    rows every time they change (machinedb.write). Nothing parses it back -- the
    mistake migration 0011 was written to undo -- so the words here are free to be
    improved.
    """
    m = model(model_key)
    pairs = []
    if model_key:
        pairs.append(("", m["model"] if m else model_key))
    pairs += [(ISSUE_KEY, issue), (STYLE_KEY, style), (REGION_KEY, region)]
    for role, variant in in_role_order(model_key, chips):
        pairs.append((chip_label(model_key, role), variant))
    return entry.build_specs(pairs)


def in_role_order(model_key, chips):
    """(role, variant) pairs in the order the catalogue lists the sockets, with
    anything it does not list last -- a chip kept from a model this machine is no
    longer filed as, or a socket since removed from the catalogue."""
    pairs = list(chips.items()) if isinstance(chips, dict) else list(chips)
    order = roles(model_key)
    return sorted(pairs, key=lambda kv: (order.index(kv[0]) if kv[0] in order
                                         else len(order), kv[0]))


def _fold(text):
    """The form two spellings of one answer have in common, for telling whether
    something is already offered: case and spacing are how the same chip gets
    written twice, and neither makes it a different chip."""
    return " ".join((text or "").split()).lower()


def _extend(known, seen):
    """`known` with everything in `seen` it does not already offer, the curated order
    kept and the discoveries after it in alphabetical order -- so the list a person
    reads down stays the one that was written deliberately, and what the register
    has taught it follows."""
    have = {_fold(k) for k in known}
    extra = {}
    for value in seen:
        folded = _fold(value)
        if value and folded not in have:
            extra.setdefault(folded, value.strip())
    return [*known, *sorted(extra.values(), key=str.lower)]


def with_recorded(catalogue, recorded):
    """A form catalogue with every answer already on file added to the lists it
    offers, so a variation that had to be typed once is picked from a radio button
    the next time -- which is what makes this a catalogue that grows rather than a
    list of what was known the day it was written.

    `recorded` is machinedb.recorded(): what real machines say, keyed by model. Only
    the lists a model already has are extended, and only for the model it was seen
    on: a ULA found in a Spectrum says nothing about a Commodore 64, and a socket
    the catalogue has since dropped is not brought back by a machine that still
    names it.
    """
    out = {}
    for key, model in catalogue.items():
        seen = recorded.get(key) or {}
        entry_out = dict(model)
        for field in ("issues", "styles", "regions"):
            entry_out[field] = _extend(model[field], seen.get(field, ()))
        chips_seen = seen.get("chips") or {}
        entry_out["chips"] = [dict(c, variants=_extend(c["variants"],
                                                       chips_seen.get(c["role"], ())))
                              for c in model["chips"]]
        out[key] = entry_out
    return out


def form_catalogue():
    """The whole catalogue as plain data for the edit form's pickers: what each
    model offers, and what picking it fills in.

    One structure, shipped to the browser as JSON, because the form's variation
    fields are built from whichever model is chosen and a page cannot hold a set of
    menus for every model in the catalogue. The same lists the server reads a save back
    against, so the two cannot come to disagree about what a model was built in.
    """
    out = {}
    for key in _ORDER:
        m = _MODELS[key]
        out[key] = {
            "model": m["model"], "issues": m["issues"], "styles": m["styles"],
            "regions": m["regions"], "ram": ram_labels(key),
            "prefill": {k: v for k, v in prefill(key).items() if v not in (None, "")},
            "chips": [{"role": c["role"], "label": c["label"],
                       "variants": c["variants"], "note": c.get("note", "")}
                      for c in m["chips"]],
        }
    return out
