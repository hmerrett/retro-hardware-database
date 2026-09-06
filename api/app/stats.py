"""Collection statistics for the public /stats page: the pool of "facts" the page
draws a handful from, and the summary figures behind them. Everything is counted
from the typed columns and child tables. Pure logic; the /stats route stays in
main and calls in here.
"""
from collections import Counter
from datetime import date
from urllib.parse import quote

from sqlalchemy import func

from . import entry, projects
from .common import (
    REGISTER, RELIABILITY_MIN, _all_years, _big_total, _held, _maker_reliability,
    _portraits, folder_images, to_dict,
)
from .models import (
    AssetVariant, Computer, ComputerDrive, ComputerRamChip, IoSpec, LogEntry,
    MotherboardSpec, NetworkSpec, Part, PartPort, PartRamSlot, PartSlot, Project,
    ProjectAsset, ProjectOrder, ProjectTask, SoundSpec, StorageSpec, VideoSpec,
)


def _facts(db, st, this_year):
    """Every figure the collection can currently answer, in one pool for the page to
    draw a handful from.

    There used to be two halves: a fixed set of tiles that were always on the page,
    and a shuffled set of odder ones underneath. The split flattered the fixed half --
    "spares on the shelf" is no more a headline than "longest wait" -- and it meant
    the interesting figures were the ones you had to scroll to. One pool, shuffled,
    and the page is different every time you look at it.

    Each figure is skipped rather than shown empty, so the pool is what the register
    can currently answer: a collection with no acquisition dates simply never offers
    the ones about waiting, and a fresh install offers none of them.

    Disposed items are left out throughout -- see _held -- bar the one figure that is
    about them.
    """
    out = []

    def add(k, v, s, href=None):
        out.append({"k": k, "v": v, "s": s, "href": href})

    def named(obj):
        return entry.display_name(to_dict(obj))

    # --- how big it is ------------------------------------------------------

    if st["top_maker"]:
        add("Most represented maker", st["top_maker"][0],
            f"{st['top_maker'][1]} parts",
            f"/browse?f=maker&v={quote(st['top_maker'][0])}")
    if st["top_type"]:
        add("Most collected thing", entry.type_label(st["top_type"][0]),
            f"{st['top_type'][1]} of them",
            f"/browse?f=type&v={quote(st['top_type'][0])}")
    if st["mean_year"]:
        add("The average item", str(st["mean_year"]),
            f"{this_year - st['mean_year']} years old", "/browse?f=year")
    if st["top_ram"]:
        each = " each" if len(st["top_ram"]) > 1 else ""
        n = st["top_ram"][0][1]
        add("Usual amount of memory",
            " / ".join(r[0] for r in st["top_ram"]),
            f"{n} machine{'' if n == 1 else 's'}{each}",
            "/browse?f=ram&v=" + ",".join(str(k) for k in st["top_ram_kb"]))
    if st["fitted_kb"]:
        add("Memory fitted, everything added up",
            entry.fmt_kb(st["fitted_kb"], True), "across every machine here",
            "/browse?f=ramfitted")
    if st["stored_kb"]:
        # The comparison used to be a hardcoded "one modern phone's worth", which
        # stopped being true as the register grew. Worked out, it stays true.
        phone_kb = 128 * 1024 * 1024
        share = st["stored_kb"] / phone_kb
        how = (f"about {share:.0%} of one modern phone" if share < 1
               else f"{share:.1f} modern phones' worth")
        add("Storage, everything added up", _big_total(st["stored_kb"]), how,
            "/browse?f=storage")
    if st["slots_per_board"]:
        add("Expansion slots", str(st["slots"]),
            f"on {st['boards']} boards, {st['slots_per_board']} each",
            "/browse?f=slots")
    if st["chips"]:
        add("Memory chips counted individually", str(int(st["chips"])),
            "soldered or socketed on a board", "/browse?f=chips")
    if st["drives"]:
        add("Drives fitted", str(int(st["drives"])),
            f"{st['gotek']} of them a Gotek" if st["gotek"]
            else "in the machines, counted individually", "/browse?f=drives")
    if st["working_pct"] is not None:
        add("Still working", f"{st['working_pct']}%",
            f"{st['working']} of {st['n_parts']} parts",
            "/browse?f=condition&v=Working")
    if st["oldest_year"] and st["newest_year"] > st["oldest_year"]:
        add("Oldest and newest", f"{st['oldest_year']}–{st['newest_year']}",
            f"{st['newest_year'] - st['oldest_year']} years apart",
            "/browse?f=extremes")
    if st["fullest"]:
        add("Best equipped machine", named(st["fullest"][0]),
            f"{st['fullest'][1]} parts fitted",
            f"/browse?f=in&v={st['fullest'][0].asset_id}")
    if st["oldest_held"]:
        add("Longest in the collection", named(st["oldest_held"]),
            f"since {st['oldest_held'].acquired_date}", "/browse?f=held")
    if st["fitted_per_machine"] is not None and st["fitted"]:
        add("Fitted in a machine", str(st["fitted"]),
            f"{st['fitted_per_machine']} per machine on average", "/browse?f=fitted")
    if st["spares"]:
        add("Spares on the shelf", str(st["spares"]), "waiting for a home",
            "/browse?f=spares")
    if st["disposed"]:
        # Counts the disposed, being the figure that is about them.
        add("No longer with us", str(st["disposed"]), "binned, sold or donated",
            "/browse?f=disposed")

    # --- and what it is like ------------------------------------------------

    rel = _maker_reliability(db)
    if len(rel) >= 2:
        best, worst = rel[0], rel[-1]
        add("Most reliable maker", best[0],
            f"{best[2]} of {best[1]} parts working",
            f"/browse?f=maker&v={quote(best[0])}")
        add("Least reliable maker", worst[0],
            f"{worst[2]} of {worst[1]} parts working",
            f"/browse?f=maker&v={quote(worst[0])}")

    # The long wait: made one year, arrived another. Computers and parts together,
    # because the record is the same record either way.
    waits = []
    for model in (Computer, Part):
        for obj in _held(db.query(model).filter(model.year.isnot(None),
                                                model.acquired_date.isnot(None)),
                         model):
            waits.append((obj.acquired_date.year - obj.year, obj))
    waits = [w for w in waits if w[0] > 0]
    if waits:
        gap, obj = max(waits, key=lambda w: w[0])
        kind = "computers" if isinstance(obj, Computer) else "parts"
        add("Longest wait", f"{gap} years",
            f"{named(obj)}, made {obj.year}, arrived {obj.acquired_date.year}",
            f"/{kind}/{obj.asset_id}")

    # Every floppy in every machine, as though each had a disk in it. Pure whimsy,
    # and it says so: the drives are real, the disks are hypothetical.
    #
    # Floppies and Goteks only. The same column holds an optical drive's size and a
    # card reader's, and a 4GB CF card among the 1.44s swamps the total: the first
    # draft of this said 7189 MiB, of which 7000 was two memory cards.
    floppy_kb, floppy_n = 0, 0
    for size, count in _held(
            db.query(ComputerDrive.size, ComputerDrive.count)
            .join(Computer, Computer.asset_id == ComputerDrive.computer_id)
            .filter(ComputerDrive.size != "",
                    ComputerDrive.kind.in_(("floppy", "Gotek"))), Computer):
        kb = entry.to_kb(size)
        if kb:
            floppy_kb += kb * (count or 1)
            floppy_n += count or 1
    # Three drives is where adding them up starts being a joke rather than a sum;
    # below that "if all 2 drives had a disk in them" is just arithmetic.
    if floppy_kb and floppy_n >= 3:
        add("Every floppy at once", f"{round(floppy_kb / 1024)} {entry.MIB}",
            f"if all {floppy_n} drives had a disk in them",
            "/browse?f=drives")

    held_ids = {a for (a,) in _held(db.query(Computer.asset_id), Computer)} | {
        a for (a,) in _held(db.query(Part.asset_id), Part)}

    eventful = (db.query(LogEntry.asset_id, func.count(LogEntry.id))
                .filter(LogEntry.asset_id.in_(held_ids) if held_ids else False)
                .group_by(LogEntry.asset_id)
                .order_by(func.count(LogEntry.id).desc()).first())
    if eventful:
        obj = db.get(Computer, eventful[0]) or db.get(Part, eventful[0])
        if obj:
            kind = "computers" if isinstance(obj, Computer) else "parts"
            add("Most written about", named(obj),
                f"{eventful[1]} entries in its history",
                f"/{kind}/{obj.asset_id}")

    lonely = [t for t, n, _v in st["types"] if n == 1]
    if lonely:
        # One is a thing; several is a count. "1 — categories with a single example:
        # Peripheral" says the same word twice and names it in the small print.
        add("One of a kind",
            entry.type_label(lonely[0]) if len(lonely) == 1 else str(len(lonely)),
            "the only one in the register" if len(lonely) == 1 else
            "categories with a single example: "
            + ", ".join(entry.type_label(t) for t in lonely[:3]),
            f"/browse?f=type&v={quote(lonely[0])}")

    # How many things have no portrait used to be a figure in here. It is on the
    # page in its own right now, above the tiles: a work queue that only appears on
    # some visits is not a work queue. It is not in the pool as well, because drawn
    # beside the standing line it would read as the shuffle repeating itself -- the
    # very fault the `seen` guard in gui_stats exists to prevent, and one that guard
    # cannot catch, since it compares tiles with each other and not with the rest of
    # the page. What is photographed is still spoken for here, twice.
    shots = st["portraits"]
    if shots:
        aid, n = max(shots.items(), key=lambda kv: (kv[1], kv[0]))
        obj = db.get(Computer, aid) or db.get(Part, aid)
        if obj and n > 1:
            kind = "computers" if isinstance(obj, Computer) else "parts"
            add("Most photographed", named(obj), f"{n} pictures of it",
                f"/{kind}/{obj.asset_id}")
    if shots and st["photos"] and len(held_ids):
        add("Photographs per thing", f"{st['photos'] / len(held_ids):.1f}",
            f"{st['photos']} pictures of {len(held_ids)} things", "/browse?f=photos")

    maker_counts = _held(db.query(Part.manufacturer, func.count(Part.asset_id))
                         .filter(Part.manufacturer.isnot(None),
                                 Part.manufacturer != ""), Part) \
        .group_by(Part.manufacturer).all()
    if maker_counts:
        add("Names on the parts", str(len(maker_counts)),
            "distinct makers in the register", "/browse?f=parts")
    singles = [m for m, n in maker_counts if n == 1]
    if len(singles) >= 3:
        add("Makers represented once", str(len(singles)),
            f"of {len(maker_counts)}, a single part each: "
            + ", ".join(sorted(singles)[:3]), "/browse?f=parts")

    # Counted in Python rather than grouped by YEAR(): the app runs on SQLite for
    # local development as well as on MariaDB, and that function is not portable.
    # At this size it is a few dozen dates either way.
    arrivals = Counter(d.year for (d,) in
                       _held(db.query(Part.acquired_date)
                             .filter(Part.acquired_date.isnot(None)), Part))
    if arrivals:
        year, n = max(arrivals.items(), key=lambda kv: (kv[1], kv[0]))
        if n > 1:
            add("Busiest year for buying", str(year), f"{n} parts arrived",
                "/browse?f=held")

    source = (_held(db.query(Part.source, func.count(Part.asset_id))
                    .filter(Part.source.isnot(None), Part.source != ""), Part)
              .group_by(Part.source)
              .order_by(func.count(Part.asset_id).desc()).first())
    if source and source[1] > 1:
        add("Where things come from", source[0], f"{source[1]} parts from there",
            f"/browse?f=source&v={quote(source[0])}")

    caps = [(kb, pid) for pid, kb in
            _held(db.query(StorageSpec.part_id, StorageSpec.capacity_kb)
                  .join(Part, Part.asset_id == StorageSpec.part_id)
                  .filter(StorageSpec.capacity_kb.isnot(None),
                          StorageSpec.capacity_kb > 0), Part)]
    if len(caps) >= 2:
        big, small = max(caps), min(caps)
        add("Biggest and smallest disk",
            f"{entry.fmt_kb(big[0], True)} / {entry.fmt_kb(small[0], True)}",
            f"a factor of {round(big[0] / small[0]):,} between them",
            "/browse?f=storage")

    chips = (_held(db.query(ComputerRamChip.computer_id,
                            func.sum(ComputerRamChip.count))
                   .join(Computer,
                         Computer.asset_id == ComputerRamChip.computer_id), Computer)
             .group_by(ComputerRamChip.computer_id)
             .order_by(func.sum(ComputerRamChip.count).desc()).first())
    if chips:
        machine = db.get(Computer, chips[0])
        if machine:
            add("Most memory chips", named(machine),
                f"{int(chips[1])} of them in one machine",
                f"/computers/{machine.asset_id}")

    longest, holder, holder_kind = 0, None, ""
    for model, kind in ((Computer, "computers"), (Part, "parts")):
        for obj in _held(db.query(model), model):
            name = named(obj)
            if len(name) > longest:
                longest, holder, holder_kind = len(name), obj, kind
    if holder and longest > 20:
        add("Longest name in the register", f"{longest} characters", named(holder),
            f"/{holder_kind}/{holder.asset_id}")

    # Not when this year is also the busiest: two tiles saying "48 parts, 2026" in
    # one draw is the shuffle looking like it is broken.
    if arrivals.get(this_year) and max(arrivals, key=arrivals.get) != this_year:
        add(f"Arrived in {this_year}", str(arrivals[this_year]),
            "parts so far this year", "/browse?f=held")

    # --- what the drives are like -------------------------------------------
    # These read the typed storage columns, which is where the per-kind form now
    # files everything a drive is asked (see entry.STORAGE_ASKS).

    def storage_rank(column, kind=None):
        """(value, count) for one storage column, commonest first, held parts only."""
        q = _held(db.query(column, func.count(StorageSpec.part_id))
                  .join(Part, Part.asset_id == StorageSpec.part_id)
                  .filter(column.isnot(None), column != ""), Part)
        if kind:
            q = q.filter(StorageSpec.kind == kind)
        return sorted(q.group_by(column).all(), key=lambda r: (-r[1], r[0]))

    ifaces = storage_rank(StorageSpec.interface)
    if ifaces:
        total = sum(n for _i, n in ifaces)
        add("How a drive usually attaches", ifaces[0][0],
            f"{ifaces[0][1]} of {total} drives", "/browse?f=storage")
    if len(ifaces) >= 3:
        add("Ways of attaching a drive", str(len(ifaces)),
            "in use here: " + ", ".join(i for i, _n in ifaces[:4])
            + ("…" if len(ifaces) > 4 else ""), "/browse?f=storage")

    discs = storage_rank(StorageSpec.media, entry.OPTICAL_KIND)
    if discs and discs[0][1] > 1:
        add("The usual disc", discs[0][0], f"{discs[0][1]} optical drives take it",
            "/browse?f=storage")

    kinds = storage_rank(StorageSpec.kind)
    if len(kinds) >= 2:
        add("What the drives are", str(sum(n for _k, n in kinds)),
            ", ".join(f"{n} × {k}" for k, n in kinds),
            "/browse?f=storage")

    disk_caps = [kb for (kb,) in
                 _held(db.query(StorageSpec.capacity_kb)
                       .join(Part, Part.asset_id == StorageSpec.part_id)
                       .filter(StorageSpec.kind == entry.DISK_KIND,
                               StorageSpec.capacity_kb.isnot(None),
                               StorageSpec.capacity_kb > 0), Part)]
    if len(disk_caps) >= 2:
        add("Every hard disk added up", _big_total(sum(disk_caps)),
            f"across {len(disk_caps)} of them", "/browse?f=storage")

    # The 137 GiB wall, as reported by the drive: a disk bigger than 8.4 GiB has to
    # lie about its geometry, and 16383/16/63 is the lie they all tell.
    clamped = _held(db.query(func.count(StorageSpec.part_id))
                    .join(Part, Part.asset_id == StorageSpec.part_id)
                    .filter(StorageSpec.chs_c == 16383, StorageSpec.chs_h == 16,
                            StorageSpec.chs_s == 63), Part).scalar() or 0
    if clamped:
        add("Drives that lie about their shape", str(clamped),
            "reporting the ATA limit of 16383/16/63 rather than their real geometry",
            "/browse?f=storage")

    shades = storage_rank(StorageSpec.colour)
    if shades:
        add("The usual shade", shades[0][0],
            f"{shades[0][1]} of {sum(n for _s, n in shades)} bezels on file",
            "/browse?f=storage")
    yellowed = storage_rank(StorageSpec.yellowing)
    if yellowed:
        n = sum(n for _y, n in yellowed)
        add("Bezels gone yellow", str(n),
            f"most often {yellowed[0][0].lower()}", "/browse?f=storage")

    # --- and the shape of the whole thing -----------------------------------

    years = _all_years(db)
    if years:
        decades = Counter((y // 10) * 10 for y in years)
        decade, n = max(decades.items(), key=lambda kv: (kv[1], kv[0]))
        if len(decades) > 1:
            add("Best represented decade", f"{decade}s", f"{n} things made then",
                "/browse?f=year")

    for label, pick, blurb in (
            ("The oldest thing here", min, "the earliest year on anything"),
            ("The newest thing here", max, "the latest year on anything")):
        dated = []
        for model, kind in ((Computer, "computers"), (Part, "parts")):
            for obj in _held(db.query(model).filter(model.year.isnot(None)), model):
                dated.append((obj.year, kind, obj))
        if dated:
            year, kind, obj = pick(dated, key=lambda d: d[0])
            add(label, str(year), f"{named(obj)} — {blurb}",
                f"/{kind}/{obj.asset_id}")

    untested = _held(db.query(func.count(Part.asset_id))
                     .filter(Part.condition == "Untested"), Part).scalar() or 0
    if untested and st["n_parts"]:
        add("Never tested", str(untested),
            f"{round(100 * untested / st['n_parts'])}% of the parts, plugged into "
            "nothing yet", "/browse?f=condition&v=Untested")

    # The rest of the pool, by theme. Split out because one function of forty
    # figures had stopped being readable, not because these are a lesser sort of
    # figure: the page shuffles the whole pool together and does not know which
    # function a tile came from.
    out += _facts_boards(db, st)
    out += _facts_cards(db, st)
    out += _facts_drives(db, st)
    out += _facts_machines(db, st)
    out += _facts_ages(db, st, this_year)
    out += _facts_provenance(db, st)
    out += _facts_register(db, st)
    out += _facts_projects(db, st)
    out += _facts_condition(db, st)
    return out
# --- the pointless department, by theme -------------------------------------
# The pool above grew out of one function, and past about forty figures that
# stopped being readable. What follows is the same thing in themed groups: each
# returns a list of figures and is skippable on its own, and each keeps the rules
# the pool has always had -- held items only (see _held), a figure omitted rather
# than shown empty, and quantities read from typed columns rather than parsed back
# out of text.
#
# A figure that is about the whole register rather than about any set of items
# passes no href. The tiles have always been links; a handful of them now are not,
# because "1327 entries in the register" leads nowhere the gallery can show, and a
# link to everything would be a link that lied about what it counted.

def _fact(k, v, s, href=None):
    """One figure for the pool, in the shape the template reads."""
    return {"k": k, "v": v, "s": s, "href": href}


def _named(obj):
    return entry.display_name(to_dict(obj))


def _spec_rank(db, model, column, *conds):
    """(value, count) for one text column of a spec table, commonest first.

    The join back to `parts` is not decoration: a spec row has no disposed flag of
    its own, so without it a binned board's chipset would still be a chipset the
    collection claims to hold."""
    q = (db.query(column, func.count(column))
         .join(Part, Part.asset_id == model.part_id)
         .filter(column.isnot(None), column != ""))
    for c in conds:
        q = q.filter(c)
    return sorted(_held(q, Part).group_by(column).all(), key=lambda r: (-r[1], r[0]))


def _spec_count(db, model, *conds):
    """How many held parts have a spec row matching."""
    q = db.query(func.count(model.part_id)).join(Part, Part.asset_id == model.part_id)
    for c in conds:
        q = q.filter(c)
    return _held(q, Part).scalar() or 0


def _commas(db, model, column):
    """A Counter over a text column that holds a comma-separated list.

    Video connectors are written 'VGA, EGA, Composite' -- one field, several
    answers -- so counting the column whole would file that card under a fourth
    kind of output rather than under the three it has. Ports and buses have proper
    child tables and are counted there; this is for the fields that do not."""
    out = Counter()
    for (v,) in _held(db.query(column).join(Part, Part.asset_id == model.part_id)
                      .filter(column.isnot(None), column != ""), Part):
        for one in (x.strip() for x in v.split(",")):
            if one:
                out[one] += 1
    return out


def _facts_boards(db, st):
    """Figures about motherboards: what shape they are, whose BIOS they answer to,
    and what can be plugged into them.

    The board is the part everything else in a machine hangs off, and it is the
    best represented category in the register, so it carries more of these than
    anything else does."""
    out = []
    shapes = _spec_rank(db, MotherboardSpec, MotherboardSpec.form_factor)
    if shapes:
        n_shaped = sum(n for _s, n in shapes)
        # "proprietary" -- the last of entry.MOBO_FORM_FACTORS -- is not a form
        # factor so much as the absence of one, and it is the commonest answer here.
        # Counted by prefix, so whatever was typed after the word lands in the same
        # pile; everything else counts as a named shape, including the spellings the
        # canonical list does not have ("Baby AT", "PC104"), because a shape someone
        # wrote down is still a shape.
        odd = sum(n for s, n in shapes if s.lower().startswith("proprietary"))
        if odd:
            out.append(_fact("Boards that fit nothing else", str(odd),
                             f"of {n_shaped} with a shape recorded, built to a plan "
                             "of their maker's own", "/browse?f=boards"))
        named_shapes = [(s, n) for s, n in shapes
                        if not s.lower().startswith("proprietary")]
        if named_shapes:
            out.append(_fact("The usual board shape", named_shapes[0][0],
                             f"{named_shapes[0][1]} boards, the commonest of the "
                             f"{len(named_shapes)} named shapes here",
                             f"/browse?f=formfactor&v={quote(named_shapes[0][0])}"))

    bios = _spec_rank(db, MotherboardSpec, MotherboardSpec.bios)
    if bios:
        out.append(_fact("Whose BIOS it usually is", bios[0][0],
                         f"{bios[0][1]} of the {sum(n for _b, n in bios)} boards that say",
                         f"/browse?f=bios&v={quote(bios[0][0])}"))

    fam = _spec_rank(db, MotherboardSpec, MotherboardSpec.cpu_family)
    if fam:
        out.append(_fact("The commonest class of board", fam[0][0],
                         f"{fam[0][1]} of the {sum(n for _f, n in fam)} that name one",
                         f"/browse?f=family&v={quote(fam[0][0])}"))

    chipsets = _spec_rank(db, MotherboardSpec, MotherboardSpec.chipset)
    if len(chipsets) >= 3:
        out.append(_fact("Chipsets named", str(len(chipsets)),
                         f"across {sum(n for _c, n in chipsets)} boards — hardly any "
                         "two of them agree", "/browse?f=boards"))

    cache = _held(db.query(func.sum(MotherboardSpec.cache_kb),
                           func.count(MotherboardSpec.part_id))
                  .join(Part, Part.asset_id == MotherboardSpec.part_id)
                  .filter(MotherboardSpec.cache_kb.isnot(None),
                          MotherboardSpec.cache_kb > 0), Part).first()
    if cache and cache[0]:
        out.append(_fact("Cache on the boards, added up",
                         entry.fmt_kb(int(cache[0]), True),
                         f"across the {cache[1]} boards that have any",
                         "/browse?f=cache"))

    onboard = _spec_count(db, MotherboardSpec,
                          MotherboardSpec.onboard_video.isnot(None),
                          MotherboardSpec.onboard_video != "")
    if onboard:
        out.append(_fact("Boards with the video already on them", str(onboard),
                         "no card required, which was once the remarkable part",
                         "/browse?f=onboardvideo"))

    boards = {a for (a,) in _held(db.query(MotherboardSpec.part_id)
                                  .join(Part, Part.asset_id == MotherboardSpec.part_id),
                                  Part)}
    slotted = {a for (a,) in db.query(PartSlot.part_id).distinct()}
    bare = boards - slotted
    if bare and boards:
        out.append(_fact("Boards with nowhere to expand", str(len(bare)),
                         f"of {len(boards)}: whatever they do, they do already",
                         "/browse?f=noslots"))

    per_board = sorted(_held(db.query(PartSlot.part_id, func.sum(PartSlot.count))
                             .join(Part, Part.asset_id == PartSlot.part_id), Part)
                       .group_by(PartSlot.part_id).all(), key=lambda r: -r[1])
    if per_board:
        top = int(per_board[0][1])
        tied = [p for p, n in per_board if int(n) == top]
        holder = db.get(Part, tied[0])
        out.append(_fact("Most slots on one board", str(top),
                         f"shared by {len(tied)} boards" if len(tied) > 1
                         else _named(holder),
                         "/browse?f=slots" if len(tied) > 1
                         else f"/parts/{holder.asset_id}"))

    # ISA outlasted its own replacements: a board here is likelier to have an ISA
    # slot than any other kind, forty years after the first one.
    isa = _held(db.query(func.sum(PartSlot.count))
                .join(Part, Part.asset_id == PartSlot.part_id)
                .filter(PartSlot.bus.like("%ISA%")), Part).scalar() or 0
    if isa and st["slots"]:
        out.append(_fact("Slots that are ISA", str(int(isa)),
                         f"of {st['slots']}, {round(100 * int(isa) / st['slots'])}% — "
                         "the bus that would not die", "/browse?f=slots"))

    sockets = sorted(_held(db.query(PartRamSlot.slot_type, func.sum(PartRamSlot.count))
                           .join(Part, Part.asset_id == PartRamSlot.part_id), Part)
                     .group_by(PartRamSlot.slot_type).all(),
                     key=lambda r: (-r[1], r[0]))
    if sockets:
        total = int(sum(n for _s, n in sockets))
        holders = _held(db.query(func.count(func.distinct(PartRamSlot.part_id)))
                        .join(Part, Part.asset_id == PartRamSlot.part_id),
                        Part).scalar() or 0
        out.append(_fact("Memory sockets", str(total),
                         f"on {holders} boards, filled or empty",
                         "/browse?f=ramslots"))
        out.append(_fact("The usual memory socket", sockets[0][0],
                         f"{int(sockets[0][1])} of {total} sockets",
                         f"/browse?f=ramslot&v={quote(sockets[0][0])}"))
        thirty = next((int(n) for s, n in sockets if s.startswith("30-pin")), 0)
        if thirty:
            out.append(_fact("30-pin SIMM sockets", str(thirty),
                             "filled four to a bank on a 32-bit board, two on a 286",
                             "/browse?f=ramslot&v=" + quote("30-pin SIMM")))
    return out


def _facts_cards(db, st):
    """Figures about the things that go in the slots: video, sound, network and I/O.

    These read the per-type spec tables, which is where the typed form files what a
    card is asked. The four tables share the shape of several columns -- `interface`
    for the bus, `chip` for the silicon -- so the questions that span all four are
    counted in one pass over them at the end, rather than four times over."""
    out = []

    # --- what a graphics card is ------------------------------------------
    outputs = _commas(db, VideoSpec, VideoSpec.connector)
    if outputs:
        best, n = outputs.most_common(1)[0]
        out.append(_fact("Video outputs counted", str(sum(outputs.values())),
                         f"most often {best}, on {n} cards",
                         "/browse?f=type&v=video"))
    multi = _spec_count(db, VideoSpec, VideoSpec.connector.like("%,%"))
    if multi:
        out.append(_fact("Cards that hedge their bets", str(multi),
                         "more than one kind of output on the same bracket",
                         "/browse?f=type&v=video"))
    # Cards whose outputs a VGA monitor will not take: MDA, CGA, EGA and composite
    # are all a different signal on a different plug, and a card with none of the
    # later ones is a card from before the standard that outlasted them.
    prevga = _spec_count(db, VideoSpec, VideoSpec.connector.isnot(None),
                         VideoSpec.connector != "",
                         ~VideoSpec.connector.like("%VGA%"),
                         ~VideoSpec.connector.like("%DVI%"))
    if prevga:
        out.append(_fact("Graphics cards from before VGA", str(prevga),
                         "nothing a VGA monitor would accept", "/browse?f=prevga"))

    chips = _spec_rank(db, VideoSpec, VideoSpec.chip)
    if len(chips) >= 3:
        out.append(_fact("Graphics chips named", str(len(chips)),
                         f"across {sum(n for _c, n in chips)} cards",
                         "/browse?f=type&v=video"))
        if chips[0][1] > 1:
            out.append(_fact("The commonest graphics chip", chips[0][0],
                             f"{chips[0][1]} cards carry it",
                             "/browse?f=type&v=video"))

    vram = [kb for (kb,) in
            _held(db.query(VideoSpec.memory_kb)
                  .join(Part, Part.asset_id == VideoSpec.part_id)
                  .filter(VideoSpec.memory_kb.isnot(None),
                          VideoSpec.memory_kb > 0), Part)]
    if vram:
        out.append(_fact("Video memory, everything added up",
                         entry.fmt_kb(sum(vram), True),
                         f"across the {len(vram)} cards that state any",
                         "/browse?f=vram"))
        # The commonest amount, not the total: the same question the register asks
        # of a machine's memory, and ties share the honour there for the same reason.
        sizes = Counter(vram)
        top = max(sizes.values())
        tied = sorted(kb for kb, n in sizes.items() if n == top)
        out.append(_fact("The usual amount of video memory",
                         " / ".join(entry.fmt_kb(kb, True) for kb in tied),
                         f"{top} cards" + (" each" if len(tied) > 1 else "")
                         + f", of {len(vram)} that state any",
                         "/browse?f=vramsize&v=" + ",".join(str(kb) for kb in tied)))
    if len(vram) >= 2 and max(vram) > min(vram):
        out.append(_fact("Biggest and smallest video memory",
                         f"{entry.fmt_kb(max(vram), True)} / "
                         f"{entry.fmt_kb(min(vram), True)}",
                         f"a factor of {round(max(vram) / min(vram)):,} between them",
                         "/browse?f=vram"))

    # --- and of the other three -------------------------------------------
    sound = _spec_rank(db, SoundSpec, SoundSpec.chip)
    if sound and sound[0][1] > 1:
        out.append(_fact("The commonest sound chip", sound[0][0],
                         f"{sound[0][1]} of the {sum(n for _c, n in sound)} cards "
                         "that name one", "/browse?f=type&v=sound"))
    nets = _spec_rank(db, NetworkSpec, NetworkSpec.interface)
    if len(nets) >= 2:
        out.append(_fact("Network cards, either side of the changeover",
                         f"{nets[0][1]} / {nets[1][1]}",
                         f"{nets[0][0]} against {nets[1][0]}",
                         "/browse?f=type&v=network"))

    # --- and what is true of all four -------------------------------------
    # One pass, four counters: how many cards there are at all, how many say which
    # bus, how many of those are ISA, and how many never had their chip written
    # down. Counted together because the figures below have to agree about how many
    # cards there are -- read as two tiles in one draw, 165 and 166 look like a bug.
    ISA_BUSES = ("8-bit ISA", "16-bit ISA", "ISA")
    n_cards = named_bus = on_isa = chip_blank = 0
    for model in (VideoSpec, SoundSpec, NetworkSpec, IoSpec):
        n_cards += _spec_count(db, model)
        named_bus += _spec_count(db, model, model.interface.isnot(None),
                                 model.interface != "")
        on_isa += _spec_count(db, model, model.interface.in_(ISA_BUSES))
        chip_blank += _spec_count(db, model, (model.chip.is_(None))
                                  | (model.chip == ""))

    # The whole changeover in one figure: a card here is still likelier to be ISA
    # than anything else, PCI having arrived late enough that most of this was
    # already on the shelf.
    if on_isa and named_bus:
        out.append(_fact("Cards that never left ISA", str(on_isa),
                         f"of {named_bus} with a bus recorded, "
                         f"{round(100 * on_isa / named_bus)}% of them",
                         "/browse?f=cards"))
    # Whose chip it is goes unrecorded far more often on a serial card than on a
    # graphics card, and the figure says which way round that is.
    if chip_blank and n_cards:
        out.append(_fact("Cards whose chip nobody has written down", str(chip_blank),
                         f"of {n_cards}: mostly the serial and network cards, where "
                         "nobody thinks to look", "/browse?f=nochip"))
    # Whimsy, and it says so: cards and slots are counted honestly and then set
    # against each other as though any card went in any slot, which no card does.
    # Only while there are slots to spare -- the other way round is a different
    # remark about a different collection, and this one would read as nonsense.
    if n_cards and st["slots"] and st["slots"] > n_cards:
        out.append(_fact("If every card were plugged in",
                         f"{st['slots'] - n_cards} slots",
                         f"would still be empty — {n_cards} cards against "
                         f"{st['slots']} slots, never mind which bus fits which",
                         "/browse?f=cards"))

    # --- ports, which are on the boards as well as on the cards -----------
    ports = _held(db.query(func.sum(PartPort.count),
                           func.count(func.distinct(PartPort.part_id)))
                  .join(Part, Part.asset_id == PartPort.part_id), Part).first()
    if ports and ports[0]:
        # The ranked list further down the page is capped, so this total is bigger
        # than its bars add up to. Said out loud -- but only when it is true, which
        # is why it is compared against that list rather than asserted about it.
        shown = sum(n for _p, n, _v in st["ports"])
        out.append(_fact("Ports counted", str(int(ports[0])),
                         f"on {ports[1]} boards and cards"
                         + (f" — the list below ranks only the commonest "
                            f"{len(st['ports'])}" if int(ports[0]) > shown else ""),
                         "/browse?f=ports"))
    per_carrier = sorted(_held(db.query(PartPort.part_id, func.sum(PartPort.count))
                               .join(Part, Part.asset_id == PartPort.part_id), Part)
                         .group_by(PartPort.part_id).all(), key=lambda r: -r[1])
    if per_carrier and int(per_carrier[0][1]) > 1:
        holder = db.get(Part, per_carrier[0][0])
        if holder:
            out.append(_fact("Most ports on one thing", str(int(per_carrier[0][1])),
                             _named(holder), f"/parts/{holder.asset_id}"))
    return out


def _facts_drives(db, st):
    """Figures about drives beyond the totals above: how they attach, how fast they
    turn, and what shape they claim to be."""
    out = []
    # Interfaces that were obsolete before most of this collection was made, and
    # are still represented in it. Named explicitly rather than inferred: what
    # makes MFM historic is not anything the database can work out.
    GONE = ("MFM", "RLL", "ESDI", "XTA")
    old = _spec_rank(db, StorageSpec, StorageSpec.interface,
                     StorageSpec.interface.in_(GONE))
    if old:
        out.append(_fact("Drives on an interface nobody uses",
                         str(sum(n for _i, n in old)),
                         ", ".join(i for i, _n in old) + " — all of them dead ends",
                         "/browse?f=legacydisk"))

    rpm = sorted(_held(db.query(StorageSpec.speed_rpm)
                       .join(Part, Part.asset_id == StorageSpec.part_id)
                       .filter(StorageSpec.speed_rpm.isnot(None),
                               StorageSpec.speed_rpm > 0), Part).all())
    if rpm:
        out.append(_fact("The fastest spindle here", f"{max(rpm)[0]:,} rpm",
                         f"of the {len(rpm)} drives that admit to a speed",
                         "/browse?f=rpm"))

    speeds = sorted(x for (x,) in
                    _held(db.query(StorageSpec.speed_x)
                          .join(Part, Part.asset_id == StorageSpec.part_id)
                          .filter(StorageSpec.speed_x.isnot(None),
                                  StorageSpec.speed_x > 0), Part))
    if len(speeds) >= 2 and speeds[-1] > speeds[0]:
        out.append(_fact("Fastest and slowest optical drive",
                         f"{speeds[-1]}× / {speeds[0]}×",
                         f"a factor of {round(speeds[-1] / speeds[0])} between them, "
                         "and about ten years", "/browse?f=optical"))

    # Whimsy, in the manner of every floppy at once: a real column, added up for no
    # reason anybody needs. Cylinders are the one part of CHS that varies enough to
    # be worth summing.
    geom = _held(db.query(func.count(StorageSpec.part_id), func.sum(StorageSpec.chs_c))
                 .join(Part, Part.asset_id == StorageSpec.part_id)
                 .filter(StorageSpec.chs_c.isnot(None), StorageSpec.chs_c > 0),
                 Part).first()
    if geom and geom[1]:
        out.append(_fact("Cylinders, added up", f"{int(geom[1]):,}",
                         f"across the {geom[0]} drives that state their geometry",
                         "/browse?f=geometry"))

    flash = _held(db.query(func.sum(ComputerDrive.count))
                  .join(Computer, Computer.asset_id == ComputerDrive.computer_id)
                  .filter(ComputerDrive.kind.in_(("CF", "SD"))), Computer).scalar()
    if flash:
        out.append(_fact("Flash standing in for a disk", str(int(flash)),
                         "cards in machines that were built before the format",
                         "/browse?f=flash"))
    return out


def _facts_machines(db, st):
    """Figures about the whole machines. There are far fewer of these than there are
    parts, so anything counted here is counted against a small number and says so."""
    out = []
    n = st["n_computers"]

    ram = Counter(kb for (kb,) in
                  _held(db.query(Computer.installed_ram_kb)
                        .filter(Computer.installed_ram_kb.isnot(None)), Computer))
    # 640 KiB is the line DOS drew and a great many machines stopped exactly on.
    if ram.get(640):
        out.append(_fact("The 640 KiB club", str(ram[640]),
                         "machines fitted with exactly as much as DOS could use",
                         "/browse?f=ram&v=640"))
    if len(ram) >= 2:
        least, most = min(ram), max(ram)
        out.append(_fact("The least memory in anything", entry.fmt_kb(least, True),
                         f"and the most is {entry.fmt_kb(most, True)}, "
                         f"a factor of {round(most / least):,}",
                         "/browse?f=ramfitted"))

    os_rank = sorted(_held(db.query(Computer.os, func.count(Computer.asset_id))
                           .filter(Computer.os.isnot(None), Computer.os != ""),
                           Computer).group_by(Computer.os).all(),
                     key=lambda r: (-r[1], r[0]))
    if os_rank and n:
        out.append(_fact("Machines with an operating system on them",
                         str(sum(x for _o, x in os_rank)),
                         f"of {n}; the rest are bare metal as they stand",
                         "/browse?f=os"))
    dos = _held(db.query(func.count(Computer.asset_id))
                .filter(Computer.os.like("%DOS%")), Computer).scalar() or 0
    if dos:
        out.append(_fact("Machines running DOS of some sort", str(dos),
                         "MS-DOS, FreeDOS or the like, as recorded",
                         "/browse?f=dos"))

    cpus = sorted(_held(db.query(Computer.cpu, func.count(Computer.asset_id))
                        .filter(Computer.cpu.isnot(None), Computer.cpu != ""),
                        Computer).group_by(Computer.cpu).all(),
                  key=lambda r: (-r[1], r[0]))
    if cpus and cpus[0][1] > 1:
        out.append(_fact("The commonest processor", cpus[0][0],
                         f"{cpus[0][1]} of the {sum(x for _c, x in cpus)} machines "
                         "that name one", "/browse?f=cpu"))

    chassis = sorted(_held(db.query(Computer.chassis, func.count(Computer.asset_id))
                           .filter(Computer.chassis.isnot(None),
                                   Computer.chassis != ""), Computer)
                     .group_by(Computer.chassis).all(),
                     key=lambda r: (-r[1], r[0]))
    if chassis:
        out.append(_fact("What shape the machines are", chassis[0][0],
                         f"{chassis[0][1]} of {sum(x for _c, x in chassis)}, and "
                         f"{len(chassis) - 1} other shapes besides",
                         f"/browse?f=chassis&v={quote(chassis[0][0])}"))
    # Portable in the sense the word had at the time, which is to say heavy.
    portable = sum(x for c, x in chassis if c.lower() in ("laptop", "luggable"))
    if portable:
        out.append(_fact("Portable, in the period sense", str(portable),
                         "laptops and luggables, the latter being portable only in "
                         "that it had a handle", "/browse?f=portable"))

    known = db.query(func.count(func.distinct(AssetVariant.asset_id))).scalar() or 0
    if known and n:
        out.append(_fact("Machines the catalogue knows", str(known),
                         f"of {n} filed as a model it can name",
                         "/browse?f=variant"))

    fitted_in = {c for (c,) in _held(db.query(Part.computer_id)
                                     .filter(Part.computer_id.isnot(None)), Part)}
    all_machines = {a for (a,) in _held(db.query(Computer.asset_id), Computer)}
    empty = all_machines - fitted_in
    if empty and all_machines:
        out.append(_fact("Machines with nothing in them", str(len(empty)),
                         f"of {len(all_machines)}: nothing tagged is fitted to them",
                         "/browse?f=emptymachines"))

    bench = _held(db.query(func.count(Computer.asset_id))
                  .filter(Computer.topbench.isnot(None)), Computer).scalar() or 0
    if bench and n:
        out.append(_fact("Machines actually benchmarked", str(bench),
                         f"of {n}: TopBench has to be run, and mostly has not been",
                         "/browse?f=benchmarked"))
    return out


def _facts_ages(db, st, this_year):
    """Figures about when all this was made, and about the gaps between the dates on
    things that ended up in the same box."""
    out = []
    years = _all_years(db)
    if years:
        span = max(years) - min(years) + 1
        if span > len(set(years)):
            out.append(_fact("Years represented", str(len(set(years))),
                             f"of the {span} the collection spans — "
                             f"{span - len(set(years))} with nothing made in them",
                             "/browse?f=year"))
        modern = sum(1 for y in years if y >= 2000)
        if modern:
            out.append(_fact("Made this century", str(modern),
                             f"of the {len(years)} things with a year on them",
                             "/browse?f=century"))
        recent = sum(1 for y in years if y >= this_year - 10)
        if recent:
            out.append(_fact("Made in the last ten years", str(recent),
                             "new parts for old machines, still being made",
                             "/browse?f=recent"))

    machine_years = [y for (y,) in _held(db.query(Computer.year)
                                         .filter(Computer.year.isnot(None)),
                                         Computer)]
    part_years = [y for (y,) in _held(db.query(Part.year)
                                      .filter(Part.year.isnot(None)), Part)]
    if machine_years and part_years:
        mm, mp = round(sum(machine_years) / len(machine_years)), \
            round(sum(part_years) / len(part_years))
        if mm != mp:
            older = "machines" if mm < mp else "parts"
            out.append(_fact(f"The {older} are the older half", f"{mm} / {mp}",
                             "average year of a machine against a part",
                             "/browse?f=year"))

    # Machines as well as parts: "thing" means both everywhere else on this page,
    # and a working machine of 1981 would be a strange one to leave out of a figure
    # about the oldest thing that still works.
    working = []
    for model, kind in ((Computer, "computers"), (Part, "parts")):
        oldest = _held(db.query(model).filter(model.year.isnot(None),
                                              model.condition == "Working"),
                       model).order_by(model.year).first()
        if oldest:
            working.append((oldest.year, oldest, kind))
    if working:
        year, obj, kind = min(working, key=lambda w: w[0])
        out.append(_fact("The oldest thing that still works", str(year),
                         _named(obj), f"/{kind}/{obj.asset_id}"))

    # The gap between a part's year and its machine's. Both dates in one row,
    # because the figure is the difference and a difference needs both ends.
    pairs = _held(db.query(Part, Computer)
                  .join(Computer, Computer.asset_id == Part.computer_id)
                  .filter(Part.year.isnot(None), Computer.year.isnot(None),
                          Computer.disposed.is_(False)), Part).all()
    if pairs:
        ahead = [(p.year - c.year, p, c) for p, c in pairs if p.year > c.year]
        if ahead:
            gap, p, c = max(ahead, key=lambda r: r[0])
            out.append(_fact("The biggest anachronism", f"{gap} years",
                             f"{_named(p)} of {p.year}, fitted to a machine from "
                             f"{c.year}", f"/computers/{c.asset_id}"))
        together = sum(1 for p, c in pairs if p.year == c.year)
        if together:
            out.append(_fact("Parts as old as their machine", str(together),
                             f"of {len(pairs)} where both dates are known, made the "
                             "same year as the thing they are in",
                             "/browse?f=born"))
        before = sum(1 for p, c in pairs if p.year < c.year)
        if before:
            out.append(_fact("Parts older than their machine", str(before),
                             "already out of date the day they were fitted",
                             "/browse?f=older"))
    return out


def _facts_provenance(db, st):
    """Where things came from and when they turned up. Provenance is the field
    least often filled in, and the figure about how often is one of the more
    honest ones here."""
    out = []
    nowhere = _held(db.query(func.count(Part.asset_id))
                    .filter((Part.source == "") | (Part.source.is_(None))),
                    Part).scalar() or 0
    if nowhere and st["n_parts"]:
        out.append(_fact("Parts with no idea where they came from", str(nowhere),
                         f"{round(100 * nowhere / st['n_parts'])}% of them: no source "
                         "recorded at all", "/browse?f=nosource"))
    # Two conventions of this register's source field rather than anything the
    # schema knows: an order number is written "eBay order no. ...", and something
    # built here is "Self-made". Both figures simply stand down on a register that
    # writes provenance some other way, which is what every figure here does.
    bought = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.source.like("eBay%")), Part).scalar() or 0
    if bought:
        out.append(_fact("Bought from strangers", str(bought),
                         "traced to an eBay order number",
                         "/browse?f=sourcelike&v=eBay"))
    made = _held(db.query(func.count(Part.asset_id))
                 .filter(Part.source.like("Self-made%")), Part).scalar() or 0
    if made:
        out.append(_fact("Made here rather than bought", str(made),
                         "built on the bench it sits on",
                         "/browse?f=sourcelike&v=Self-made"))

    arrivals = [d for (d,) in _held(db.query(Part.acquired_date)
                                    .filter(Part.acquired_date.isnot(None)), Part)]
    if arrivals and st["n_parts"]:
        out.append(_fact("Parts with an arrival date", str(len(arrivals)),
                         f"of {st['n_parts']}; the rest were simply there one day",
                         "/browse?f=held"))
        # Ties share the honour, as they do for the usual amount of memory: two days
        # with nine arrivals each are both the day things arrive.
        days = Counter(d.strftime("%A") for d in arrivals)
        top = max(days.values())
        winners = sorted(d for d, x in days.items() if x == top)
        if len(winners) == 1:
            out.append(_fact(f"Things arrive on a {winners[0]}", str(top),
                             "more of them than on any other day", "/browse?f=held"))
        else:
            out.append(_fact("The day things arrive", " / ".join(winners),
                             f"tied on {top} arrivals each", "/browse?f=held"))
        busiest, count = Counter(arrivals).most_common(1)[0]
        if count > 1:
            out.append(_fact("The busiest single day", str(count),
                             f"parts all dated {busiest}", "/browse?f=held"))
    return out


def _facts_register(db, st):
    """Figures about the register rather than about the hardware: how much has been
    written down, how much has been photographed, and how new all the writing is.

    These are the figures with no gallery view behind them -- an entry in a
    history is not an item -- so the first few pass no link at all.

    The entry counts are also the one place _held does not apply: they count what
    has been written, and a note about something since disposed was still written.
    The figures about parts below are about the collection again, and do."""
    out = []
    entries = db.query(func.count(LogEntry.id)).scalar() or 0
    started = db.query(func.min(LogEntry.created_at)).scalar()
    if entries and started:
        days = max((date.today() - started.date()).days, 1)
        out.append(_fact("The register is younger than everything in it",
                         f"{days} days",
                         f"{entries:,} entries written since {started.date()}"))
    kinds = dict(db.query(LogEntry.kind, func.count(LogEntry.id))
                 .group_by(LogEntry.kind).all())
    if kinds.get("note"):
        out.append(_fact("Notes written by hand", str(kinds["note"]),
                         f"of {entries:,} entries; the rest are the database "
                         "recording its own changes"))
    longest_note = (db.query(LogEntry.asset_id, func.length(LogEntry.message))
                    .filter(LogEntry.kind == "note")
                    .order_by(func.length(LogEntry.message).desc()).first())
    if longest_note and longest_note[1] and longest_note[0]:
        # All three kinds, because log_entry is keyed by a register id and a project
        # writes notes through the same bar a machine does. Looking in two tables
        # only would not be wrong so much as quietly incomplete: the tile would
        # disappear on the day the longest note happened to be on a project.
        obj = next((o for _, cls in REGISTER
                    if (o := db.get(cls, longest_note[0])) is not None), None)
        if obj is not None:
            kind = next(k for k, cls in REGISTER if isinstance(obj, cls))
            out.append(_fact("The longest note anyone has written",
                             f"{longest_note[1]} characters",
                             obj.name if isinstance(obj, Project) else _named(obj),
                             f"/{kind}/{obj.asset_id}"))

    shots = st["portraits"]
    if shots:
        once = sum(1 for x in shots.values() if x == 1)
        if once:
            out.append(_fact("Things photographed exactly once", str(once),
                             f"of {len(shots)} photographed at all: one angle and no "
                             "more", "/browse?f=photos"))
        many = sum(1 for x in shots.values() if x >= 5)
        if many:
            out.append(_fact("Things photographed five times or more", str(many),
                             "properly documented, as opposed to merely recorded",
                             "/browse?f=photos"))

    unwritten = _held(db.query(func.count(Part.asset_id))
                      .filter(Part.summary == "", Part.notes == ""), Part).scalar() or 0
    if unwritten and st["n_parts"]:
        out.append(_fact("Parts nobody has written a word about", str(unwritten),
                         f"{round(100 * unwritten / st['n_parts'])}% of them: no "
                         "summary and no notes", "/browse?f=unwritten"))
    linked = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.url != "", Part.url.isnot(None)), Part).scalar() or 0
    if linked:
        out.append(_fact("Parts with a link out", str(linked),
                         "somebody else's page about the same thing",
                         "/browse?f=links"))
    images = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.disk_image != "", Part.disk_image.isnot(None)),
                   Part).scalar() or 0
    if images:
        out.append(_fact("Disk images kept", str(images),
                         "the contents as well as the object",
                         "/browse?f=diskimages"))
    nested = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.parent_id.isnot(None)), Part).scalar() or 0
    if nested:
        out.append(_fact("Parts fitted to another part", str(nested),
                         "a riser, a daughterboard, or a chip on a carrier",
                         "/browse?f=subparts"))

    dupes = sorted(_held(db.query(Part.manufacturer, Part.model,
                                  func.count(Part.asset_id))
                         .filter(Part.model != "", Part.model.isnot(None)), Part)
                   .group_by(Part.manufacturer, Part.model).all(),
                   key=lambda r: -r[2])
    repeated = [r for r in dupes if r[2] > 1]
    if repeated:
        out.append(_fact("Things there is more than one of", str(len(repeated)),
                         f"models held twice or more, of {len(dupes)} in the register",
                         "/browse?f=dupes"))
        top = repeated[0][2]
        tied = sorted(f"{r[0]} {r[1]}".strip() for r in repeated if r[2] == top)
        if len(tied) == 1:
            said = tied[0]
        elif len(tied) == 2:
            said = f"{tied[0]} and {tied[1]}, tied"
        else:
            said = f"{tied[0]} and {len(tied) - 1} others, tied"
        out.append(_fact("The most duplicated thing here", str(top), said,
                         "/browse?f=dupes"))

    # The other end of the longest name, which is counted the same way in the pool
    # above. A second walk over every held object rather than one walk answering
    # both, because at this size it costs nothing and the two figures belong to
    # different groups.
    names = []
    for model in (Computer, Part):
        for obj in _held(db.query(model), model):
            names.append((len(_named(obj)), obj,
                          "computers" if model is Computer else "parts"))
    short = min(names, key=lambda n: n[0], default=None)
    if short and short[0] > 1:
        out.append(_fact("Shortest name in the register", f"{short[0]} characters",
                         _named(short[1]), f"/{short[2]}/{short[1].asset_id}"))
    return out


def _facts_projects(db, st):
    """Figures about the work rather than about the hardware: what is on the go,
    what is still to do, and what is in the post.

    No money here, on purpose. /stats is a public page and what a thing cost is the
    one fact on a project that is not -- see project.html, where the cost column is
    drawn for a signed-in reader only. A total spent would put on the most public
    page of the site exactly the figure the item page takes care to withhold.

    Everything is counted across all projects rather than per project, because a
    figure about one project is a fact about that project's own page."""
    out = []
    open_n = (db.query(func.count(Project.asset_id))
              .filter(Project.status.notin_(projects.CLOSED)).scalar() or 0)
    total = db.query(func.count(Project.asset_id)).scalar() or 0
    if open_n:
        out.append(_fact("Projects on the go", str(open_n),
                         f"of {total} written down: repairs, builds and machines "
                         "still being looked for", "/projects"))
    done = (db.query(func.count(Project.asset_id))
            .filter(Project.status == "done").scalar() or 0)
    if done:
        out.append(_fact("Projects actually finished", str(done),
                         f"of {total}, which is the figure a pile of half-done "
                         "machines is measured against", "/projects"))
    todo = (db.query(func.count(ProjectTask.id))
            .filter(ProjectTask.done.is_(False)).scalar() or 0)
    ticked = (db.query(func.count(ProjectTask.id))
              .filter(ProjectTask.done.is_(True)).scalar() or 0)
    if todo:
        out.append(_fact("Jobs still on the list", str(todo),
                         f"against {ticked} ticked off", "/projects"))
    coming = (db.query(func.count(ProjectOrder.id))
              .filter(ProjectOrder.delivered.is_(False)).scalar() or 0)
    if coming:
        out.append(_fact("Things in the post", str(coming),
                         "ordered for a project and not here yet", "/projects"))
    spoken_for = (db.query(func.count(func.distinct(ProjectAsset.asset_id)))
                  .scalar() or 0)
    if spoken_for:
        out.append(_fact("Things spoken for by a project", str(spoken_for),
                         "not spare, whatever the shelf says", "/projects"))
    # The one that says something a count cannot: how long the oldest unfinished
    # project has been unfinished. Only a started one -- a project nobody has begun
    # is not overdue, it is an idea.
    oldest = (db.query(Project).filter(Project.status.notin_(projects.CLOSED),
                                       Project.started_at.isnot(None))
              .order_by(Project.started_at).first())
    if oldest is not None:
        days = (date.today() - oldest.started_at).days
        if days > 0:
            out.append(_fact("The project that has been going longest",
                             f"{days} days", oldest.name,
                             f"/projects/{oldest.asset_id}"))
    return out


def _facts_condition(db, st):
    """Figures about what state it is all in, beyond the working share on the page
    above and the two reliability tables below it."""
    out = []
    rel = _maker_reliability(db)
    perfect = [r for r in rel if r[3] == 100]
    if perfect and len(rel) > len(perfect):
        out.append(_fact("Makers with a clean sheet", str(len(perfect)),
                         f"of {len(rel)} with {RELIABILITY_MIN}+ parts here, every "
                         "one of them working"))

    # Four of the six values in entry.CONDITIONS, each with a sentence of its own,
    # because each says something the working share does not: what was kept anyway,
    # and what was worked on. Working and Untested already have figures above.
    for label, key, blurb in (
            ("Broken and kept anyway", "Faulty",
             "known bad and still on the shelf"),
            ("Works, but not all of it", "Partially working",
             "the most honest category there is"),
            ("Brought back", "Restored",
             "working, but it did not arrive that way"),
            ("Good only for parts", "For parts/repair",
             "kept for what can be taken off it")):
        n = _held(db.query(func.count(Part.asset_id))
                  .filter(Part.condition == key), Part).scalar() or 0
        if n:
            out.append(_fact(label, str(n), blurb,
                             f"/browse?f=condition&v={quote(key)}"))

    spare_types = sorted(_held(db.query(Part.type, func.count(Part.asset_id))
                               .filter(Part.computer_id.is_(None)), Part)
                         .group_by(Part.type).all(), key=lambda r: (-r[1], r[0]))
    if spare_types and st["spares"]:
        out.append(_fact("The commonest thing to have spare",
                         entry.type_label(spare_types[0][0]),
                         f"{spare_types[0][1]} of {st['spares']} on the shelf",
                         f"/browse?f=sparetype&v={quote(spare_types[0][0])}"))
    return out


def _collection_stats(db):
    """Figures about the collection for the public /stats page. Everything here is
    counted from the typed columns and child tables rather than parsed out of
    strings, which is the whole point of their being typed.

    The ranked lists carry three fields per row -- label, count, and the value to
    query on -- so that a bar on the page can link to the items behind it. Usually
    the label is the value; for part types the label is prettified and the raw type
    key is what /browse needs."""
    n_computers = _held(db.query(func.count(Computer.asset_id)), Computer).scalar() or 0
    n_parts = _held(db.query(func.count(Part.asset_id)), Part).scalar() or 0

    def ranked(query, limit=None):
        rows = [(k, n, k) for k, n in query if (k or "").strip()]
        rows.sort(key=lambda r: (-r[1], r[0]))
        return rows[:limit] if limit else rows

    makers = ranked(_held(db.query(Part.manufacturer, func.count(Part.asset_id)), Part)
                    .group_by(Part.manufacturer), 8)
    types = ranked(_held(db.query(Part.type, func.count(Part.asset_id)), Part)
                   .group_by(Part.type))
    # The child tables have no disposed flag of their own, so these join back to the
    # part that owns the row: a binned board's slots are not slots the collection has.
    buses = ranked(_held(db.query(PartSlot.bus, func.sum(PartSlot.count))
                         .join(Part, Part.asset_id == PartSlot.part_id), Part)
                   .group_by(PartSlot.bus), 6)
    ports = ranked(_held(db.query(PartPort.port, func.sum(PartPort.count))
                         .join(Part, Part.asset_id == PartPort.part_id), Part)
                   .group_by(PartPort.port), 6)
    conditions = ranked(_held(db.query(Part.condition, func.count(Part.asset_id)), Part)
                        .group_by(Part.condition))

    years = _all_years(db)
    ram = [kb for (kb,) in _held(db.query(Computer.installed_ram_kb)
                                 .filter(Computer.installed_ram_kb.isnot(None)),
                                 Computer)]
    common_ram = sorted(((entry.fmt_kb(kb), ram.count(kb), kb) for kb in set(ram)),
                        key=lambda r: (-r[1], r[0]))
    # Ties share the honour: two sizes fitted to three machines each are both "the
    # usual amount". Sorted by count, so the ties are the rows at the front.
    top_ram = [r for r in common_ram if r[1] == common_ram[0][1]][:3] if common_ram else []

    fitted_kb = sum(ram)
    stored_kb = _held(db.query(func.sum(StorageSpec.capacity_kb))
                      .join(Part, Part.asset_id == StorageSpec.part_id),
                      Part).scalar() or 0
    slots = _held(db.query(func.sum(PartSlot.count))
                  .join(Part, Part.asset_id == PartSlot.part_id), Part).scalar() or 0
    boards = _held(db.query(func.count(func.distinct(PartSlot.part_id)))
                   .join(Part, Part.asset_id == PartSlot.part_id), Part).scalar() or 0
    chips = _held(db.query(func.sum(ComputerRamChip.count))
                  .join(Computer, Computer.asset_id == ComputerRamChip.computer_id),
                  Computer).scalar() or 0
    drives = _held(db.query(func.sum(ComputerDrive.count))
                   .join(Computer, Computer.asset_id == ComputerDrive.computer_id),
                   Computer).scalar() or 0
    gotek = _held(db.query(func.count(ComputerDrive.id))
                  .join(Computer, Computer.asset_id == ComputerDrive.computer_id)
                  .filter(ComputerDrive.kind == "Gotek"), Computer).scalar() or 0
    working = _held(db.query(func.count(Part.asset_id))
                    .filter(Part.condition == "Working"), Part).scalar() or 0
    # The one figure that is about the disposed, so the only one that counts them.
    disposed = ((db.query(func.count(Part.asset_id)).filter(Part.disposed).scalar() or 0)
                + (db.query(func.count(Computer.asset_id))
                   .filter(Computer.disposed).scalar() or 0))

    fullest = (_held(db.query(Part.computer_id, func.count(Part.asset_id))
                     .filter(Part.computer_id.isnot(None)), Part)
               .group_by(Part.computer_id)
               .order_by(func.count(Part.asset_id).desc()).first())
    fullest_machine = db.get(Computer, fullest[0]) if fullest else None
    if fullest_machine and fullest_machine.disposed:
        fullest, fullest_machine = None, None

    oldest_held = _held(db.query(Part).filter(Part.acquired_date.isnot(None)),
                        Part).order_by(Part.acquired_date).first()
    photos = sum(len(folder_images(k)) for k in ("computers", "parts"))
    # Portrait coverage: the one figure on the page that is a job rather than a
    # curiosity, so the page shows it every visit rather than dealing it into the
    # shuffle. Both halves come from here -- the standing line and the pool's
    # figures about photographs -- so the page cannot disagree with itself about
    # what a photograph is.
    portraits, unphotographed = _portraits(db)
    # A share that rounds to nothing is still one thing nobody has photographed, and
    # "0% of the register, waiting for a camera" beside a count of 1 reads as a bug
    # rather than as a nearly-finished job.
    share = 100 * len(unphotographed) / ((n_computers + n_parts) or 1)
    # Most parts are spares on a shelf, so "parts per machine" over the whole
    # register would say 19 and mean nothing. Only the fitted ones divide.
    fitted = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.computer_id.isnot(None)), Part).scalar() or 0

    return {
        "n_computers": n_computers, "n_parts": n_parts,
        "n_total": n_computers + n_parts,
        "makers": makers, "types": types, "buses": buses, "ports": ports,
        "types_labelled": [(entry.type_label(t), n, t) for t, n, _ in types],
        "conditions": conditions,
        "top_maker": makers[0] if makers else None,
        "top_type": types[0] if types else None,
        "top_ram": top_ram, "top_ram_kb": [r[2] for r in top_ram],
        "mean_year": round(sum(years) / len(years)) if years else None,
        "oldest_year": min(years) if years else None,
        "newest_year": max(years) if years else None,
        "fitted_kb": fitted_kb, "stored_kb": stored_kb,
        "slots": slots, "boards": boards, "chips": chips,
        "drives": drives, "gotek": gotek,
        "working": working, "disposed": disposed, "photos": photos,
        "portraits": portraits, "unphotographed": len(unphotographed),
        "unphotographed_pct": "under 1" if 0 < share < 0.5 else str(round(share)),
        "fullest": (fullest_machine, fullest[1]) if fullest_machine else None,
        "oldest_held": oldest_held,
        "fitted": fitted, "spares": n_parts - fitted,
        # Guarded because an empty register is a real state -- a fresh install --
        # and a stats page that divides by zero on day one is no use to anyone.
        "fitted_per_machine": (round(fitted / n_computers, 1) if n_computers else None),
        "working_pct": (round(100 * working / n_parts) if n_parts else None),
        "slots_per_board": (round(slots / boards, 1) if boards else None),
    }


# How many figures a visit gets. Eight fills two rows on a wide screen, and with the
# whole pool shuffled rather than half of it there is no fixed half left for them to
# be a preamble to.
FACTS_SHOWN = 8
