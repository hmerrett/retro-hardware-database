#!/usr/bin/env python3
"""The half of a survey that runs beside the machines being surveyed.

A machine surveying itself writes files into a folder on its network drive, and
this reads that folder from the server the drive lives on. It answers the machine's
question before its tests, sends its report once it is finished, and writes back
what the register said -- all as files, because a DOS machine on a boot network
can write a file and cannot speak HTTPS (MANUAL §23, ADR-0043).

Standard library only, and no shared code with the rest of `tools/`, for the same
reason as the print agent: it goes on a file server you visit when something is
wrong, and a thing that needs a virtualenv built for it there does not get deployed.

    export RHDB_API=https://db.example.com
    export RHDB_SURVEY_AGENT=bench
    export RHDB_SURVEY_KEY=...            # this agent's key, from the server's .env
    export RHDB_SURVEY_DIR=/srv/surveys   # the folder the machines write into
    python3 survey_agent.py

    python3 survey_agent.py --check     # what it is set up with, and try the key
    python3 survey_agent.py --once      # one pass over the folder, then stop

What it reads and writes, in the folder and every folder inside it:

    M1.ASK   a question: what a machine has found so far, and its tag once typed
    M1.ANS   the answer, written beside it
    RH01.TXT a report: any other file with an [RHDB] section
    RH01.RCT the register's receipt, written beside it once it is sent
    SENT\\    where a sent report and its ROMs go
    REFUSED\\ where a report the register would not take goes, with a .WHY
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("survey-agent")

# How often it looks. A question is somebody at a machine waiting for its name to
# come up on the screen, so this is short; a look at a folder of a few files costs
# nothing.
POLL_SECONDS = 2.0

# How long a file has to be left alone before it is taken to be finished. A report
# arrives over the network drive a sector at a time, and half of one is not a
# report. A question is a few lines written at once.
SETTLE_REPORT = 10.0
SETTLE_QUESTION = 1.0

# A soak rewrites its report after every pass, so one still running is left alone
# until it stops -- or until it has not changed for this long, which means the
# machine was switched off part-way, the way most soaks end.
SETTLE_SOAK = 3600.0

# What to wait after failing to reach the register, doubling up to the cap, so a
# register being redeployed is not hammered by every agent pointed at it.
BACKOFF_START, BACKOFF_MAX = 5.0, 120.0

TIMEOUT = 60

# The register's own ceilings. A file bigger than a report can be is not read to
# find out whether it is one.
MOST_REPORT = 4 * 1024 * 1024
MOST_ROM = 1024 * 1024

# No survey was taken before surveys existed. A file dated earlier carries the clock
# of the machine that wrote it -- a floppy's report, from a machine whose battery
# went years ago -- and says nothing about when, so the agent's own clock answers.
EARLIEST = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()

# The same reading the register gives a report: a line `[RHDB]`, then KEY=VALUE
# lines until one that is not. Kept in step with api/app/surveyreport.py by hand,
# since this file shares no code with it on purpose.
SECTION = "[RHDB]"
KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
ROM_KEY = re.compile(r"^ROM\d+$")

QUESTION, ANSWER, RECEIPT, REASON = ".ASK", ".ANS", ".RCT", ".WHY"
# DOS's own name for a file still being made: what this agent writes first and then
# renames, so a machine never opens half of one.
MAKING = ".$$$"
SENT, REFUSED = "SENT", "REFUSED"
# What this agent writes, and so never reads back as a report.
OURS = {QUESTION, ANSWER, RECEIPT, REASON, MAKING}

# Exit status for a fault in how it was set up rather than anything that might
# pass: the unit file will not restart on it, because a key the register does not
# know will not start being one, and retrying it every ten seconds only earns the
# address a rate limit (the print agent learnt this first). sysexits.h's EX_CONFIG.
EX_CONFIG = 78


class Undelivered(RuntimeError):
    """The register could not be asked, or did not answer. Whatever was being sent
    stays where it is and is tried again."""


class Server:
    """The register, as this agent talks to it: two requests and a bearer key."""

    def __init__(self, base: str, key: str) -> None:
        self.base = base.rstrip("/")
        self.key = key

    def _open(self, path: str, body: bytes, content_type: str) -> tuple[int, bytes]:
        req = urllib.request.Request(self.base + path, data=body, method="POST")
        req.add_header("Authorization", "Bearer " + self.key)
        req.add_header("User-Agent", "rhdb-survey-agent/1")
        req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return int(r.status), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise Undelivered(f"cannot reach {self.base}: {e}") from e

    def _refused_key(self, status: int) -> None:
        if status == 401:
            log.error(
                "the register does not recognise this agent's key -- check "
                "RHDB_SURVEY_KEY against RHDB_SURVEY_AGENTS on the server"
            )
            raise SystemExit(EX_CONFIG)
        if status == 429:
            # Its rate limiter, which counts wrong keys: almost always the tail of
            # an earlier mistake rather than anything this attempt did.
            raise Undelivered("the register is rate-limiting this address; it clears in 5 minutes")

    def ask(self, question: bytes) -> str:
        status, body = self._open("/api/survey/agent/ask", question, "text/plain")
        self._refused_key(status)
        if status != 200:
            raise Undelivered(f"the question was answered {status}: {body[:200]!r}")
        return body.decode("utf-8", "replace")

    def send(
        self, report: Path, raw: bytes, roms: list[Path], taken: str
    ) -> tuple[bool, dict[str, object]]:
        """(True, the register's answer) for a report taken; (False, the reason) for
        one it refused."""
        parts: list[tuple[str, str, bytes]] = [("report", report.name, raw)]
        parts += [("roms", rom.name, rom.read_bytes()) for rom in roms]
        body, content_type = multipart({"taken": taken}, parts)
        status, answer = self._open("/api/survey/agent/surveys", body, content_type)
        self._refused_key(status)
        if status == 422:
            return False, {"reason": _detail(answer)}
        if status != 200:
            raise Undelivered(f"the report was answered {status}: {answer[:200]!r}")
        got = json.loads(answer)
        return True, got if isinstance(got, dict) else {}


def _detail(body: bytes) -> str:
    """The reason in a refusal, which FastAPI sends as {"detail": ...}."""
    try:
        got = json.loads(body)
    except ValueError:
        return body.decode("utf-8", "replace").strip() or "The register refused it."
    detail = got.get("detail") if isinstance(got, dict) else None
    if isinstance(detail, str):
        return detail
    return json.dumps(detail) if detail else "The register refused it."


def multipart(fields: dict[str, str], files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    """A multipart/form-data body, by hand: urllib has no encoder for one."""
    boundary = "rhdb-" + uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += value.encode() + b"\r\n"
    for name, filename, data in files:
        safe = filename.replace('"', "").replace("\r", "").replace("\n", "")
        out += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{safe}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


# --- reading what a machine left -----------------------------------------------------


def decode(raw: bytes) -> str:
    """DOS text is code page 437; anything that is valid UTF-8 is read as that."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp437")


def sections(text: str) -> list[dict[str, str]] | None:
    """The keys of each [RHDB] section in a file, or None for a file with none --
    which is not a report, however it is named."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[dict[str, str]] = []
    at = 0
    while at < len(lines):
        if lines[at].strip().upper() != SECTION:
            at += 1
            continue
        keys: dict[str, str] = {}
        at += 1
        while at < len(lines) and (found := KEY_LINE.match(lines[at].strip())):
            keys[found.group(1)] = found.group(2).strip()
            at += 1
        out.append(keys)
    return out or None


def soaking(found: list[dict[str, str]]) -> bool:
    """A soak that has not said it stopped is still running."""
    return any(k.get("MODE", "").upper() == "SOAK" and not k.get("STOPPED") for k in found)


def dos_name(stem: str, ext: str) -> str:
    """A name a DOS machine can open: eight characters, a dot and three."""
    clean = re.sub(r"[^A-Z0-9_-]", "", stem.upper())[:8] or "REPORT"
    return f"{clean}{ext.upper()}"


def named(folder: Path, name: str) -> Path | None:
    """The file in `folder` called `name`, whatever its case: the server's copy of a
    DOS drive may show the name in either, and DOS cannot tell them apart."""
    exact = folder / name
    if exact.is_file():
        return exact
    want = name.upper()
    for p in folder.iterdir():
        if p.name.upper() == want and p.is_file():
            return p
    return None


def roms_named(report: Path, found: list[dict[str, str]]) -> list[Path]:
    """The ROMs a report names, `ROM<n>=segment size filename`, from the report's own
    folder and no other: the name is reduced to its last part, so a report cannot
    send a file from anywhere else on the server."""
    out: list[Path] = []
    for keys in found:
        for key, value in keys.items():
            words = value.split()
            if not ROM_KEY.match(key) or len(words) < 3:
                continue
            name = words[-1].replace("\\", "/").rsplit("/", 1)[-1]
            rom = named(report.parent, name) if name else None
            if rom is None or rom == report or rom in out:
                continue
            if rom.stat().st_size <= MOST_ROM:
                out.append(rom)
    return out


def free(folder: Path, name: str) -> Path:
    """Where `name` can go in `folder` without writing over anything: the name
    itself, or the DOS way of keeping two (`RH0001~1.TXT`), which still fits."""
    folder.mkdir(exist_ok=True)
    taken = {p.name.upper() for p in folder.iterdir()}
    if name.upper() not in taken:
        return folder / name
    stem, dot, ext = name.partition(".")
    for n in range(1, 100000):
        mark = f"~{n}"
        candidate = f"{stem[: 8 - len(mark)]}{mark}{dot}{ext}"
        if candidate.upper() not in taken:
            return folder / candidate
    raise OSError(f"no free name for {name} in {folder}")


def write_dos(path: Path, text: str) -> None:
    """Text as a DOS machine shows it: code page 437, lines ending CR LF, none longer
    than the screen."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n")
    shown = "\r\n".join(line[:79] for line in lines) + "\r\n"
    tmp = path.with_name(path.stem[:8] + MAKING)
    tmp.write_bytes(shown.encode("cp437", "replace"))
    os.replace(tmp, path)


def when_taken(mtime: float, first_seen: float) -> str:
    """When the report was written, by a clock the register can trust: the file's
    date as the server wrote it, unless that is a date no survey could carry."""
    now = time.time()
    when = mtime if EARLIEST <= mtime <= now + 60 else first_seen
    return datetime.fromtimestamp(when, timezone.utc).isoformat(timespec="seconds")


# --- the folder ------------------------------------------------------------------------


class Watch:
    """The folder, and what this agent has seen happen in it.

    Whether a file has been left alone is judged by the agent's own eyes where it
    can be. A file's date is the clock of whatever wrote it, and a DOS machine's
    clock is often years out: a report dated 1980 is not one finished in 1980. So
    only the first look at the folder goes by the files' dates, since there is
    nothing else to go on; after that a file is new when it is first seen, and
    changed when its size or date is.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.first = True
        self.since: dict[Path, tuple[tuple[int, int], float]] = {}
        self.answered: dict[Path, tuple[int, int]] = {}
        self.not_reports: dict[Path, tuple[int, int]] = {}

    def files(self) -> list[Path]:
        out: list[Path] = []
        for here, dirs, names in os.walk(self.root):
            # What has gone, has gone: SENT and REFUSED are never looked in.
            dirs[:] = sorted(d for d in dirs if d.upper() not in (SENT, REFUSED))
            out += [Path(here) / n for n in sorted(names)]
        return out

    def quiet(self, path: Path, st: os.stat_result) -> tuple[float, float]:
        """(how long it has been left alone, when this agent first saw it as it is)."""
        signature = (st.st_size, st.st_mtime_ns)
        now = time.time()
        held = self.since.get(path)
        if held is None or held[0] != signature:
            held = (signature, min(st.st_mtime, now) if self.first else now)
            self.since[path] = held
        return now - held[1], held[1]

    def done_looking(self, present: list[Path]) -> None:
        self.first = False
        keep = set(present)
        for memo in (self.since, self.answered, self.not_reports):
            for gone in [p for p in memo if p not in keep]:
                del memo[gone]


def answer_questions(server: Server, watch: Watch, files: list[Path]) -> int:
    """Every question waiting, answered beside it. Returns how many."""
    done = 0
    for path in files:
        if path.suffix.upper() != QUESTION:
            continue
        try:
            st = path.stat()
            quiet, _ = watch.quiet(path, st)
            reply = path.with_name(dos_name(path.stem, ANSWER))
            signature = (st.st_size, st.st_mtime_ns)
            if quiet < SETTLE_QUESTION:
                continue
            if watch.answered.get(path) == signature and reply.exists():
                continue
            answer = server.ask(path.read_bytes()[:65536])
        except FileNotFoundError:
            continue
        write_dos(reply, answer)
        watch.answered[path] = signature
        tag = re.search(r"^TAG=(\S+)", answer, re.M)
        log.info("%s: %s", path.relative_to(watch.root), tag.group(1) if tag else "not known yet")
        done += 1
    return done


def send_reports(server: Server, watch: Watch, files: list[Path]) -> int:
    """Every finished report, sent, and its receipt written. Returns how many."""
    done = 0
    for path in files:
        if path.suffix.upper() in OURS:
            continue
        try:
            st = path.stat()
            quiet, first_seen = watch.quiet(path, st)
            signature = (st.st_size, st.st_mtime_ns)
            if quiet < SETTLE_REPORT or watch.not_reports.get(path) == signature:
                continue
            if st.st_size > MOST_REPORT:
                watch.not_reports[path] = signature
                continue
            raw = path.read_bytes()
        except FileNotFoundError:
            continue
        found = sections(decode(raw))
        if found is None:
            watch.not_reports[path] = signature
            continue
        if soaking(found) and quiet < SETTLE_SOAK:
            continue
        roms = roms_named(path, found)
        ok, answer = server.send(path, raw, roms, when_taken(st.st_mtime, first_seen))
        name = path.relative_to(watch.root)
        if ok:
            # Moved before the receipt is written: a report that has reached the
            # register must not be in the folder to be sent a second time, and a
            # receipt that failed to be written is the smaller loss.
            for f in [path, *roms]:
                f.rename(free(path.parent / SENT, f.name))
            receipt = str(answer.get("receipt") or "Sent.")
            write_dos(path.with_name(dos_name(path.stem, RECEIPT)), receipt)
            made = answer.get("surveys")
            log.info("%s: sent, %s", name, _said(made if isinstance(made, list) else []))
        else:
            reason = str(answer.get("reason") or "The register refused it.")
            into = path.parent / REFUSED
            for f in [path, *roms]:
                f.rename(free(into, f.name))
            write_dos(into / dos_name(path.stem, REASON), reason)
            # The machine waits for a receipt, so it is told as well: a person at it
            # is not left watching a screen that will never change.
            write_dos(
                path.with_name(dos_name(path.stem, RECEIPT)),
                f"Not taken: {reason}\nThe report is in {REFUSED}, with the reason beside it.",
            )
            log.warning("%s: refused, %s", name, reason)
        done += 1
    return done


def _said(made: list[object]) -> str:
    words = []
    for s in made:
        if isinstance(s, dict):
            where = s.get("machine") or "no machine yet"
            wait = f", waiting for {s['waiting']}" if s.get("waiting") else ""
            words.append(f"survey {s.get('id')} ({where}{wait})")
    return "; ".join(words) or "nothing filed"


def one_pass(server: Server, watch: Watch) -> int:
    """The questions first, since somebody may be standing at the machine, then the
    reports. Returns how many files were dealt with."""
    if not watch.root.is_dir():
        raise Undelivered(f"cannot read the folder {watch.root}")
    files = watch.files()
    done = answer_questions(server, watch, files)
    done += send_reports(server, watch, files)
    watch.done_looking(files)
    return done


def check(server: Server, args: argparse.Namespace) -> int:
    """Say what this agent has been told and what the register makes of it, as the
    print agent's --check does: enough of the key to compare against the server
    without the whole of it in a terminal, then a question with nothing in it --
    which writes nothing, so it is safe to ask."""
    key = args.key or ""
    ends = f"{key[:6]}…{key[-6:]}" if len(key) > 12 else "(too short to be one)"
    folder = Path(args.dir)
    log.info("register : %s", server.base)
    log.info("agent    : %s", args.name or "(not named -- only affects this log)")
    log.info("key      : %s  (%d characters)", ends, len(key))
    if not folder.is_dir():
        log.info("folder   : %s  (not there)", folder)
    else:
        writable = os.access(folder, os.W_OK)
        log.info("folder   : %s%s", folder, "" if writable else "  (this agent cannot write in it)")
    if key != key.strip():
        log.error("the key has whitespace around it, which is almost certainly the fault")
    try:
        server.ask(b"")
    except SystemExit:
        log.error("the register does not know that key. Compare the six characters at")
        log.error("each end against RHDB_SURVEY_AGENTS in the register's .env, and check")
        log.error("`systemctl show survey-agent -p Environment` -- an edited unit file is")
        log.error("not read until `systemctl daemon-reload`, so a fixed key can sit unused.")
        return EX_CONFIG
    except Undelivered as exc:
        log.error("could not ask: %s", exc)
        return 1
    log.info("the key works.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--api", default=os.getenv("RHDB_API", ""), help="the register's base URL")
    ap.add_argument("--key", default=os.getenv("RHDB_SURVEY_KEY", ""), help="this agent's key")
    ap.add_argument(
        "--dir", default=os.getenv("RHDB_SURVEY_DIR", ""), help="the folder the machines write into"
    )
    # The register knows which agent a key belongs to; the name is for the journal,
    # on a server that may run more than one of these.
    ap.add_argument(
        "--name", default=os.getenv("RHDB_SURVEY_AGENT", ""), help="this agent's name, for the log"
    )
    ap.add_argument("--once", action="store_true", help="one pass over the folder, then stop")
    ap.add_argument(
        "--check", action="store_true", help="say what this is set up with, and try the key"
    )
    ap.add_argument("--poll", type=float, default=POLL_SECONDS, help="seconds between looks")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    if not args.api or not args.key or not args.dir:
        log.error(
            "RHDB_API, RHDB_SURVEY_KEY and RHDB_SURVEY_DIR (or --api, --key, --dir) are all needed"
        )
        log.error("  RHDB_API is %s", args.api or "not set")
        log.error("  RHDB_SURVEY_KEY is %s", "set" if args.key else "not set")
        log.error("  RHDB_SURVEY_DIR is %s", args.dir or "not set")
        return EX_CONFIG

    server = Server(args.api, args.key)
    who = args.name or "survey agent"
    if args.check:
        return check(server, args)
    watch = Watch(Path(args.dir))
    if args.once:
        try:
            took = one_pass(server, watch)
        except Undelivered as exc:
            # Not an error: what was not sent is still in the folder, and the next
            # pass sends it.
            log.warning("%s: %s; nothing lost, it is tried again next time", who, exc)
            return 0
        log.info("%s: %d file%s", who, took, "" if took == 1 else "s")
        return 0

    log.info("%s: watching %s for %s every %gs", who, watch.root, server.base, args.poll)
    wait = BACKOFF_START
    while True:
        try:
            one_pass(server, watch)
            wait = BACKOFF_START
            time.sleep(args.poll)
        except KeyboardInterrupt:
            log.info("stopped")
            return 0
        except Undelivered as exc:
            # The register being out of reach is ordinary on a home network: back
            # off and keep looking, and say so once a time rather than every pass.
            log.warning("%s; trying again in %gs", exc, wait)
            time.sleep(wait)
            wait = min(wait * 2, BACKOFF_MAX)


if __name__ == "__main__":
    raise SystemExit(main())
