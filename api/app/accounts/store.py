"""Accounts, and the sessions and tokens they are used through.

Every key this module hands out -- a session's cookie, an API token -- is random,
shown once, and kept only as a SHA-256 digest, so the database is never a copy of
anybody's way in. Passwords are argon2 hashes. A key can be looked up by its
digest because it is random and long: a digest of a password would need a salt
and a slow hash, and a digest of 32 random bytes needs neither.

Each function that changes something commits, because they are called from the
login, from setup and from the command line alike, and in each of those the change
is the whole of the job.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import ApiToken, Membership, User, UserSession
from .roles import ADMIN, ROLES, SITE, Principal

# argon2id with the library's defaults, which are RFC 9106's second recommendation:
# tens of milliseconds a sign-in, and a guess costs a GPU the same.
_hasher = PasswordHasher()

MIN_PASSWORD = 10
# Letters, digits and the punctuation a username is usually written with, an email
# address included -- nothing that looks like whitespace or needs escaping in a log.
USERNAME = re.compile(r"[A-Za-z0-9._@+-]{1,64}")

SESSION_LIFE = timedelta(days=30)
# How stale `last_seen_at` may get before a request writes it again. Every request
# with a session would otherwise be a write, for a figure read by a person who wants
# to know roughly when a browser was last used, not to the second.
SEEN_EVERY = timedelta(minutes=5)

# Every token starts with this, so one pasted into the wrong file is recognisable
# for what it is -- by a person and by a secret scanner alike.
TOKEN_PREFIX = "rhdb_"


class AccountError(ValueError):
    """Something asked of an account that cannot be done, in words that can be shown
    to whoever asked. Never carries a password."""


def _now() -> datetime:
    """Naive UTC, matching every other timestamp column."""
    return datetime.now(UTC).replace(tzinfo=None)


def digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def check_username(username: str) -> str:
    username = username.strip()
    if not USERNAME.fullmatch(username):
        raise AccountError("A username is up to 64 letters, digits and the characters . _ - @ +")
    return username


def check_password(password: str) -> str:
    if len(password) < MIN_PASSWORD:
        raise AccountError(f"A password is at least {MIN_PASSWORD} characters.")
    return password


def check_role(role: str) -> str:
    if role not in ROLES:
        raise AccountError(f"A role is one of: {', '.join(ROLES)}.")
    return role


# --- accounts ---------------------------------------------------------------


def count(db: Session) -> int:
    return db.query(func.count(User.id)).scalar() or 0


def find(db: Session, username: str) -> User | None:
    """The account with this username, whichever way it is capitalised: the column's
    collation folds case, so the comparison does too."""
    return db.query(User).filter(User.username == username.strip()).one_or_none()


def role_of(db: Session, user: User, site: int = SITE) -> str:
    m = db.get(Membership, (user.id, site))
    return m.role if m else ""


def create(db: Session, username: str, password: str, role: str, short_ok: bool = False) -> User:
    """A new account with this role on the site. `short_ok` is for the one account
    made from a password chosen before there was a rule about its length."""
    username = check_username(username)
    if not short_ok:
        check_password(password)
    check_role(role)
    if find(db, username):
        raise AccountError(f"There is already an account called {username}.")
    user = User(
        username=username,
        password_hash=hash_password(password),
        active=True,
        created_at=_now(),
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, site_id=SITE, role=role))
    db.commit()
    return user


def admins(db: Session, site: int = SITE) -> int:
    """How many accounts are switched on and administrators here."""
    return (
        db.query(func.count(User.id))
        .join(Membership, Membership.user_id == User.id)
        .filter(Membership.site_id == site, Membership.role == ADMIN, User.active.is_(True))
        .scalar()
        or 0
    )


def _the_last_admin(db: Session, user: User) -> bool:
    return user.active and role_of(db, user) == ADMIN and admins(db) <= 1


def set_role(db: Session, user: User, role: str) -> None:
    check_role(role)
    if role != ADMIN and _the_last_admin(db, user):
        raise AccountError(
            f"{user.username} is the only administrator. Make somebody else one first."
        )
    m = db.get(Membership, (user.id, SITE))
    if m:
        m.role = role
    else:
        db.add(Membership(user_id=user.id, site_id=SITE, role=role))
    db.commit()


def set_active(db: Session, user: User, active: bool) -> None:
    """Switch an account on or off. Off ends its sessions there and then; its tokens
    are kept, and stop working because every check asks whether the account is on,
    so switching it back on is restoring it rather than rebuilding it."""
    if not active and _the_last_admin(db, user):
        raise AccountError(
            f"{user.username} is the only administrator. Make somebody else one first."
        )
    user.active = active
    if not active:
        db.query(UserSession).filter(UserSession.user_id == user.id).delete()
    db.commit()


def set_password(db: Session, user: User, password: str, keep: str = "") -> None:
    """A new password, which signs the account out everywhere -- except the session
    `keep` names, which is the browser the change was made from."""
    check_password(password)
    user.password_hash = hash_password(password)
    q = db.query(UserSession).filter(UserSession.user_id == user.id)
    if keep:
        q = q.filter(UserSession.digest != digest(keep))
    q.delete()
    db.commit()


# A hash of nothing anybody knows, verified against when a username matches no
# account, so a wrong username costs the same time as a wrong password and the
# login cannot be used to find out which usernames exist. Made on first use rather
# than at import: an argon2 hash is deliberately slow, and most imports of this
# module never sign anybody in.
_decoy: list[str] = []


def _decoy_hash() -> str:
    if not _decoy:
        _decoy.append(_hasher.hash(secrets.token_hex(16)))
    return _decoy[0]


def authenticate(db: Session, username: str, password: str) -> User | None:
    """The account these credentials are for, or None.

    Only the password. Opening a session is a separate step (`open_session`), so a
    second factor, when there is one, is a step between the two rather than a
    change to either."""
    user = find(db, username) if USERNAME.fullmatch(username.strip()) else None
    try:
        _hasher.verify(user.password_hash if user else _decoy_hash(), password)
    except (VerificationError, InvalidHashError):
        return None
    if user is None or not user.active:
        return None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user


def principal(db: Session, user: User, via: str) -> Principal:
    return Principal(
        user_id=user.id, username=user.username, role=role_of(db, user), site=SITE, via=via
    )


# --- sessions ---------------------------------------------------------------


def open_session(db: Session, user: User) -> str:
    """Sign this account in, and return the key for the browser's cookie."""
    key = secrets.token_urlsafe(32)
    now = _now()
    db.add(
        UserSession(
            digest=digest(key),
            user_id=user.id,
            created_at=now,
            expires_at=now + SESSION_LIFE,
            last_seen_at=now,
        )
    )
    user.last_login_at = now
    # Expired rows are swept here, on the way in, rather than by a job: signing in is
    # the one moment a row is added, so the table can never grow faster than this
    # keeps it trimmed.
    db.query(UserSession).filter(UserSession.expires_at < now).delete()
    db.commit()
    return key


def from_session(db: Session, key: str) -> Principal | None:
    row = db.query(UserSession).filter(UserSession.digest == digest(key)).one_or_none()
    now = _now()
    if row is None or row.expires_at < now:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.active:
        return None
    if row.last_seen_at is None or now - row.last_seen_at > SEEN_EVERY:
        row.last_seen_at = now
        db.commit()
    return principal(db, user, "session")


def end_session(db: Session, key: str) -> None:
    db.query(UserSession).filter(UserSession.digest == digest(key)).delete()
    db.commit()


# --- API tokens -------------------------------------------------------------


def make_token(db: Session, user: User, name: str) -> str:
    """A new token for this account, returned once and never again."""
    name = name.strip()
    if not name or len(name) > 100:
        raise AccountError("A token needs a name of up to 100 characters: what it is for.")
    key = TOKEN_PREFIX + secrets.token_urlsafe(32)
    db.add(ApiToken(digest=digest(key), user_id=user.id, name=name, created_at=_now()))
    db.commit()
    return key


def from_token(db: Session, key: str) -> Principal | None:
    if not key.startswith(TOKEN_PREFIX):
        return None
    row = db.query(ApiToken).filter(ApiToken.digest == digest(key)).one_or_none()
    if row is None:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.active:
        return None
    now = _now()
    if row.last_used_at is None or now - row.last_used_at > SEEN_EVERY:
        row.last_used_at = now
        db.commit()
    return principal(db, user, "token")


def revoke_token(db: Session, token_id: int) -> bool:
    gone = db.query(ApiToken).filter(ApiToken.id == token_id).delete()
    db.commit()
    return bool(gone)


@dataclass(frozen=True)
class TokenLine:
    """A token as a list shows it: never the key, which is not kept."""

    id: int
    username: str
    name: str
    created_at: datetime
    last_used_at: datetime | None


def tokens(db: Session, user_id: int | None = None) -> list[TokenLine]:
    """Every token, or one account's."""
    q = db.query(ApiToken, User.username).join(User, User.id == ApiToken.user_id)
    if user_id is not None:
        q = q.filter(ApiToken.user_id == user_id)
    rows = q.order_by(ApiToken.id).all()
    return [TokenLine(t.id, name, t.name, t.created_at, t.last_used_at) for t, name in rows]


# --- what the account pages read ----------------------------------------------


@dataclass(frozen=True)
class AccountLine:
    """An account as the Accounts page lists it."""

    id: int
    username: str
    role: str
    active: bool
    last_login_at: datetime | None


def accounts(db: Session) -> list[AccountLine]:
    rows = (
        db.query(User, Membership.role)
        .outerjoin(Membership, (Membership.user_id == User.id) & (Membership.site_id == SITE))
        .order_by(User.username)
        .all()
    )
    return [
        AccountLine(u.id, u.username, role or "", u.active, u.last_login_at) for u, role in rows
    ]


def password_is(user: User, password: str) -> bool:
    """Whether this is the account's password: asked again before it is changed, so
    a browser left signed in is not enough to take the account over."""
    try:
        return bool(_hasher.verify(user.password_hash, password))
    except (VerificationError, InvalidHashError):
        return False


@dataclass(frozen=True)
class SessionLine:
    """A signed-in browser, as the account page lists it. `here` is the one the
    list is being read in."""

    id: int
    created_at: datetime
    last_seen_at: datetime | None
    here: bool


def sessions_of(db: Session, user_id: int, key: str = "") -> list[SessionLine]:
    mine = digest(key) if key else ""
    rows = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.expires_at >= _now())
        .order_by(UserSession.created_at.desc())
        .all()
    )
    return [SessionLine(s.id, s.created_at, s.last_seen_at, s.digest == mine) for s in rows]


def end_other_sessions(db: Session, user_id: int, keep: str) -> int:
    """Sign this account out of every browser but the one holding `keep`."""
    gone = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.digest != digest(keep))
        .delete()
    )
    db.commit()
    return gone


def revoke_token_of(db: Session, user_id: int, token_id: int) -> bool:
    """Withdraw a token, only if it is this account's: the account page offers a
    person their own, and an id typed into its form must not reach anybody else's."""
    gone = db.query(ApiToken).filter(ApiToken.id == token_id, ApiToken.user_id == user_id).delete()
    db.commit()
    return bool(gone)
