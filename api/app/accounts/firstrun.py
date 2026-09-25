"""An installation with no accounts, and the way out of that state (ADR-0032).

A new install is on the internet from the moment its certificate arrives, before
its owner has visited it. So the first account is made at /setup only by somebody
holding the setup code, which is written to the app's log and nowhere else:
whoever can read the server's log is the owner, and whoever found the address
first is not.

An installation upgraded from the single login never sees setup. The pair it was
run with becomes its first administrator on the first start, so nobody has to be
told a new password.

`startup` also says which state the app came up in, which is what ADR-0019 asked
of the open mode and still holds now that the open mode is gone: a configuration
that can only be inferred is one nobody notices for weeks.
"""

import logging
import secrets

from sqlalchemy.orm import Session

from ..db import SessionLocal
from . import store
from .roles import ADMIN

log = logging.getLogger(__name__)

# No 0/O, 1/I/L: the code is read off a terminal and typed on a phone.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# Whether there is an administrator, once there is. Only True is kept: the last
# administrator cannot be removed, so an installation that has one keeps having
# one, and a request should not have to ask the database that on every page.
#
# An administrator and not merely an account: a viewer made from the command line
# on a new install is an account, and a site whose only account can change
# nothing is still a site that nobody has set up.
# False is asked again each time, because it stops being true the moment setup
# finishes. One process -- see ADR-0032 on what a second would mean.
_ready = False
_code: str | None = None


def forget() -> None:
    """Drop what is kept between requests. For the suite, which empties the tables
    between tests and so takes away accounts this module thought were there."""
    global _ready, _code
    _ready = False
    _code = None


def ready() -> bool:
    """Whether the installation has an administrator, and so is past setup."""
    global _ready
    if not _ready:
        with SessionLocal() as db:
            _ready = store.admins(db) > 0
    return _ready


def mark_ready() -> None:
    global _ready, _code
    _ready = True
    _code = None


def _new_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def code() -> str:
    """The setup code for this process, made and logged the first time it is asked
    for. Normally that is at startup; asking again from /setup covers a process that
    never ran its startup, which is what a test client without a lifespan is."""
    global _code
    if _code is None:
        _code = _new_code()
        log.warning(
            "No accounts yet. Open /setup on this site and give it this setup code: %s",
            _code,
        )
    return _code


def _plain(typed: str) -> str:
    return "".join(ch for ch in typed.upper() if ch.isalnum())


def code_matches(typed: str) -> bool:
    """Whether this is the setup code, ignoring case, spaces and dashes -- it is
    read off one screen and typed into another -- and compared in constant time."""
    return secrets.compare_digest(_plain(typed), _plain(code()))


def seed(db: Session, username: str, password: str) -> bool:
    """Make the first administrator from the old single login, if there are no
    accounts and it is set. Whether it did."""
    if not (username and password) or store.count(db):
        return False
    # The old login's password was never held to the length rule, and refusing it
    # here would lock an upgraded site out of itself on its first start. It is
    # hashed as it is; the manual asks for it to be changed.
    try:
        store.create(db, username, password, ADMIN, short_ok=True)
    except store.AccountError as e:
        # Said and not raised: a site that will not start is worse than a site that
        # opens on setup, which is what it does instead.
        log.error("Could not make an administrator from RHDB_AUTH_USER: %s", e)
        return False
    return True


def startup(env_user: str, env_password: str, env_open: str) -> None:
    """Seed if there is anything to seed from, and say which state the app is in.

    Nothing here writes a password. The setup code is written, on purpose: it is the
    one secret whose job is to be read out of the log."""
    with SessionLocal() as db:
        seeded = seed(db, env_user, env_password)
        accounts = store.admins(db)
    if env_open.strip():
        log.warning(
            "RHDB_OPEN is set, and does nothing any more: there is no running without "
            "a login. A site anybody may read is the default. Remove it from .env."
        )
    # Warnings, all of them, and not because each is a fault: under uvicorn an INFO
    # from the app's own loggers reaches nobody, and a line saying which state the
    # site came up in is only worth writing if it is read.
    if seeded:
        mark_ready()
        log.warning(
            "Made an administrator from RHDB_AUTH_USER and RHDB_AUTH_PASSWORD. Sign in "
            "as before; from now on the accounts are the login and those two are not "
            "read by the site."
        )
    elif accounts:
        mark_ready()
        if env_user or env_password:
            log.warning(
                "RHDB_AUTH_USER and RHDB_AUTH_PASSWORD are set, but the site no longer "
                "reads them: its accounts are the login. Only the tool server still "
                "does, until it is given RHDB_API_TOKEN."
            )
    else:
        code()
