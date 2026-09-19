"""Where the database is.

DATABASE_URL used to default to `mysql+pymysql://retro:retro@db:3306/retro`. Under
compose nobody ever met that default -- DB_PASSWORD is `${VAR:?message}`, so a
missing value stops the stack long before the app imports anything -- but nothing
outside compose has that guard. On Kubernetes a Secret missing the key is simply an
unset variable, and the app did not fail: it quietly tried a guessable password on
a host called db. Found by standing the stack up on k3s (docs/deploying-on-k3s.md),
which is what that exercise was for.
"""

import pytest

from app.db import _resolve_database_url


def test_uses_the_configured_url_when_present():
    url = "mysql+pymysql://retro:pw@db:3306/retro"
    assert _resolve_database_url(url) == url


def test_refuses_to_start_without_one():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _resolve_database_url("")


def test_says_how_to_set_it_rather_than_only_that_it_is_missing():
    # The message is the whole value of failing here rather than at the first query,
    # where the traceback would be about a connection and not about configuration.
    with pytest.raises(RuntimeError) as raised:
        _resolve_database_url("")
    assert "mysql+pymysql://" in str(raised.value)


def test_the_message_carries_no_password_anybody_could_paste():
    # The old default is what this test keeps out: an example with a real-looking
    # password in it is an example somebody will paste into a running installation.
    with pytest.raises(RuntimeError) as raised:
        _resolve_database_url("")
    assert "retro:retro" not in str(raised.value)
