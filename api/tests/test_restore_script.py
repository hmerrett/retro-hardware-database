"""What tools/restore.sh promises, read off the script itself.

It is shell, and only runs against a live stack, so like the entrypoint tests in
test_deployment.py these read the shipped file. Each one pins something that went
wrong, or would go wrong quietly, if the script were edited without it. The script
was exercised end to end when written: a backup of a seeded stack restored into a
fresh one, every table's count and every archived file checked.
"""
from pathlib import Path

RESTORE = (Path(__file__).resolve().parents[2] / "tools" / "restore.sh").read_text()


def _code():
    """The script without its comments, so a check reads what runs."""
    return "\n".join(ln for ln in RESTORE.splitlines() if not ln.lstrip().startswith("#"))


class TestItDoesNothingUntilTheBackupIsWhole:
    """A truncated archive found halfway through leaves the stack with the new
    database and the old photographs. Found first, it leaves the stack as it was."""

    def test_every_archive_is_read_through_before_the_database_is_loaded(self):
        code = _code()
        load = code.index("mariadb -uroot\n")
        for check in ('gzip -t "$DUMP"', 'tar -tzf "$IMAGES"', 'tar -tzf "$FILES"'):
            assert code.index(check) < load, check

    def test_it_asks_before_replacing_the_database(self):
        code = _code()
        assert code.index("read -r -p") < code.index("mariadb -uroot\n")
        assert 'RHDB_RESTORE_YES:-}" != "1"' in code


class TestItsChecksCannotPassByAccident:
    """The checks are the point: a restore that says "checked" when it checked one
    table of twenty-nine is worse than one that says nothing."""

    def test_the_query_in_the_table_loop_cannot_read_the_loop_s_input(self):
        """`docker compose exec` reads standard input. Inside a loop fed the list of
        tables, the first query swallowed the rest, and the script reported the
        restore checked after looking at alembic_version alone. It did, once."""
        sql = RESTORE.split("sql() {", 1)[1].split("\n}", 1)[0]
        assert sql.rstrip().endswith("</dev/null")

    def test_it_counts_the_tables_it_checked_against_the_dump(self):
        assert 'problem "checked $checked of the $tables tables in the dump"' in RESTORE

    def test_a_problem_makes_it_exit_non_zero(self):
        """So a cron job or a CI step that restores to prove a backup fails loudly."""
        tail = _code().rsplit('if [ "$problems" -gt 0 ]; then', 1)[1]
        assert "exit 1" in tail.split("fi", 1)[0]
