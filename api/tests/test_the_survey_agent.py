"""tools/survey_agent.py, run against the real register and a real folder.

The half of a survey that runs beside the machines being surveyed, on a computer
that can read the folder their reports are written into. It answers their
questions, sends their reports and writes back what the register said, and it
talks to them only through files a DOS machine can read (MANUAL §23, ADR-0043).

So it is exercised end to end, as the print agent is: a real HTTP connection to
the real routes, and a real folder on disk. What is faked is the machine, and
only the machine: its files are written here as it would have left them.
"""

import importlib.util
import logging
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
AGENTS = "bench:key-one"

# What a DOS machine can open: eight characters, a dot and three.
EIGHT_DOT_THREE = re.compile(r"^[A-Z0-9_-]{1,8}(\.[A-Z0-9_-]{1,3})?$", re.I)


def agent_module():
    path = TOOLS / "survey_agent.py"
    assert path.exists(), "tools/survey_agent.py has not been written yet"
    spec = importlib.util.spec_from_file_location("survey_agent", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["survey_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def agent():
    return agent_module()


@pytest.fixture
def served(client, monkeypatch):
    """The register on a real socket, so the agent reaches it the way it will on
    the file server: through urllib, over TCP, with its own headers. The same
    stand-in the print agent's tests use."""
    monkeypatch.setenv("RHDB_SURVEY_AGENTS", AGENTS)

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
def folder(tmp_path):
    """The folder the machines write into, as the file server shares it."""
    made = tmp_path / "surveys"
    made.mkdir()
    return made


def leave(where: Path, name: str, text: str, age: float = 60) -> Path:
    """A file as a machine left it, `age` seconds ago, in DOS's own encoding."""
    path = where / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", "\r\n").encode("cp437"))
    then = time.time() - age
    os.utime(path, (then, then))
    return path


def report(*extra: str) -> str:
    """A report as a survey program writes one: words for the person reading it,
    then the [RHDB] section."""
    lines = [
        "DIAG 1.0  hardware report",
        "Every test passed.",
        "",
        "[RHDB]",
        "TOOL=DIAG",
        "VERSION=1.0",
        "TAG=",
        "MODE=ONCE",
        "RESULT=PASS",
        "TESTS=1",
        "TEST_CPU=PASS",
        "CPU=80286",
        "CPUKHZ=12000",
        *extra,
    ]
    return "\n".join(lines) + "\n"


def run(agent, api, folder, key="key-one"):
    return agent.main(["--api", api, "--key", key, "--dir", str(folder), "--once"])


def surveys(client):
    r = client.get("/api/surveys")
    assert r.status_code == 200, r.text
    return r.json()


# --- a question, answered beside it -------------------------------------------


def test_a_question_is_answered_beside_it(agent, served, folder, client, computer, part):
    """The machine asks before it tests anything, so that a machine the register
    knows is named on its screen and nothing is asked of whoever is there."""
    machine = computer()
    part(
        type="storage",
        model="FIREBALL1080A",
        serial="QX123",
        computer_id=machine["asset_id"],
        specs="Kind: Hard disk | Interface: IDE",
    )
    leave(folder, "M1.ASK", "[RHDB]\nDISK1_SERIAL=QX123\n")
    assert run(agent, served, folder) == 0
    answer = (folder / "M1.ANS").read_text(encoding="cp437")
    assert f"TAG={machine['asset_id']}" in answer


def test_a_question_is_not_a_survey(agent, served, folder, client):
    """Asking writes nothing: the serial number in a question is recorded when the
    survey that carries it arrives, and not before."""
    leave(folder, "M1.ASK", "[RHDB]\nDISK1_SERIAL=QX123\n")
    run(agent, served, folder)
    assert surveys(client) == []
    seen = client.get("/surveys/seen")
    assert seen.status_code == 200, seen.text
    assert "QX123" not in seen.text


# --- a report, sent once it is finished ---------------------------------------


def test_a_report_is_sent_and_its_receipt_written_beside_it(agent, served, folder, client):
    leave(folder, "RH0001.TXT", report())
    assert run(agent, served, folder) == 0
    assert len(surveys(client)) == 1
    assert (folder / "RH0001.RCT").read_text(encoding="cp437").strip()
    assert (folder / "SENT" / "RH0001.TXT").exists()
    assert not (folder / "RH0001.TXT").exists()


def test_a_report_is_sent_once(agent, served, folder, client):
    """SENT is a folder inside the one it watches, and what is in it has gone."""
    leave(folder, "RH0001.TXT", report())
    run(agent, served, folder)
    run(agent, served, folder)
    assert len(surveys(client)) == 1


def test_a_report_still_being_written_is_left_alone(agent, served, folder, client):
    """A report is sent once it has been left alone for ten seconds. A file still
    arriving over the network drive is half a report."""
    leave(folder, "RH0001.TXT", report(), age=2)
    run(agent, served, folder)
    assert surveys(client) == []
    assert (folder / "RH0001.TXT").exists()
    assert not (folder / "RH0001.RCT").exists()


def test_the_receipt_is_lines_a_dos_screen_can_show(agent, served, folder):
    """The survey program shows it as it is: short lines, in the machine's own
    character set, ending the way DOS ends a line."""
    leave(folder, "RH0001.TXT", report())
    run(agent, served, folder)
    raw = (folder / "RH0001.RCT").read_bytes()
    text = raw.decode("cp437")
    assert "\r\n" in text
    assert all(len(line) <= 79 for line in text.split("\r\n"))


def test_its_roms_go_into_sent_with_it(agent, served, folder):
    leave(folder, "RH0001.TXT", report("ROM1=F000 65536 BIOS.BIN"))
    rom = folder / "BIOS.BIN"
    rom.write_bytes(b"\x55\xaa" + b"Award Modular BIOS v4.51PG" + b"\0" * 64)
    os.utime(rom, (time.time() - 60, time.time() - 60))
    run(agent, served, folder)
    assert (folder / "SENT" / "BIOS.BIN").exists()
    assert not rom.exists()


def test_reports_in_folders_inside_it_are_sent_too(agent, served, folder, client):
    """A boot network may give each machine a folder of its own."""
    leave(folder / "PC2286", "RH0001.TXT", report())
    run(agent, served, folder)
    assert len(surveys(client)) == 1
    assert (folder / "PC2286" / "RH0001.RCT").exists()


def test_a_file_with_no_rhdb_section_is_not_a_report(agent, served, folder, client):
    """Notes, a README, a soak's log: the folder is a shared drive, and the agent
    sends only what a survey program wrote for it."""
    leave(folder, "NOTES.TXT", "The 286 needs a new clock battery.\n")
    run(agent, served, folder)
    assert surveys(client) == []
    assert (folder / "NOTES.TXT").exists()


def test_a_report_copied_in_from_a_floppy_is_sent_like_any_other(agent, served, folder, client):
    """A machine with no network carries its report on a floppy, and the file keeps
    the date it was written."""
    leave(folder, "RH0001.TXT", report(), age=30 * 24 * 3600)
    run(agent, served, folder)
    assert len(surveys(client)) == 1


# --- a soak, sent when it stops -------------------------------------------------


def test_a_soak_still_running_is_left_alone(agent, served, folder, client):
    """A soak rewrites its report after every pass. Sending each one would be a
    survey for every pass of a machine left running overnight."""
    leave(folder, "SOAK.TXT", report("MODE=SOAK", "PASSES=3"), age=30 * 60)
    run(agent, served, folder)
    assert surveys(client) == []


def test_a_soak_that_stopped_is_sent(agent, served, folder, client):
    leave(folder, "RH0001.TXT", report("MODE=SOAK", "PASSES=48", "STOPPED=ESC"))
    run(agent, served, folder)
    assert len(surveys(client)) == 1


def test_a_soak_left_alone_for_an_hour_is_sent_as_it_stands(agent, served, folder, client):
    """Because the machine was switched off part-way, which is how most soaks end."""
    leave(folder, "SOAK.TXT", report("MODE=SOAK", "PASSES=48"), age=61 * 60)
    run(agent, served, folder)
    assert len(surveys(client)) == 1


# --- what the register would not take, and what it could not be sent ------------


def test_a_report_the_register_refuses_moves_into_refused_with_the_reason(
    agent, served, folder, client
):
    leave(folder, "RH0001.TXT", "DIAG 1.0\n\n[RHDB]\n")
    run(agent, served, folder)
    assert surveys(client) == []
    assert (folder / "REFUSED" / "RH0001.TXT").exists()
    assert (folder / "REFUSED" / "RH0001.WHY").read_text(encoding="cp437").strip()


def test_a_refused_report_says_so_where_the_machine_is_waiting(agent, served, folder):
    """The machine waits for a receipt; one that never came would leave whoever is
    at it watching a screen that will not change."""
    leave(folder, "RH0001.TXT", "DIAG 1.0\n\n[RHDB]\n")
    run(agent, served, folder)
    said = (folder / "RH0001.RCT").read_text(encoding="cp437")
    assert "REFUSED" in said


def test_a_report_it_could_not_deliver_stays_and_is_tried_again(agent, served, folder, client):
    """An agent with no register to talk to is not an error: the report waits in
    its folder until it can be sent."""
    leave(folder, "RH0001.TXT", report())
    assert run(agent, "http://127.0.0.1:9", folder) == 0
    assert (folder / "RH0001.TXT").exists()
    assert not (folder / "SENT").exists() and not (folder / "REFUSED").exists()
    run(agent, served, folder)
    assert len(surveys(client)) == 1


def test_every_name_it_writes_fits_eight_characters_and_three(agent, served, folder):
    """So a DOS machine can read every file the agent writes."""
    leave(folder, "M1.ASK", "[RHDB]\nDISK1_SERIAL=QX123\n")
    leave(folder, "RH0001.TXT", report())
    leave(folder, "RH0002.TXT", "DIAG 1.0\n\n[RHDB]\n")
    run(agent, served, folder)
    written = [p.relative_to(folder) for p in folder.rglob("*")]
    assert written
    for path in written:
        for part in path.parts:
            assert EIGHT_DOT_THREE.match(part), f"{path} is not a name DOS can open"


# --- a key, and being told where the register is ---------------------------------


def test_a_wrong_key_stops_rather_than_retrying_for_ever(agent, served, folder):
    """A key the register does not know will not start working, and asking again
    for ever would hide the one fault a person has to fix."""
    leave(folder, "RH0001.TXT", report())
    with pytest.raises(SystemExit) as stopped:
        run(agent, served, folder, key="not-a-key")
    assert stopped.value.code == agent.EX_CONFIG
    assert (folder / "RH0001.TXT").exists()


def test_check_says_the_key_works(agent, served, folder, caplog):
    with caplog.at_level(logging.INFO):
        assert (
            agent.main(["--api", served, "--key", "key-one", "--dir", str(folder), "--check"]) == 0
        )
    assert "the key works" in caplog.text


def test_check_on_a_wrong_key_says_so_in_the_code_the_unit_stops_on(agent, served, folder):
    code = agent.main(["--api", served, "--key", "not-a-key", "--dir", str(folder), "--check"])
    assert code == agent.EX_CONFIG


def test_it_needs_to_be_told_where_the_register_is(agent, folder):
    assert agent.main(["--key", "key-one", "--dir", str(folder), "--once"]) == agent.EX_CONFIG


def test_it_needs_to_be_told_which_folder_to_watch(agent, served):
    assert agent.main(["--api", served, "--key", "key-one", "--once"]) == agent.EX_CONFIG


# --- the unit file ---------------------------------------------------------------


def test_the_service_file_matches_the_script_it_starts(agent):
    unit = (TOOLS / "survey-agent.service").read_text()
    assert "survey_agent.py" in unit
    assert "Restart=always" in unit
    assert f"RestartPreventExitStatus={agent.EX_CONFIG}" in unit


def test_the_unit_and_the_script_agree_on_what_is_set(agent):
    """A variable in the unit that the script ignores, or one the script needs and
    the unit leaves out, is a service that does nothing and says nothing."""
    unit = (TOOLS / "survey-agent.service").read_text()
    script = (TOOLS / "survey_agent.py").read_text()
    for name in re.findall(r"^Environment=(RHDB_[A-Z0-9_]+)=", unit, re.M):
        assert f'"{name}"' in script, f"the unit sets {name} and the agent never reads it"
    for name in set(re.findall(r'os\.getenv\("(RHDB_[A-Z0-9_]+)"', script)):
        assert f"Environment={name}=" in unit, f"the agent reads {name} and the unit never sets it"


def test_the_unit_names_what_the_manual_names(agent):
    unit = (TOOLS / "survey-agent.service").read_text()
    for name in ("RHDB_API", "RHDB_SURVEY_AGENT", "RHDB_SURVEY_KEY", "RHDB_SURVEY_DIR"):
        assert f"Environment={name}=" in unit
