#!/usr/bin/env python3
"""The half of the print queue that runs where the label printer is.

It asks the register whether there is a job for it, fetches the label, sends it to
CUPS and says how it went. Nothing ever calls in: the register is a server and this
is on a desk behind a broadband router, so every connection is opened from here
(ADR-0025).

Standard library only, and no shared code with the rest of `tools/` -- a Raspberry
Pi with CUPS and a Dymo on a USB port should need nothing installed to run this,
because a thing that needs a virtualenv built for it on a machine you only visit
when something is wrong is a thing that does not get deployed.

    export RHDB_API=https://db.example.com
    export RHDB_PRINT_AGENT=workshop-pi
    export RHDB_PRINT_KEY=...            # this agent's key, from the server's .env
    export RHDB_PRINTER=DYMO_LabelWriter_450_Turbo
    python3 print_agent.py

    python3 print_agent.py --once      # one pass, then stop -- run this first
    python3 print_agent.py --dry-run   # write the label to a file, print nothing
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("print-agent")

# How long to wait between asking. Short enough that pressing print and walking to
# the printer is the same gesture it would be if the printer were attached here.
POLL_SECONDS = 5.0

# What to wait after a failure to reach the register, so a server that is down or a
# network that is out is not hammered by every agent on it. Doubles up to the cap.
BACKOFF_START, BACKOFF_MAX = 5.0, 120.0

# Nothing here is worth waiting on for longer than this.
TIMEOUT = 30


class Server:
    """The register, as this agent talks to it: four requests and a bearer key."""

    def __init__(self, base: str, key: str) -> None:
        self.base = base.rstrip("/")
        self.key = key

    def _open(self, method: str, path: str, body: object = None) -> tuple[int, bytes]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.key)
        req.add_header("User-Agent", "rhdb-print-agent/1")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            # An HTTP answer this agent has to act on -- 401 for a wrong key, 410
            # for an item that has gone -- rather than a failure to be retried.
            return e.code, e.read()

    def claim(self) -> dict[str, object] | None:
        status, body = self._open("POST", "/api/print/agent/claim")
        if status == 204:
            return None
        if status == 401:
            raise SystemExit("the register does not recognise this agent's key")
        if status != 200:
            raise RuntimeError(f"claim answered {status}: {body[:200]!r}")
        got = json.loads(body)
        return got if isinstance(got, dict) else None

    def label(self, job_id: int, fmt: str) -> bytes | None:
        """The label's bytes, or None if the item has gone since it was queued."""
        status, body = self._open("GET", f"/api/print/agent/jobs/{job_id}/label.{fmt}")
        if status == 410:
            return None
        if status != 200:
            raise RuntimeError(f"label answered {status}: {body[:200]!r}")
        return body

    def done(self, job_id: int, ok: bool, error: str = "") -> None:
        self._open("POST", f"/api/print/agent/jobs/{job_id}/done", {"ok": ok, "error": error[:255]})


def send_to_cups(path: Path, printer: str, copies: int) -> tuple[bool, str]:
    """Hand the file to `lp`. Returns (printed, what to tell the register).

    The printer's own words go back verbatim, because the person who will read them
    is standing in another room wondering why nothing came out, and "no such
    printer" is the whole of what they need.
    """
    cmd = ["lp"]
    if printer:
        cmd += ["-d", printer]
    if copies > 1:
        cmd += ["-n", str(copies)]
    cmd.append(str(path))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError:
        return False, "no 'lp' command on this machine -- is CUPS installed?"
    except subprocess.TimeoutExpired:
        return False, "lp did not answer"
    if res.returncode == 0:
        return True, (res.stdout or "").strip()
    return False, (res.stderr or res.stdout or f"lp exited {res.returncode}").strip()


def handle(server: Server, job: dict[str, object], printer: str, dry_run: bool) -> None:
    """One job, start to finish. Anything that goes wrong is reported to the
    register rather than raised: the agent's job is to keep printing, and a job it
    cannot do is news for whoever sent it rather than a reason to stop."""
    job_id = int(job["id"])
    fmt = str(job.get("format") or "pdf")
    copies = int(job.get("copies") or 1)
    tag = str(job.get("asset_id") or job_id)
    try:
        body = server.label(job_id, fmt)
    except Exception as exc:
        log.warning("job %s: could not fetch the label: %s", job_id, exc)
        server.done(job_id, False, f"could not fetch the label: {exc}")
        return
    if body is None:
        log.warning("job %s: %s is no longer in the register", job_id, tag)
        return
    out = Path(tempfile.gettempdir()) / f"rhdb-{tag}-{job_id}.{fmt}"
    out.write_bytes(body)
    try:
        if dry_run:
            log.info("job %s: %s written to %s (dry run, nothing printed)", job_id, tag, out)
            server.done(job_id, True, "")
            return
        ok, said = send_to_cups(out, printer, copies)
        log.info(
            "job %s: %s %s%s",
            job_id,
            tag,
            "printed" if ok else "FAILED",
            f" -- {said}" if said else "",
        )
        server.done(job_id, ok, said)
    finally:
        if not dry_run:
            out.unlink(missing_ok=True)


def one_pass(server: Server, printer: str, dry_run: bool) -> int:
    """Everything waiting, printed. Returns how many jobs were taken."""
    done = 0
    while True:
        job = server.claim()
        if job is None:
            return done
        handle(server, job, printer, dry_run)
        done += 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--api", default=os.getenv("RHDB_API", ""), help="the register's base URL")
    ap.add_argument("--key", default=os.getenv("RHDB_PRINT_KEY", ""), help="this agent's key")
    ap.add_argument("--printer", default=os.getenv("RHDB_PRINTER", ""), help="CUPS printer name")
    # The name is the register's own answer -- a key belongs to exactly one agent,
    # so nothing here has to be told which it is. It is taken anyway because it is
    # the only thing that makes a line in the journal say which printer it is about,
    # on a machine that may be running more than one of these.
    ap.add_argument(
        "--name", default=os.getenv("RHDB_PRINT_AGENT", ""), help="this agent's name, for the log"
    )
    ap.add_argument("--once", action="store_true", help="print what is waiting, then stop")
    ap.add_argument("--dry-run", action="store_true", help="write the label to a file instead")
    ap.add_argument("--poll", type=float, default=POLL_SECONDS, help="seconds between asking")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    if not args.api or not args.key:
        ap.error("RHDB_API and RHDB_PRINT_KEY (or --api and --key) are both needed")

    server = Server(args.api, args.key)
    who = args.name or "print agent"
    if args.once:
        took = one_pass(server, args.printer, args.dry_run)
        log.info("%s: %d job%s", who, took, "" if took == 1 else "s")
        return 0

    log.info(
        "%s: asking %s every %gs%s",
        who,
        server.base,
        args.poll,
        " (dry run)" if args.dry_run else "",
    )
    wait = BACKOFF_START
    while True:
        try:
            one_pass(server, args.printer, args.dry_run)
            wait = BACKOFF_START
            time.sleep(args.poll)
        except KeyboardInterrupt:
            log.info("stopped")
            return 0
        except SystemExit:
            raise
        except Exception as exc:
            # The register being unreachable is an ordinary thing on a home network
            # and not a reason to stop: back off, keep asking, and say so once a
            # time rather than filling the journal with it.
            log.warning("cannot reach the register (%s); trying again in %gs", exc, wait)
            time.sleep(wait)
            wait = min(wait * 2, BACKOFF_MAX)


if __name__ == "__main__":
    raise SystemExit(main())
