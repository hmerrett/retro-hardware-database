"""Projects: the work, as against the things it is done to.

The register says what is owned. A project says what is intended -- a repair, a
build, a machine wanted and not yet found -- and it is described by facts an asset
has no room for: a state, a list of jobs, and a pile of things on order.

What a project shares with an asset is the register itself. It takes an id from
the same allocator, which is what lets it keep a history: log_entry is keyed by a
plain asset id because no one table owns the register, so a project writes notes
and hangs photographs on them through exactly the code a machine does.

This module owns everything about a project that is not a route: the vocabulary,
the money, and the reading of the three child tables. main.py holds the routes and
the forms, the way it holds the file routes over filesdb.
"""
import re

from sqlalchemy import func

from .models import (Computer, Part, Project, ProjectAsset, ProjectOrder,
                     ProjectTask)

# The states a project can be in, as (slug, label). Stored as the slug so the
# wording on screen can be changed without rewriting anybody's rows.
#
# Five, and no more. 'stalled' earns its place because it is the true state of most
# of them -- waiting on a part, waiting on the weather, waiting on the will -- and
# calling that 'active' would make the active list a lie and the whole status
# useless. 'abandoned' is kept apart from 'done' for the same reason: a project
# given up on is not a project finished, and losing that distinction would mean
# never being able to ask what was actually built.
STATUSES = [
    ("planned", "planned"),
    ("active", "in progress"),
    ("stalled", "stalled"),
    ("done", "done"),
    ("abandoned", "abandoned"),
]
STATUS_LABELS = dict(STATUSES)
DEFAULT_STATUS = "planned"

# The two that are over. Used for the ordering below and for the count on the list
# page: a project that is finished or given up on is not one of the ones in hand.
CLOSED = ("done", "abandoned")

# The order the list page reads in, which is deliberately not the order the form
# offers. The form runs down the life of a project -- planned, then in progress,
# then over -- because that is the order somebody setting a status thinks in. The
# page leads with what is actually being worked on instead: 'planned' is a list of
# intentions and 'in progress' is the list of things with the lid off, and the
# second is what the page is opened to find.
LIST_ORDER = ["active", "planned", "stalled", "done", "abandoned"]


def status_label(slug):
    """The words for a status, falling back to whatever is stored. A row written
    under a status this list no longer names still reads back as itself rather than
    as a blank."""
    return STATUS_LABELS.get(slug or "", slug or "")


def clean_status(raw):
    slug = (raw or "").strip().lower()
    return slug if slug in STATUS_LABELS else DEFAULT_STATUS


# --- money -------------------------------------------------------------------
# The one corner of the register that holds an amount of money. Pence, as an
# integer, for the reason every other quantity here is an integer in a small unit
# named by the column suffix: it adds up and sorts exactly, and a float of pounds
# does neither. Sterling is assumed throughout -- there is one collector and one
# currency, and a currency column that is always 'GBP' is a column that says
# nothing.

_MONEY = re.compile(r"^\d*(?:\.\d*)?$")


def parse_money(raw):
    """Pence from whatever was typed in a cost box, or None for not recorded.

    Accepts the pound sign, thousands commas and a bare number of pounds, because
    those are what a person copies out of an order confirmation. Anything that will
    not read as an amount is None -- the same rule _parse_date follows, and for the
    same reason: a form is not the place to argue, and a cost is optional.

    Note what None means. It is a cost nobody wrote down, and it is not zero: a
    total that quietly counted unpriced lines as free would be a smaller number
    than the truth and would look just as authoritative."""
    text = (raw or "").strip().replace("£", "").replace(",", "").replace(" ", "")
    if not text or text == "." or not _MONEY.match(text):
        return None
    whole, _, frac = text.partition(".")
    return int(whole or 0) * 100 + int((frac + "00")[:2])


def money(pence):
    """Pence as it is written. Empty for None, so a template can print it straight
    into a cell that means 'not recorded' when it is blank."""
    if pence is None:
        return ""
    return f"£{pence // 100:,}.{pence % 100:02d}"


# --- reading a project's contents --------------------------------------------


def tasks(db, project_id):
    """A project's jobs: the outstanding ones first, then the finished, each in the
    order they were written. Undone first because the list is read to find out what
    to do next, and a long tail of ticked lines between you and it is the thing that
    stops task lists being read at all."""
    return (db.query(ProjectTask).filter(ProjectTask.project_id == project_id)
            .order_by(ProjectTask.done, ProjectTask.id).all())


def orders(db, project_id):
    """A project's purchases: what is still coming first, then what has arrived.

    Same reason the tasks sort that way, with one addition -- the outstanding ones
    are in expected order, soonest first, because that is the question a list of
    things on order is actually asked. A line with no expected date sorts last
    among them: it is not due sooner than one that is due, it is simply not known."""
    rows = (db.query(ProjectOrder).filter(ProjectOrder.project_id == project_id)
            .order_by(ProjectOrder.id).all())
    rows.sort(key=lambda o: (bool(o.delivered),
                             o.expected_at is None, o.expected_at or o.id))
    return rows


def members(db, project_id):
    """What the project is about, as [(kind, object)] with kind the URL segment.

    Three queries whatever the membership: the rows, then the computers and the
    parts among them at once. The asset ids are looked up in both tables because
    project_asset holds a register id and the register is two tables -- the same
    lookup /items/<id> makes, for the same reason.

    A membership pointing at an asset that no longer exists is dropped rather than
    shown as a gap. The delete paths clear these rows, so this should not happen;
    it reads defensively because a dangling id here would otherwise render as a
    link to a 404, and a project is not the place to find that out."""
    rows = (db.query(ProjectAsset).filter(ProjectAsset.project_id == project_id)
            .order_by(ProjectAsset.id).all())
    if not rows:
        return []
    ids = [r.asset_id for r in rows]
    found = {}
    for kind, cls in (("computers", Computer), ("parts", Part)):
        for obj in db.query(cls).filter(cls.asset_id.in_(ids)):
            found[obj.asset_id] = (kind, obj)
    out = []
    for r in rows:
        if r.asset_id in found:
            kind, obj = found[r.asset_id]
            out.append((kind, obj, r))
    return out


def projects_by_asset(db, asset_ids):
    """{asset_id: [Project]} for a page's worth of items, in one query.

    The list version of projects_for, for the queue on /projects: it answers
    "have I already made a job out of this?" against every flagged item at once,
    rather than asking once per row."""
    if not asset_ids:
        return {}
    out = {}
    for pa, p in (db.query(ProjectAsset, Project)
                  .join(Project, Project.asset_id == ProjectAsset.project_id)
                  .filter(ProjectAsset.asset_id.in_(list(asset_ids)))
                  .order_by(Project.name, Project.asset_id)):
        out.setdefault(pa.asset_id, []).append(p)
    return out


def projects_for(db, asset_id, authed=True):
    """The projects one computer or part is in, for the panel on its own page.

    Ordered by name so the chips on an item page do not shuffle between reloads.

    A private one is left out for a visitor. An item page is public, so without this
    a project kept off the list, out of the search and out of the sitemap would name
    itself on the page of every machine it is about -- which is the whole of what
    was being kept back, said in the one place nobody thought to look."""
    q = (db.query(Project).join(ProjectAsset,
                                ProjectAsset.project_id == Project.asset_id)
         .filter(ProjectAsset.asset_id == asset_id))
    if not authed:
        q = q.filter(Project.private.is_(False))
    return q.order_by(Project.name, Project.asset_id).all()


def add_asset(db, project_id, asset_id, note=""):
    """Put a computer or part in a project. Returns whether it was added.

    False for one already in it, and False for an id that is in neither asset
    table: a project is about things that exist, and a typo'd id stored here would
    be a membership that renders as nothing for ever."""
    asset_id = (asset_id or "").strip().upper()
    if not asset_id:
        return False
    if not any(db.get(cls, asset_id) for cls in (Computer, Part)):
        return False
    if (db.query(ProjectAsset)
            .filter(ProjectAsset.project_id == project_id,
                    ProjectAsset.asset_id == asset_id).first()):
        return False
    db.add(ProjectAsset(project_id=project_id, asset_id=asset_id,
                        note=(note or "").strip()[:255]))
    return True


def drop_asset(db, project_id, asset_id):
    """Take one out. Returns whether there was one to take."""
    n = (db.query(ProjectAsset)
         .filter(ProjectAsset.project_id == project_id,
                 ProjectAsset.asset_id == (asset_id or "").strip().upper())
         .delete(synchronize_session=False))
    return bool(n)


def forget_asset(db, asset_id):
    """Every membership held by an asset that is being deleted.

    Called by the delete paths by hand, because project_asset.asset_id is a plain
    column with no foreign key behind it -- so nothing in the database will do this,
    for exactly the reason nothing in the database clears log_entry either."""
    return (db.query(ProjectAsset).filter(ProjectAsset.asset_id == asset_id)
            .delete(synchronize_session=False))


# --- the list page -----------------------------------------------------------


def _counts(db, model, *conds):
    """{project_id: n} for one child table, in one query."""
    q = (db.query(model.project_id, func.count(model.id))
         .group_by(model.project_id))
    for cond in conds:
        q = q.filter(cond)
    return dict(q.all())


def summaries(db, authed=True):
    """Every project with the numbers its row on the list page shows, in five
    queries however many there are: the projects, then one grouped count per thing
    counted. Written this way rather than as a property on the model because a list
    of thirty projects each asking its own three questions is ninety queries, and
    this page is the one that would notice.

    The order is the one the page is read in: what is in hand first, closed at the
    bottom, and within each the ones touched most recently -- which here means by
    name, since a project has no update stamp of its own that is not its history.

    `authed` false leaves out the private ones. Defaulted to true because every
    caller that is not a page is the owner's own -- the API is behind the login
    entire -- and a default that hides things from the code that is entitled to see
    them is a default that gets worked around."""
    q = db.query(Project)
    if not authed:
        q = q.filter(Project.private.is_(False))
    rows = q.order_by(Project.name, Project.asset_id).all()
    assets = _counts(db, ProjectAsset)
    tasks_all = _counts(db, ProjectTask)
    tasks_done = _counts(db, ProjectTask, ProjectTask.done.is_(True))
    orders_all = _counts(db, ProjectOrder)
    orders_out = _counts(db, ProjectOrder, ProjectOrder.delivered.is_(False))
    out = []
    for p in rows:
        out.append({
            "p": p,
            "assets": assets.get(p.asset_id, 0),
            "tasks": tasks_all.get(p.asset_id, 0),
            "tasks_done": tasks_done.get(p.asset_id, 0),
            "orders": orders_all.get(p.asset_id, 0),
            "orders_out": orders_out.get(p.asset_id, 0),
        })
    def rank(status):
        # A status this list no longer names sorts with the open ones rather than
        # being dropped to the bottom: it is not known to be over.
        return LIST_ORDER.index(status) if status in LIST_ORDER else len(LIST_ORDER)

    out.sort(key=lambda r: (rank(r["p"].status),
                            (r["p"].name or "").lower(), r["p"].asset_id))
    return out


def searchable(db, project_id):
    """Everything written under a project that is not one of its own columns: the
    jobs on its list and the things it has on order, as plain lines.

    Here rather than in main._haystack because it is a fact about a project's shape.
    A machine's searchable text is its columns and its history, and a project has a
    third place words go: "Gotek" typed into the search bar should find the project
    with a Gotek on order, which is the question somebody standing in front of a
    parcel actually asks. The cost is left out -- a search for "12.99" is not a
    search anybody makes, and the figure is not shown to a visitor anyway.
    """
    out = []
    for (text,) in db.query(ProjectTask.text).filter(
            ProjectTask.project_id == project_id):
        out.append(text or "")
    for row in db.query(ProjectOrder.description, ProjectOrder.supplier,
                        ProjectOrder.note).filter(
            ProjectOrder.project_id == project_id):
        out.extend(x or "" for x in row)
    return [x for x in out if x]


def spend(rows):
    """What a project's orders have cost, as (pence, how many lines had no price).

    The second number is the point of returning a pair. A total is a claim, and a
    total over lines where three had no figure is a claim about only some of them --
    so the page can say so rather than quietly under-reporting."""
    total = sum(o.cost_p for o in rows if o.cost_p is not None)
    unpriced = sum(1 for o in rows if o.cost_p is None)
    return total, unpriced


def open_projects(db):
    """The projects a thing arriving today could be joining: the ones still in hand,
    by name.

    Closed ones are left out rather than sorted to the bottom. This feeds the picker
    on the entry forms, where the question is "is this for something I am already
    doing?" -- and a finished project is not something, while a list of every project
    ever finished is a menu nobody reads to the end of. A project taken up again is
    reopened on its own page, which puts it back here."""
    return (db.query(Project).filter(Project.status.notin_(CLOSED))
            .order_by(Project.name, Project.asset_id).all())
