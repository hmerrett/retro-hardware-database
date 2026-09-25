"""Roles as lists of permissions, and the one check the rest of the app makes.

Nothing outside this module compares a role by name. A page asks whether its
reader `can` do a thing, and what each role may do is this table, so a third role
-- or a role held on one site and not another -- is a row here rather than a
search through every `if role == "admin"` in the code (ADR-0032).
"""

from dataclasses import dataclass

# The one site there is. A membership names the site its role is held on, and a
# principal carries the site it was worked out for, so the day there are two, the
# question "may this person edit?" is already "may this person edit *here*?" and
# nothing that asks it changes shape.
SITE = 1

ADMIN, VIEWER = "admin", "viewer"

# What a permission lets somebody do, in the words the rest of the code asks for.
READ_PRIVATE = "read_private"  # see what a visitor is not shown
EDIT = "edit"  # add, change and delete anything in the register
MANAGE_SETTINGS = "manage_settings"
MANAGE_ACCOUNTS = "manage_accounts"

ROLES: dict[str, frozenset[str]] = {
    VIEWER: frozenset({READ_PRIVATE}),
    ADMIN: frozenset({READ_PRIVATE, EDIT, MANAGE_SETTINGS, MANAGE_ACCOUNTS}),
}

# What a role is called where a person reads it, in the order they are offered.
ROLE_NAMES: dict[str, str] = {ADMIN: "Administrator", VIEWER: "Viewer"}


@dataclass(frozen=True)
class Principal:
    """Who a request is made by, as far as the gate could tell.

    A visitor is a principal too -- one with no account and no role -- so every
    request has one and no page has to ask whether there is one before asking what
    it may do. `via` is how they proved it: a session cookie, an API token, or an
    HTTP Basic password. It is kept because a second factor, when it comes, will
    care which door was used, and because a log line about a request is more use
    for saying."""

    user_id: int | None = None
    username: str = ""
    role: str = ""
    site: int = SITE
    via: str = ""

    @property
    def signed_in(self) -> bool:
        return self.user_id is not None


VISITOR = Principal()


def can(principal: Principal, permission: str, site: int = SITE) -> bool:
    """Whether this principal may do this, on this site.

    A role held on one site grants nothing on another, which is true today only
    vacuously and is written down so it stays true when it stops being vacuous."""
    if principal.site != site:
        return False
    return permission in ROLES.get(principal.role, frozenset())
