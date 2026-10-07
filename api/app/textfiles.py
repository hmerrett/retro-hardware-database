"""A text file read as a page of the register: the words in one, and Markdown set
as the site's own markup (ADR-0035).

Nothing here hands a file to the browser as itself. What a file says is read on the
server and put into a page of the register, so the page is the site's -- its
stylesheet, its themes, its banner and its content policy -- and the file is only
ever words in it. A plain text file reaches the template as a string, which
autoescapes it. A Markdown file is parsed with HTML switched off, so whatever it
writes as markup arrives as the characters it is, and the tokens are then walked
before they are rendered, so that nothing the page draws asks for anything the
register's policy would refuse: no picture from elsewhere, no style attribute, no
link that runs script.

Which files are read this way, and how big one may be, is a fact about the name and
the size, and so lives in filekinds; the bytes are filesdb's.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.rules_core import StateCore
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from markupsafe import Markup

# Every control character except the tab and the newline. A DOS file ends with a
# Ctrl-Z that was never part of what it said, a form feed was a page break on a
# printer, and a stray NUL from a sector's padding is nothing a reader can see:
# none of them is a character a page can show.
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


# Box drawing and block elements: the lines and shading a DOS screen was drawn with,
# and a folder tree in a README is drawn with now.
_DRAWING = re.compile("[\u2500-\u259f]")


def drawn(text: str) -> bool:
    """Whether this text draws with box-drawing characters. The register's
    fixed-width face has none, so a browser takes them from some other face and the
    letters from this one, and the two are not the same width -- Consolas is
    nearly a tenth narrower -- so the corners of a box miss each other. Text that
    draws is set in one face that has both (components.css, `.drawn`)."""
    return bool(_DRAWING.search(text))


def decode(data: bytes) -> str | None:
    """What these bytes say as text, or None if they are not text.

    A zero byte anywhere means a program, a disk image or a document in some binary
    format that has been given a text file's name: text never has one, and nearly
    everything else does, which is the test git uses too. UTF-8 first, since a file
    that decodes as UTF-8 almost certainly is; anything else is read as code page
    437, the PC's own, which is what a readme on a driver disk was written in -- so
    its box drawing and its accented letters come out as they did on the screen it
    was typed for, where Latin-1 would make them a row of symbols."""
    if b"\0" in data:
        return None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp437")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROLS.sub("", text)


# The schemes a link in a file may keep: the ones a note's links are made of
# (entry.linked), and nothing else. markdown-it already refuses javascript: and its
# kind, by leaving the link as the text it was written as; this is the allowlist
# behind that blocklist.
_SCHEMES = frozenset({"http", "https", "ftp", "ftps", "sftp", "mailto"})
_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*):", re.I)

# A heading's anchor is prefixed, so that a file cannot give one of its headings the
# id of something on the page around it -- a README with a section called Main
# would otherwise be `id="main"` twice, and the skip link would land in the file.
ANCHOR = "doc-"


def _href(url: str) -> tuple[str, bool] | None:
    """Where a link in a file may go, and whether it is to another site -- or None
    for a link the page should show as its words.

    Kept: a scheme on the list, a heading in the same file, and a page of this site.
    Not kept: a path relative to the file, which points at a file that sat beside
    it in a folder the register does not have -- followed, it would open this file
    again under another name, or nothing at all."""
    if url.startswith("#"):
        return "#" + ANCHOR + url[1:].lower(), False
    if url.startswith("//"):
        return url, True
    if url.startswith("/"):
        return url, False
    scheme = _SCHEME.match(url)
    if scheme and scheme[1].lower() in _SCHEMES:
        return url, scheme[1].lower() != "mailto"
    return None


def _words(children: Sequence[Token] | None) -> str:
    """The words a run of inline tokens says, without its markup: what a heading's
    anchor is made from, and what a picture is shown as."""
    out = []
    for child in children or ():
        if child.type in ("text", "code_inline"):
            out.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            out.append(" ")
        elif child.type == "image":
            out.append(_words(child.children))
    return "".join(out)


def _slug(words: str) -> str:
    """A heading's anchor as GitHub makes one, since that is where most of the links
    to one were written: lower case, no punctuation, a hyphen for each space."""
    return re.sub(r"[^\w\- ]", "", words.lower()).replace(" ", "-")


def _inline(children: list[Token]) -> list[Token]:
    """A paragraph's inline tokens, made fit for the page: a picture becomes its
    description, and a link the page will not keep becomes its words."""
    out: list[Token] = []
    dropping = False
    for child in children:
        if child.type == "image":
            # Never fetched: the policy loads nothing from another site, and a picture
            # beside the file in its folder is not in the register. Its description is
            # what it was standing in for. Inside a link, it is the link's words.
            out.append(Token("text", "", 0, content=_words(child.children)))
        elif child.type == "link_open":
            kept = _href(str(child.attrGet("href") or ""))
            if kept is None:
                dropping = True
                continue
            href, offsite = kept
            child.attrSet("href", href)
            if offsite:
                # As a link in a note opens (entry.linked): the register is a thing you
                # are working through, and following a file out of it should not lose
                # your place in it.
                child.attrSet("target", "_blank")
                child.attrSet("rel", "noopener noreferrer")
            out.append(child)
        elif child.type == "link_close" and dropping:
            # Links do not nest, so the next close is this link's.
            dropping = False
        else:
            out.append(child)
    return out


def _for_the_page(state: StateCore) -> None:
    """The core rule that runs last: everything the parser made, made fit for a page
    of the register.

    - A heading goes down a level, because the page's own heading is the file's name
      and the file's sections are inside it; and it gets an anchor, so a contents
      list at the top of a README jumps to where it says.
    - A block of code that draws with box-drawing characters is marked, so it is set
      in a face that has them (`drawn`).
    - A table is the register's own table component, so it is drawn as the site's
      tables are; its header cells say they head columns, as every `<th>` the
      register draws does (accessibility-standards); and a column's alignment is a
      class rather than the style attribute the parser writes, which the content
      policy refuses (ADR-0022).
    """
    seen: dict[str, int] = {}
    tokens = state.tokens
    for at, token in enumerate(tokens):
        if token.type in ("heading_open", "heading_close"):
            token.tag = f"h{min(int(token.tag[1]) + 1, 6)}"
            if token.type == "heading_open" and at + 1 < len(tokens):
                slug = _slug(_words(tokens[at + 1].children)) or "section"
                count = seen.get(slug, 0)
                seen[slug] = count + 1
                token.attrSet("id", ANCHOR + (slug if not count else f"{slug}-{count}"))
        elif token.type in ("fence", "code_block") and drawn(token.content):
            token.attrJoin("class", "drawn")
        elif token.type == "table_open":
            token.attrSet("class", "table")
        elif token.type in ("th_open", "td_open"):
            if token.type == "th_open":
                token.attrSet("scope", "col")
            align = str(token.attrs.pop("style", "")).removeprefix("text-align:")
            if align in ("center", "right"):
                token.attrSet("class", "al-" + align)
        elif token.type == "inline" and token.children:
            token.children = _inline(token.children)


def _table_open(
    self: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    """A table in a box of its own, which scrolls sideways when the table is wider
    than the screen rather than taking the page with it (accessibility-standards,
    "On a narrow screen")."""
    return '<div class="doctable">' + self.renderToken(tokens, idx, options, env)


def _table_close(
    self: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    return self.renderToken(tokens, idx, options, env) + "</div>\n"


# CommonMark, with the two things from GitHub's dialect a README most often leans on:
# tables, and struck-through text. HTML off -- the whole of what keeps a file from
# writing markup into the page -- and no typographer, which would change what the
# file says.
_MD = MarkdownIt("commonmark", {"html": False, "typographer": False}).enable(
    ["table", "strikethrough"]
)
_MD.core.ruler.push("for_the_page", _for_the_page)
_MD.add_render_rule("table_open", _table_open)
_MD.add_render_rule("table_close", _table_close)


def markdown(text: str) -> Markup:
    """A Markdown file as the markup of a page of the register. Safe to put in a
    template as it is: every character the file supplied has been escaped by the
    renderer, and every tag in what comes back is one the renderer wrote."""
    return Markup(_MD.render(text))
