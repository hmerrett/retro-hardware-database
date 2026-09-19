# 0025 — A print agent asks, and is never called

**Status:** Accepted
**Date:** 2026-09-19

## Context

ADR-0024 made a label that a thermal printer can take. It deliberately said
nothing about how the label reaches a printer, which is this.

The printer is not where the register is. The register is a server — this
installation's is a cloud box with a public address — and the label printers are
on a desk at home, behind a broadband router, on a Raspberry Pi or a laptop that
is switched off half the time. There is no route from the one to the other.

That single fact decides most of the design, and it is easy to get wrong: the
obvious shape is the register POSTing a label to the printer's machine, which
works beautifully in a test where both are on one LAN and cannot work at all in
the installation this is for. Making it work would mean a port forwarded to a Pi,
or a tunnel, or a VPN — a piece of network plumbing to maintain for the sake of
printing a sticker.

There is a second question underneath it. Whatever runs on that Pi has to
authenticate, and the credentials the register has are the owner's: one username
and password that open the whole register, the whole JSON API and every write in
it. A box in a workshop that anybody in the house can unplug and walk off with is
not where that belongs.

## Decision

**The agent opens every connection. The register never initiates one.** The agent
asks whether there is a job for it, fetches the label, prints it and reports the
result. Three requests, all outbound from the printer's side.

This costs nothing in latency that matters — a few seconds between pressing print
and the label appearing — and it buys: no inbound access to the home network, no
port forwarding, no tunnel, nothing to configure on a router, and an agent that is
switched off being an ordinary state rather than a failure. Its jobs wait.

**An agent holds a key of its own, and that key opens nothing else.** Agents are
named in the environment with a key each (`RHDB_PRINT_AGENTS`), as every other
secret in this app is (security-standards). Everything a key can reach is under
one path prefix, `/api/print/agent/`, and there are exactly three things there:
claim a job for *this* agent, fetch the label for a job *this* agent holds, and
report on it. A key cannot read the register, cannot write to it, and cannot see
another agent's queue.

That prefix is let through the login gate, and the route asks for the key — the
same shape ADR-0009 uses for files, where the door is open and the row decides.
A wrong key is rate-limited exactly as a wrong password at the API's door is.

**With no agents named there is no queue.** Not an empty one: the endpoints answer
as though the feature does not exist, because until somebody has written a key
down it does not. A default agent, or a queue anyone can post to, would be a way
into the register that arrived without being asked for.

**A claimed job that is not finished goes back on the queue.** The agent takes a
lease, not the job. If its Pi reboots mid-print the job returns after a few
minutes rather than sitting claimed by a machine that is not coming back. The cost
of being wrong in this direction is a label printed twice, which is a label; the
cost of the other direction is a job lost in silence, which is somebody standing
at a printer wondering.

**The label is rendered when it is fetched, not when it is queued.** A job is a
request to print an item, not a copy of one — so a label printed two minutes after
a correction carries the correction, and the queue does not become a second place
the register's data lives.

## Consequences

- One table, `print_job`, holding what to print, for whom, and how it went. Swept
  a week after it finishes: the queue is what is about to happen, not an archive.
  A label being printed is not an event in the life of a machine, so it does not
  go in the item's history either.
- `tools/print_agent.py` is the other half, and it is deliberately dull: about a
  hundred lines, **standard library only**, shelling out to `lp`. A Raspberry Pi
  with CUPS and a Dymo needs nothing installed to run it, which is the difference
  between a thing that gets deployed and a thing that gets meant to be.
- The agent decides nothing. What stock is loaded and what format suits the
  printer are the register's answer, given per agent in `RHDB_PRINT_AGENTS`, so a
  printer's settings are in one place rather than split across two machines.
- Because the transport is a queue and not a connection, a second destination
  costs nothing here: a Bluetooth printer in a browser is a different way of
  getting the same bitmap, and the device setting that chooses between them is
  ADR-0023's to answer, not this one's.
- Polling is a request every few seconds per agent, forever. That is the price of
  needing no inbound access and it is a small one, but it is a real one, and if a
  future agent is on the same machine as the register it should be given something
  better rather than being made to poll a socket it could share.
