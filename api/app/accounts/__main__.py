"""The accounts command: `python -m app.accounts`, run inside the app's container.

    docker compose exec api python -m app.accounts list

It is how accounts are managed until there are pages for it, and it stays as the
way back in when every administrator's password is lost. It asks for nothing
beyond being run: whoever can run a command in the container can read the
database already, so a password here would guard nothing (ADR-0032).

A password is asked for twice and not echoed. When nothing is at the keyboard --
a script, a pipe -- one line is read from standard input instead, so it never has
to be written on the command line, where it would be kept in a shell's history.
"""

import argparse
import getpass
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import TextIO

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import User
from . import store
from .roles import ROLE_NAMES, ROLES, VIEWER


def _password(stdin: TextIO) -> str:
    if not stdin.isatty():
        return stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if getpass.getpass("Again: ") != first:
        raise store.AccountError("The two passwords were not the same.")
    return first


def _when(d: datetime | None) -> str:
    return d.strftime("%Y-%m-%d %H:%M") if d else "never"


def _user(db: Session, username: str) -> User:
    user = store.find(db, username)
    if user is None:
        raise store.AccountError(f"There is no account called {username}.")
    return user


def run(argv: Sequence[str], stdin: TextIO = sys.stdin, out: TextIO = sys.stdout) -> int:
    p = argparse.ArgumentParser(
        prog="python -m app.accounts", description="Accounts, roles, passwords and API tokens."
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="every account, its role and when it last signed in")
    a = sub.add_parser("add", help="a new account; asks for its password")
    a.add_argument("username")
    a.add_argument("--role", choices=list(ROLES), default=VIEWER)
    sub.add_parser("password", help="set an account's password").add_argument("username")
    r = sub.add_parser("role", help="change an account's role")
    r.add_argument("username")
    r.add_argument("role", choices=list(ROLES))
    sub.add_parser("disable", help="switch an account off").add_argument("username")
    sub.add_parser("enable", help="switch an account back on").add_argument("username")
    t = sub.add_parser("token", help="a new API token for an account, printed once")
    t.add_argument("username")
    t.add_argument("name", help="what it is for, e.g. 'tool server'")
    sub.add_parser("tokens", help="every API token, and when each was last used")
    sub.add_parser("revoke", help="withdraw an API token").add_argument("id", type=int)
    args = p.parse_args(argv)

    with SessionLocal() as db:
        try:
            if args.cmd == "list":
                for u in db.query(User).order_by(User.username).all():
                    role = ROLE_NAMES.get(store.role_of(db, u), "no role")
                    state = "" if u.active else "  (switched off)"
                    print(
                        f"{u.username:24} {role:14} last in {_when(u.last_login_at)}{state}",
                        file=out,
                    )
            elif args.cmd == "add":
                store.create(db, args.username, _password(stdin), args.role)
                print(f"Made {args.username}, {ROLE_NAMES[args.role].lower()}.", file=out)
            elif args.cmd == "password":
                store.set_password(db, _user(db, args.username), _password(stdin))
                print(f"Changed; {args.username} is signed out everywhere.", file=out)
            elif args.cmd == "role":
                store.set_role(db, _user(db, args.username), args.role)
                print(f"{args.username} is now {ROLE_NAMES[args.role].lower()}.", file=out)
            elif args.cmd in ("disable", "enable"):
                store.set_active(db, _user(db, args.username), args.cmd == "enable")
                print(
                    f"{args.username} is switched {'on' if args.cmd == 'enable' else 'off'}.",
                    file=out,
                )
            elif args.cmd == "token":
                key = store.make_token(db, _user(db, args.username), args.name)
                print(key, file=out)
                print("Shown once: keep it now. It is not stored.", file=sys.stderr)
            elif args.cmd == "tokens":
                for line in store.tokens(db):
                    print(
                        f"{line.id:4}  {line.username:20} {line.name:24} "
                        f"made {_when(line.created_at)}  last used {_when(line.last_used_at)}",
                        file=out,
                    )
            elif args.cmd == "revoke":
                if not store.revoke_token(db, args.id):
                    raise store.AccountError(f"There is no token {args.id}.")
                print(f"Token {args.id} revoked.", file=out)
        except store.AccountError as e:
            print(e, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
