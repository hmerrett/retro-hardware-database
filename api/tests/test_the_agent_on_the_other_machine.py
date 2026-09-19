"""tools/print_agent.py, run against the real register and a real `lp`.

This is the half that runs on a machine nobody is sitting at, installed once and
then visited only when something has gone wrong. So it is exercised end to end
rather than trusted: a real HTTP connection to the real routes, and a real
`subprocess` call to an `lp` that records what it was handed.

What is faked is the printer, and only the printer.
"""

import importlib.util
import os
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
AGENTS = "workshop-pi:key-one:dymo-11355:pdf,bench:key-two:niimbot-50x30:png"


def agent_module():
    spec = importlib.util.spec_from_file_location("print_agent", TOOLS / "print_agent.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["print_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def agent():
    return agent_module()


@pytest.fixture
def served(client, monkeypatch):
    """The register on a real socket, so the agent reaches it the way it will on
    the Pi -- through urllib, over TCP, with its own headers."""
    monkeypatch.setenv("RHDB_PRINT_AGENTS", AGENTS)

    class Handler(BaseHTTPRequestHandler):
        def _pass_on(self, method: str) -> None:
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower() in ("authorization", "content-type")
            }
            r = client.request(method, self.path, content=body, headers=headers)
            self.send_response(r.status_code)
            self.send_header("content-type", r.headers.get("content-type", "application/json"))
            self.send_header("content-length", str(len(r.content)))
            self.end_headers()
            self.wfile.write(r.content)

        def do_GET(self) -> None:
            self._pass_on("GET")

        def do_POST(self) -> None:
            self._pass_on("POST")

        def log_message(self, *_args) -> None:
            """Quiet: the suite's output is not a web server's access log."""

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def fake_lp(tmp_path, monkeypatch):
    """An `lp` that records its arguments instead of printing.

    A script on PATH and not a patched function: what is being checked is the
    command line the agent builds, which a stub inside the process would not see.
    """
    log = tmp_path / "lp.log"
    script = tmp_path / "lp"
    # POSIX sh, and the last argument found by walking them: `${@: -1}` is bash's
    # and /bin/sh here is dash, where it is a syntax error -- which showed up as
    # `lp` succeeding and the label never being written.
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> {log}\n'
        'for f in "$@"; do last=$f; done\n'
        f'cat "$last" > {tmp_path}/last-label 2>/dev/null\n'
        "exit ${LP_EXIT:-0}\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    return log


@pytest.fixture
def queue(client, part):
    def send(**body):
        card = part(manufacturer="Seagate", model="ST-225", type="storage")
        r = client.post(
            "/api/print/jobs",
            json={"agent": "workshop-pi", "kind": "part", "asset_id": card["asset_id"]} | body,
        )
        assert r.status_code == 200, r.text
        return r.json(), card

    return send


def states(client):
    return [j["state"] for j in client.get("/api/print/jobs").json()]


def test_it_claims_prints_and_reports_in_one_pass(agent, served, queue, fake_lp, client, tmp_path):
    """The whole of what it does, done once. `--once` is what to run first on a new
    machine: it prints what is waiting and stops, so a first installation is proved
    without anything being left running."""
    queue()
    assert agent.main(["--api", served, "--key", "key-one", "--printer", "TEST", "--once"]) == 0
    assert fake_lp.exists(), "lp was never called"
    assert "-d TEST" in fake_lp.read_text()
    assert (tmp_path / "last-label").read_bytes().startswith(b"%PDF")
    assert states(client) == ["done"]


def test_it_prints_everything_waiting_not_just_the_first(agent, served, queue, fake_lp, client):
    queue()
    queue()
    queue()
    agent.main(["--api", served, "--key", "key-one", "--once"])
    assert len(fake_lp.read_text().strip().splitlines()) == 3
    assert states(client) == ["done", "done", "done"]


def test_it_asks_for_as_many_copies_as_the_job_says(agent, served, queue, fake_lp):
    queue(copies=3)
    agent.main(["--api", served, "--key", "key-one", "--once"])
    assert "-n 3" in fake_lp.read_text()


def test_one_copy_does_not_ask_for_a_number(agent, served, queue, fake_lp):
    """`lp -n 1` is the same as `lp`, and a command line that says only what it
    means is one somebody can read in a log."""
    queue()
    agent.main(["--api", served, "--key", "key-one", "--once"])
    assert "-n" not in fake_lp.read_text()


def test_it_fetches_the_format_the_job_asked_for(agent, served, queue, fake_lp, tmp_path):
    queue(format="png", media="niimbot-50x30")
    agent.main(["--api", served, "--key", "key-one", "--once"])
    assert (tmp_path / "last-label").read_bytes().startswith(b"\x89PNG")


def test_nothing_waiting_is_a_quiet_no(agent, served, fake_lp, client):
    """An agent asks for ever; an empty queue must not print, must not report and
    must not read as a fault."""
    assert agent.main(["--api", served, "--key", "key-one", "--once"]) == 0
    assert not fake_lp.exists()


def test_a_printer_that_refuses_is_reported_back_in_its_own_words(
    agent, served, queue, fake_lp, client, monkeypatch
):
    """So the answer to "why has nothing come out" is on the screen in the room the
    label was sent from, rather than in a log on a Pi under a bench."""
    monkeypatch.setenv("LP_EXIT", "1")
    queue()
    agent.main(["--api", served, "--key", "key-one", "--once"])
    job = client.get("/api/print/jobs").json()[0]
    assert job["state"] == "failed"
    assert job["error"]


def test_a_wrong_key_stops_rather_than_retrying_for_ever(agent, served, queue, fake_lp):
    """A key the register does not know will not start working. Backing off and
    asking again for ever would hide the one fault a person has to fix."""
    queue()
    with pytest.raises(SystemExit):
        agent.main(["--api", served, "--key", "not-a-key", "--once"])
    assert not fake_lp.exists()


def test_an_item_deleted_before_it_prints_is_let_go(agent, served, queue, fake_lp, client):
    """The register has already failed the job by the time it answers, so there is
    nothing for the agent to print and nothing for it to report."""
    _, card = queue()
    assert client.delete(f"/api/parts/{card['asset_id']}").status_code == 200
    assert agent.main(["--api", served, "--key", "key-one", "--once"]) == 0
    assert not fake_lp.exists()
    assert states(client) == ["failed"]


def test_a_dry_run_prints_nothing_and_leaves_the_label_to_look_at(
    agent, served, queue, fake_lp, client, tmp_path, monkeypatch
):
    """For proving the connection on a machine that has no printer attached yet,
    which is the state this was written in."""
    monkeypatch.setattr(agent.tempfile, "tempdir", str(tmp_path))
    queue()
    assert agent.main(["--api", served, "--key", "key-one", "--once", "--dry-run"]) == 0
    assert not fake_lp.exists()
    assert states(client) == ["done"]
    written = list(tmp_path.glob("rhdb-*.pdf"))
    assert len(written) == 1 and written[0].read_bytes().startswith(b"%PDF")


def test_it_needs_to_be_told_where_the_register_is(agent, capsys):
    """Rather than defaulting to something and failing somewhere less obvious."""
    with pytest.raises(SystemExit):
        agent.main(["--key", "key-one", "--once"])


def test_the_label_is_not_left_lying_about_after_it_prints(
    agent, served, queue, fake_lp, tmp_path, monkeypatch
):
    """A register behind a login does not leave its labels in /tmp on a machine
    other people use."""
    monkeypatch.setattr(agent.tempfile, "tempdir", str(tmp_path))
    queue()
    agent.main(["--api", served, "--key", "key-one", "--once"])
    assert not list(tmp_path.glob("rhdb-*.pdf"))


def test_the_service_file_matches_the_script_it_starts(agent):
    """The unit file is what actually gets installed, and a wrong path or a
    variable the script does not read is a fault discovered by ssh."""
    unit = (TOOLS / "print-agent.service").read_text()
    assert "print_agent.py" in unit
    for name in ("RHDB_API", "RHDB_PRINT_KEY", "RHDB_PRINTER"):
        assert f"Environment={name}=" in unit
    assert "Restart=always" in unit


def test_it_says_what_it_did(agent, served, queue, fake_lp, caplog):
    """The journal on the Pi is the only place anybody can look when the register
    says a job failed but not why."""
    import logging

    _, card = queue()
    with caplog.at_level(logging.INFO):
        agent.main(["--api", served, "--key", "key-one", "--once"])
    assert card["asset_id"] in caplog.text
    assert "printed" in caplog.text
