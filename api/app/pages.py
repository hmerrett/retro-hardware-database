"""The small pieces every editable page needs.

What somebody has typed before, offered back as a datalist so the second machine
from the same seller is not typed out again; and a note posted with photographs on
it, which three different pages allow and which writes one history entry rather
than one per photograph.
"""

from collections import Counter

from .history import PHOTO_ENTRY, add_log
from .models import Computer, Part
from .photos import _attach_log_photos, _chosen_photos


def _answers_given(db, *columns, limit=200):
    """Every answer already given to a free-text field, commonest first, for the
    pick list on the box that asks it.

    A field answered the same way over and over wants to offer its own past
    answers. `source` is the case that asked for this: 154 of them, in 69
    spellings, among which "Pete Farm" sixteen times and "Farm Pete" eight -- one
    person and one provenance, recorded as two, and now unfindable as one. A list
    does not stop anybody typing something new (it is a datalist, not a menu); it
    only makes the answer already given the easier one to give again.

    Commonest first, because a datalist is offered in the order it is written and
    the answer given twenty times is the likelier one. Case and surrounding space
    fold together for the counting, and the spelling offered back is the one used
    most -- so "eBay" wins over "ebay" by being what was actually typed, rather
    than by any rule about capitals.

    The counting is done here rather than by the query it would obviously be done
    by. MariaDB's collation folds case and ignores trailing spaces, so GROUP BY on
    the column has already merged "eBay", "ebay" and "eBay " before we see them,
    and what comes back as the group's label is whichever row it happened to read
    first -- which makes "the spelling used most" whatever the storage engine felt
    like that morning. Reading the values and counting them here makes the rule
    ours. It is a column of a few hundred short strings; the query it replaces was
    not saving anything worth this.

    Capped: this goes into the markup of every form that asks, and two hundred is
    already past what anybody scrolls.
    """
    counts, spellings = Counter(), {}
    for column in columns:
        for (value,) in db.query(column):
            text = (value or "").strip()
            if not text:
                continue
            key = text.casefold()
            counts[key] += 1
            spellings.setdefault(key, Counter())[text] += 1
    return [spellings[key].most_common(1)[0][0] for key, _ in counts.most_common(limit)]


def _datalists(db, computer=False):
    """The pick lists a form's free-text boxes are offered, in one place because
    two forms ask several of the same questions.

    `computer` adds the three a machine is asked and a part is not. A part's
    equivalent of them is its typed spec table, which has its own vocabularies."""
    lists = {"source": _answers_given(db, Computer.source, Part.source)}
    if computer:
        lists |= {
            "makes": _answers_given(db, Computer.manufacturer, Part.manufacturer),
            # A machine's models only. A list of every card and drive model as well
            # would bury "PC1512" in a thousand answers to a different question.
            "models": _answers_given(db, Computer.model),
            "chassis": _answers_given(db, Computer.chassis),
            "os": _answers_given(db, Computer.os),
            "cpu": _answers_given(db, Computer.cpu),
        }
    return lists


def _note_with_photos(db, aid, form):
    """Whatever the note bar was filled in with: words, photographs, or both.

    Neither half needs the other. Words alone are a note, as they always were.
    Photographs alone are an entry of their own with its own time on it, because a
    photograph of the thing is a thing said about it -- and having to type a sentence
    first was a toll on the commonest gesture in the register. Both together stay one
    entry: they were one gesture, and the words are the caption.

    Nothing at all writes nothing at all. Every upload is still checked before the
    entry is written, so a refused file leaves no half-written history behind."""
    uploads = _chosen_photos(form)
    message = (form.get("message", "") or "").strip()
    if not message and not uploads:
        return
    row = add_log(db, aid, message, kind="note" if message else PHOTO_ENTRY)
    _attach_log_photos(db, row, uploads)
    db.commit()
