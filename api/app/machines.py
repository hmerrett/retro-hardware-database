"""The catalogue of machines the register knows as models, and the variations each
was built in.

A PC is described by what is fitted in it -- a board, a card, a drive -- and the
register asks for those one at a time, each with its own asset tag. A home
computer or a console is not that sort of object. A ZX Spectrum is a sealed
machine that was built in a handful of documented forms, and what a collector
records about one is which of those forms it is: which board issue, which ULA,
16K or 48K, rubber keys or moulded ones. None of that is a part to tag, and none
of it means much except against a list of what was made.

A branded PC is both of those at once, and the two descriptions compose rather
than compete. An IBM 5170 is as documented and as varianted as any Amiga -- three
planar types, three BIOS dates, a lock on the front -- and it is also a box with
cards in it. The catalogue identity says which machine this is; the tagged parts
say what is fitted in it today, and neither answers the other's question. So the
line drawn here is not "home machine or PC". It is whether the thing was sold as
a model somebody documented: a Deskpro 386 was, and the beige tower somebody
screwed together out of a magazine advert was not, and that one is described by
its parts alone. This file therefore holds machines wherever they were sold and
whatever they were sold for -- a Spectrum, a PS/2 Model 80, an Olivetti M24 on an
accountant's desk.

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

# What the columns behind these answers hold (see models.AssetVariant and
# models.AssetChip). Checked here as well as in the tests, because a suggestion
# too long for its column would fail on save rather than at the keyboard, and the
# person it would fail for is the one who edited the file.
_LIMITS = {"key": 64, "issues": 64, "styles": 64, "regions": 32, "socket": 32, "variants": 64}

_TOP_FIELDS = {"lists", "families"}
_FAMILY_FIELDS = {"key", "name", "manufacturer", "regions", "chips", "models"}
_MODEL_FIELDS = {
    "key",
    "model",
    "manufacturer",
    "year",
    "cpu",
    "chassis",
    "os",
    "ram",
    "issues",
    "styles",
    "chips",
    "summary",
}
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
            hint = (
                f" -- did you mean '{near[0]}'?"
                if near
                else f" -- the fields here are: {', '.join(sorted(allowed))}"
            )
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
            hint = (
                f" -- did you mean '{near[0]}'?"
                if near
                else (
                    f" -- the shared lists are: {', '.join(sorted(lists))}"
                    if lists
                    else " -- there are no shared lists in this file"
                )
            )
            _fault(where, f"'{field}' names a shared list '{name}' that is not there{hint}")
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
            _fault(
                where,
                f"'{field}' has an answer of {len(line)} characters, and"
                f" the register stores {limit}: {line!r}",
            )
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
            _fault(
                at,
                f"'socket' is {len(role)} characters and the register stores {_LIMITS['socket']}",
            )
        if role in seen:
            _fault(where, f"the '{role}' socket is asked twice")
        seen.add(role)
        at = f"{where}, {role}"
        label = (
            _text(item.get("label"), at, "label")
            or (inherited or {}).get(role, {}).get("label")
            or _label_for(role)
        )
        out.append(
            _chip(
                role,
                label,
                _strings(item.get("variants"), lists, at, "variants"),
                _text(item.get("note"), at, "note"),
            )
        )
    return out


def _ram(raw, lists, where):
    """The standard memory sizes a model was sold with, as [(label, KiB)]. The label
    is what the memory box shows and reads back, so a size it cannot read is a size
    that would file the machine wrongly, and is refused here."""
    out = []
    for label in _strings(raw, lists, where, "ram"):
        kb = entry.to_kb(label)
        if kb is None:
            _fault(
                where,
                f"'ram' has a size the register cannot read: {label!r}"
                " -- write it as 48K, 128K, 1MiB",
            )
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
                _fault(
                    mat,
                    f"the key is {len(mkey)} characters and the register stores {_LIMITS['key']}",
                )
            if mkey in keys:
                _fault(
                    mat,
                    f"that key is already used, in {keys[mkey]} -- a key is"
                    " what a machine's record stores, so two models cannot"
                    " share one",
                )
            keys[mkey] = at
            year = mod.get("year")
            if not isinstance(year, int):
                _fault(mat, f"'year' should be a plain year like 1982, not {year!r}")
            family["models"].append(
                {
                    "key": mkey,
                    "model": _text(mod.get("model"), mat, "model", required=True),
                    "year": year,
                    "cpu": _text(mod.get("cpu"), mat, "cpu"),
                    "chassis": _text(mod.get("chassis"), mat, "chassis"),
                    "os": _text(mod.get("os"), mat, "os"),
                    # What makes the model worth holding, in a paragraph. Optional and
                    # often absent: a summary nobody could write accurately is better
                    # missing than invented, and the pages that show it fall back to
                    # the specs, which were never the interesting part but are at
                    # least true.
                    "summary": _text(mod.get("summary"), mat, "summary"),
                    "ram": _ram(mod.get("ram"), lists, mat),
                    "issues": _strings(mod.get("issues"), lists, mat, "issues"),
                    "styles": _strings(mod.get("styles"), lists, mat, "styles"),
                    "chips": _chips(mod.get("chips"), lists, mat, inherited),
                    **(
                        {"manufacturer": _text(mod["manufacturer"], mat, "manufacturer")}
                        if mod.get("manufacturer")
                        else {}
                    ),
                }
            )
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
    return [
        (0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
        for part in re.split(r"(\d+)", name or "")
        if part != ""
    ]


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
    out = {
        "family": family["name"],
        "family_key": family["key"],
        "manufacturer": family.get("manufacturer", ""),
        "regions": list(family.get("regions", [])),
        "ram": [],
        "issues": [],
        "styles": [],
        "cpu": "",
        "chassis": "",
        "os": "",
        "year": None,
    }
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
    out["full_name"] = name if doubled else " ".join(p for p in (maker, name) if p)
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
        out.append((family["name"], [_MODELS[m["key"]] for m in family["models"]]))
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
    return {
        "manufacturer": m.get("manufacturer", ""),
        "model": m.get("model", ""),
        "year": m.get("year"),
        "cpu": m.get("cpu", ""),
        "chassis": m.get("chassis", ""),
        "os": m.get("os", ""),
    }


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
    return sorted(
        pairs, key=lambda kv: (order.index(kv[0]) if kv[0] in order else len(order), kv[0])
    )


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


# --- reading a typed record against the catalogue ---------------------------
# Most of the register was typed before the catalogue existed, as a maker and a
# model in two free-text boxes, and most of those machines are in here under a key.
# This is how the two are introduced: not by rewriting what somebody typed -- the
# machine in front of them was the authority and still is -- but by proposing which
# model it looks like, for a person to agree with or not.

# How alike two names have to be before the catalogue will mention one at all. It
# is deliberately generous, because the job of this number is to decide what a
# person is shown rather than what is filed: "IBM 5170" and "IBM PC/AT 5170" are
# one machine written twice, while "Amstrad PC1640" and "Amstrad PC1512" are two
# machines that differ in three characters, and no threshold tells those apart. So
# everything above the floor is offered with its score and nothing above any score
# is ever filed without somebody saying yes.
MATCH_FLOOR = 0.7

# A parenthetical in a model box is somebody recording a second opinion beside the
# name -- "GRiDCASE 2 (Philips PC200)" -- rather than part of what the machine is
# called. Compared both ways, so it neither hides the match nor pretends it was
# not written down.
_ASIDE = re.compile(r"\s*\([^)]*\)")

# What the numbers in a name are worth. Nearly every machine in here is named with
# a number in it, and a number is the one part of a name that is never a near-miss:
# a 5170 is not almost a 5150, a PC1640 is not almost a PC1512, and letter by
# letter those pairs are as alike as two spellings of one machine. The same
# reasoning _by_name follows when it sorts an Amiga 500 before an Amiga 1000 --
# digits are read as digits and not as characters.
#
# Three cases, and all three are marked rather than decided, because a person who
# can see the machine settles it: the names disagree about a number, one of them
# is silent about a number the other carries ("Compaq Portable" is a real machine
# and so is the Portable 486/66 typed on the record), or they share one, which is
# the strongest thing two of these names can have in common.
# How much of a name has to line up in one unbroken run before "this name is
# inside that one" is worth believing. Below it the measure is the plain ratio:
# "Nascom 2" shares a couple of letters and a digit with half the register, and at
# eight characters long that is most of it.
_RUN_MIN = 5
_NUMBERS_DIFFER = 0.8
_NUMBER_MISSING = 0.85
_NUMBER_SHARED = 0.3
_DIGITS = re.compile(r"\d+")


def _whole(maker, name):
    """One machine's name written out in full -- the maker and the model together --
    and the same again with any aside taken off.

    Folded, which is what absorbs the trailing space in "IBM " -- two of those are
    in the live register, and a space is not a different manufacturer."""
    out = set()
    folded = _fold(" ".join(p for p in (maker, name) if (p or "").strip()))
    if folded:
        out.add(folded)
        bare = _fold(_ASIDE.sub("", folded))
        if bare:
            out.add(bare)
    return out


def _forms(maker, name):
    """Every way of writing it worth comparing: in full, and the model on its own
    for the many records whose maker box says what the model box already implies."""
    return _whole(maker, name) | _whole("", name)


def _alike(a, b):
    """How alike two folded names are, 0 to 1.

    Two measures, the better of them taken. difflib's ratio asks how much of the
    two strings together is shared, which is the right question about a misspelling
    and the wrong one about "Olivetti Personal Computer M21" against "Olivetti M21"
    -- the same machine, one of them with the words off the badge left in, and a
    ratio that halves for the extra words. So the second measure asks how much of
    the shorter name is inside the longer, which is what those two really differ by.

    Then the numbers: if both names carry digits and share none of them, they are
    not two ways of writing one machine however alike the letters are. Marked down
    rather than thrown away, because it is still worth offering to somebody who can
    see the machine."""
    m = difflib.SequenceMatcher(None, a, b)
    # The longest single run rather than every scrap that lines up: a short name
    # made of common letters can find a matching character in almost anything, and
    # adding those up says "Didaktik M" is inside "IBM 5170".
    run = m.find_longest_match(0, len(a), 0, len(b)).size
    score = m.ratio()
    if run >= _RUN_MIN:
        score = max(score, run / min(len(a), len(b)))
    mine, theirs = set(_DIGITS.findall(a)), set(_DIGITS.findall(b))
    shared = mine & theirs
    if shared:
        score += (1 - score) * _NUMBER_SHARED * len(shared) / len(mine)
    elif mine and theirs:
        score *= _NUMBERS_DIFFER
    elif mine or theirs:
        score *= _NUMBER_MISSING
    return min(score, 1.0)


# What a match on a style is worth against a match on the name. A style is where a
# machine's other names live -- an Olivetti M24 is an AT&T 6300, a Victor 9000 is a
# Sirius 1, a Tandon PCX is a TM 6001A -- and somebody typing what is on the badge
# in front of them has typed one of those as often as not. It is still the second
# answer to "what is this called", so a model whose own name is as good a match
# wins.
_BY_STYLE = 0.95


def suggest(manufacturer, model, limit=3):
    """Which catalogue models a typed manufacturer and model might mean, best first,
    as [(key, score, exact)]: a score from 0 to 1, and `exact` for a model whose
    name is the same name once case, spacing and asides are set aside.

    Nothing here writes anything or reads a database: it is a question about two
    strings, asked of the catalogue, and what is done with the answer belongs to
    whoever asked -- tools/adopt_machines.py asks it of a person, one machine at a
    time."""
    want = _forms(manufacturer, model)
    if not want:
        return []
    # Styles are matched against the whole of what was typed and never against the
    # model box alone. A style is a second name for the machine -- "AT&T 6300",
    # "Sirius 1", "TM 6001A" -- but it is also where a configuration ends up
    # ("386SX-20", "two drives"), and a bare model box tested against those finds
    # the PS/1 for a machine whose model box happens to read "386sx-40".
    whole = _whole(manufacturer, model)
    scored = []
    for key in _ORDER:
        m = _MODELS[key]
        have = _forms(m.get("manufacturer", ""), m["model"]) | {_fold(m["full_name"])}
        score = max(_alike(a, b) for a in want for b in have)
        for style in m["styles"]:
            also = _whole(m.get("manufacturer", ""), style)
            if also and whole:
                score = max(score, _BY_STYLE * max(_alike(a, b) for a in whole for b in also))
        if score >= MATCH_FLOOR:
            scored.append((key, round(score, 3), bool(want & have)))
    # The same name first, whatever the scores say. A machine typed as "BBC Micro
    # Model B" is as wholly inside "BBC Micro Model B+" as it is inside itself, and
    # of those two only one of them is what somebody wrote down. Then by score, then
    # by key -- so the same register gives the same report twice.
    scored.sort(key=lambda kv: (not kv[2], -kv[1], kv[0]))
    return scored[:limit]


def disagreements(key, record):
    """Where a typed record and the catalogue say different things about the same
    machine, as [(field, what the record says, what the catalogue says)].

    Shown in the report and never acted on. A catalogue year is what the model
    came out; the year on a record is what somebody read off the machine, and the
    machine wins -- two IBM 5170s in this register are dated 1985 and 1988, which
    is a fact about those two machines rather than a mistake about the AT."""
    m = model(key)
    if not m:
        return []
    out = []
    for field in ("manufacturer", "model", "year", "cpu"):
        mine, theirs = record.get(field), m.get(field)
        if mine in (None, "") or theirs in (None, ""):
            continue
        if _fold(str(mine)) != _fold(str(theirs)):
            out.append((field, str(mine), str(theirs)))
    return out


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
        entry_out["chips"] = [
            dict(c, variants=_extend(c["variants"], chips_seen.get(c["role"], ())))
            for c in model["chips"]
        ]
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
            "model": m["model"],
            "issues": m["issues"],
            "styles": m["styles"],
            "regions": m["regions"],
            "ram": ram_labels(key),
            "prefill": {k: v for k, v in prefill(key).items() if v not in (None, "")},
            "chips": [
                {
                    "role": c["role"],
                    "label": c["label"],
                    "variants": c["variants"],
                    "note": c.get("note", ""),
                }
                for c in m["chips"]
            ],
        }
    return out
