"""The account pages: Settings -> Accounts for administrators, and Your account for
everybody who is signed in (ADR-0032).

Thin on purpose. What an account is, and every rule about changing one -- the
length of a password, the last administrator -- is `accounts/store.py`, which the
command line uses too, so the page and the command cannot come to disagree about
what is allowed. A refusal from there is shown on the page it came from, as the
store worded it.

Who may open which is the gate's: /settings/users is an administrator's like the
rest of /settings, and /settings/account is let through for anybody signed in.
"""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..accounts import store
from ..accounts.roles import ROLE_NAMES, VIEWER, Principal
from ..auth import COOKIE
from ..db import get_db
from ..forms import Posted, posted
from ..models import User
from ..web import templates

router = APIRouter()


def _principal(request: Request) -> Principal:
    return cast(Principal, request.state.principal)


def _me(db: Session, request: Request) -> User:
    p = _principal(request)
    user = db.get(User, p.user_id) if p.user_id is not None else None
    if user is None:
        raise HTTPException(404)
    return user


def _back(path: str, done: str) -> Response:
    """Post/redirect/get, with what was done in the address, the way the settings
    page says it saved."""
    return RedirectResponse(f"{path}?done={done}", status_code=303)


def _two(form: Posted) -> str:
    """The new password, if the two boxes agree; the refusal is the store's."""
    if form.get("password", "") != form.get("password2", ""):
        raise store.AccountError("The two passwords were not the same.")
    return form.get("password", "")


# --- your account -------------------------------------------------------------


def _account_page(request: Request, db: Session, status: int = 200, **extra: object) -> Response:
    me = _me(db, request)
    return templates.TemplateResponse(
        request,
        "settings_account.html",
        {
            "me": me,
            "role_name": ROLE_NAMES.get(store.role_of(db, me), ""),
            "sessions": store.sessions_of(db, me.id, request.cookies.get(COOKIE, "")),
            "tokens": store.tokens(db, me.id),
            "done": request.query_params.get("done", "")[:20],
            "noindex": True,
        }
        | extra,
        status_code=status,
    )


@router.get("/settings/account", include_in_schema=False)
def gui_account(request: Request, db: Session = Depends(get_db)) -> Response:
    return _account_page(request, db)


@router.post("/settings/account/password", include_in_schema=False)
async def gui_account_password(request: Request, db: Session = Depends(get_db)) -> Response:
    form = await posted(request)
    me = _me(db, request)
    try:
        if not await run_in_threadpool(store.password_is, me, form.get("current", "")):
            raise store.AccountError("That is not your password now.")
        new = _two(form)
        await run_in_threadpool(store.set_password, db, me, new, request.cookies.get(COOKIE, ""))
    except store.AccountError as e:
        return _account_page(request, db, 400, password_error=str(e))
    return _back("/settings/account", "password")


@router.post("/settings/account/sessions", include_in_schema=False)
def gui_account_sessions(request: Request, db: Session = Depends(get_db)) -> Response:
    store.end_other_sessions(db, _me(db, request).id, request.cookies.get(COOKIE, ""))
    return _back("/settings/account", "sessions")


@router.post("/settings/account/tokens", include_in_schema=False)
async def gui_account_token(request: Request, db: Session = Depends(get_db)) -> Response:
    """Answered with the page rather than a redirect: the key is shown this once,
    and a redirect would have to carry it in an address, which a browser keeps."""
    form = await posted(request)
    try:
        key = store.make_token(db, _me(db, request), form.get("name", ""))
    except store.AccountError as e:
        return _account_page(request, db, 400, token_error=str(e))
    return _account_page(request, db, new_token=key, new_token_name=form.get("name", "").strip())


@router.post("/settings/account/tokens/{token_id}/revoke", include_in_schema=False)
def gui_account_revoke(token_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    if not store.revoke_token_of(db, _me(db, request).id, token_id):
        raise HTTPException(404)
    return _back("/settings/account", "revoked")


# --- everybody's accounts -----------------------------------------------------


def _users_page(request: Request, db: Session, status: int = 200, **extra: object) -> Response:
    return templates.TemplateResponse(
        request,
        "settings_users.html",
        {
            "accounts": store.accounts(db),
            "roles": ROLE_NAMES,
            "done": request.query_params.get("done", "")[:20],
            "noindex": True,
            "form": {"username": "", "role": VIEWER},
        }
        | extra,
        status_code=status,
    )


@router.get("/settings/users", include_in_schema=False)
def gui_users(request: Request, db: Session = Depends(get_db)) -> Response:
    return _users_page(request, db)


@router.post("/settings/users", include_in_schema=False)
async def gui_add_user(request: Request, db: Session = Depends(get_db)) -> Response:
    form = await posted(request)
    username, role = form.get("username", "").strip(), form.get("role", VIEWER)
    try:
        await run_in_threadpool(store.create, db, username, _two(form), role)
    except store.AccountError as e:
        return _users_page(
            request, db, 400, error=str(e), form={"username": username, "role": role}
        )
    return _back("/settings/users", "added")


def _user(db: Session, uid: int) -> User:
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(404)
    return user


def _user_page(
    request: Request, db: Session, user: User, status: int = 200, **extra: object
) -> Response:
    return templates.TemplateResponse(
        request,
        "settings_user.html",
        {
            "u": user,
            "role": store.role_of(db, user),
            "roles": ROLE_NAMES,
            "tokens": store.tokens(db, user.id),
            "done": request.query_params.get("done", "")[:20],
            "noindex": True,
        }
        | extra,
        status_code=status,
    )


@router.get("/settings/users/{uid}", include_in_schema=False)
def gui_user(uid: int, request: Request, db: Session = Depends(get_db)) -> Response:
    return _user_page(request, db, _user(db, uid))


@router.post("/settings/users/{uid}/role", include_in_schema=False)
async def gui_user_role(uid: int, request: Request, db: Session = Depends(get_db)) -> Response:
    user = _user(db, uid)
    form = await posted(request)
    try:
        store.set_role(db, user, form.get("role", ""))
    except store.AccountError as e:
        return _user_page(request, db, user, 400, error=str(e))
    return _back(f"/settings/users/{uid}", "role")


@router.post("/settings/users/{uid}/active", include_in_schema=False)
async def gui_user_active(uid: int, request: Request, db: Session = Depends(get_db)) -> Response:
    """A tick, which posts nothing when it is off -- the reading every other tick in
    the register takes of the same silence."""
    user = _user(db, uid)
    form = await posted(request)
    try:
        store.set_active(db, user, bool(form.get("active")))
    except store.AccountError as e:
        return _user_page(request, db, user, 400, error=str(e))
    return _back(f"/settings/users/{uid}", "active")


@router.post("/settings/users/{uid}/password", include_in_schema=False)
async def gui_user_password(uid: int, request: Request, db: Session = Depends(get_db)) -> Response:
    user = _user(db, uid)
    form = await posted(request)
    try:
        await run_in_threadpool(store.set_password, db, user, _two(form))
    except store.AccountError as e:
        return _user_page(request, db, user, 400, password_error=str(e))
    return _back(f"/settings/users/{uid}", "password")


@router.post("/settings/users/{uid}/tokens/{token_id}/revoke", include_in_schema=False)
def gui_user_revoke(
    uid: int, token_id: int, request: Request, db: Session = Depends(get_db)
) -> Response:
    if not store.revoke_token_of(db, _user(db, uid).id, token_id):
        raise HTTPException(404)
    return _back(f"/settings/users/{uid}", "revoked")
