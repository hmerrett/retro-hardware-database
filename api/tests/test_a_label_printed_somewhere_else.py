"""A label printed on a printer that is not attached to the machine you are holding.

The register is a server and the label printer is on a desk behind a broadband
router, so there is no route from the one to the other. The agent therefore opens
every connection: it asks whether there is a job for it, fetches the label, prints
it and says how it went (ADR-0025).

Its key opens that and nothing else.
"""

import pytest

from app import labels, printing

AGENTS = "workshop-pi:key-one:dymo-11355:pdf,bench:key-two:niimbot-50x30:png"


@pytest.fixture
def agents(monkeypatch):
    """Two agents, as the environment names them."""
    monkeypatch.setenv("RHDB_PRINT_AGENTS", AGENTS)
    return printing.agents()


@pytest.fixture
def queued(client, part, agents):
    """One job waiting for the workshop Pi, and the part it is for."""

    def make(agent="workshop-pi", **body):
        card = part(manufacturer="Seagate", model="ST-225", type="storage")
        r = client.post(
            "/api/print/jobs",
            json={"agent": agent, "kind": "part", "asset_id": card["asset_id"]} | body,
        )
        assert r.status_code == 200, r.text
        return r.json(), card

    return make


def claim(client, key="key-one"):
    return client.post("/api/print/agent/claim", headers={"Authorization": f"Bearer {key}"})


def finish(client, job_id, key="key-one", **body):
    return client.post(
        f"/api/print/agent/jobs/{job_id}/done",
        json={"ok": True} | body,
        headers={"Authorization": f"Bearer {key}"},
    )


# --- there is no queue until somebody has named an agent ---------------------


def test_with_no_agent_named_there_is_no_queue(client, part, monkeypatch):
    """Not an empty queue: the feature does not exist until a key has been written
    down. A default agent, or a queue anybody may post to, would be a way into the
    register that arrived without being asked for."""
    monkeypatch.delenv("RHDB_PRINT_AGENTS", raising=False)
    aid = part()["asset_id"]
    r = client.post(
        "/api/print/jobs", json={"agent": "workshop-pi", "kind": "part", "asset_id": aid}
    )
    assert r.status_code == 404, r.text
    assert claim(client).status_code == 401


def test_an_agent_the_register_does_not_know_is_refused(client, part, agents):
    aid = part()["asset_id"]
    r = client.post("/api/print/jobs", json={"agent": "nonesuch", "kind": "part", "asset_id": aid})
    assert r.status_code == 404, r.text


def test_an_item_that_is_not_there_is_refused_at_the_door(client, agents):
    """Rather than queued and discovered to be missing by a Pi in another room."""
    r = client.post(
        "/api/print/jobs", json={"agent": "workshop-pi", "kind": "part", "asset_id": "RH-NOPE"}
    )
    assert r.status_code == 404, r.text


# --- what a key opens --------------------------------------------------------


def test_a_wrong_key_opens_nothing(client, agents):
    assert claim(client, "not-a-key").status_code == 401


def test_an_agents_key_does_not_open_the_rest_of_the_api(client, part, agents, monkeypatch):
    """The whole point of a key per agent. A box in a workshop that anybody can
    unplug and walk off with does not hold the owner's password.

    With the login on, which is the only state in which the claim means anything --
    the suite otherwise runs open (ADR-0019) and everything would answer."""
    from app import main

    card = part()
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
    head = {"Authorization": "Bearer key-one"}
    assert client.get("/api/parts", headers=head).status_code == 401
    assert client.get(f"/api/parts/{card['asset_id']}", headers=head).status_code == 401
    assert client.post("/api/parts", json={"model": "X"}, headers=head).status_code == 401
    assert client.get("/api/print/jobs", headers=head).status_code == 401


def test_an_agent_claims_its_own_jobs_and_not_another_agents(client, queued, agents):
    job, _ = queued(agent="workshop-pi")
    assert claim(client, "key-two").status_code == 204
    mine = claim(client, "key-one")
    assert mine.status_code == 200, mine.text
    assert mine.json()["id"] == job["id"]


def test_a_job_another_agent_holds_is_not_readable_or_reportable(client, queued, agents):
    job, _ = queued()
    assert claim(client).status_code == 200
    head = {"Authorization": "Bearer key-two"}
    assert (
        client.get(f"/api/print/agent/jobs/{job['id']}/label.pdf", headers=head).status_code == 404
    )
    assert finish(client, job["id"], key="key-two").status_code == 404


# --- claiming ----------------------------------------------------------------


def test_a_job_is_claimed_once(client, queued, agents):
    """Two agents under one name, or one agent asking twice before it has finished,
    must not both print it."""
    queued()
    assert claim(client).status_code == 200
    assert claim(client).status_code == 204


def test_nothing_waiting_is_not_an_error(client, agents):
    """An agent asks every few seconds forever; an empty queue is its ordinary
    answer and must not read as a fault in the log."""
    assert claim(client).status_code == 204


def test_the_oldest_job_goes_first(client, queued, agents):
    first, _ = queued()
    second, _ = queued()
    assert claim(client).json()["id"] == first["id"]
    assert claim(client).json()["id"] == second["id"]


def test_a_claim_says_what_to_print_and_how(client, queued, agents):
    """Everything the agent needs in one answer, so it never has to ask the
    register a second question to know what it is doing."""
    _, card = queued()
    got = claim(client).json()
    assert got["asset_id"] == card["asset_id"]
    assert got["kind"] == "part"
    assert got["media"] == "dymo-11355"
    assert got["format"] == "pdf"
    assert got["copies"] == 1


# --- what the job says -------------------------------------------------------


def test_the_agents_own_settings_are_the_default(client, queued, agents):
    """What stock is loaded and what the printer would rather be handed are facts
    about the printer, so they are answered once on the server rather than
    configured again on the machine in the workshop."""
    queued(agent="bench")
    got = claim(client, "key-two").json()
    assert got["media"] == "niimbot-50x30"
    assert got["format"] == "png"


def test_a_job_may_say_otherwise(client, queued, agents):
    queued(media="niimbot-40x30", format="png", copies=3)
    got = claim(client).json()
    assert (got["media"], got["format"], got["copies"]) == ("niimbot-40x30", "png", 3)


def test_a_stock_the_register_does_not_know_is_refused(client, part, agents):
    aid = part()["asset_id"]
    r = client.post(
        "/api/print/jobs",
        json={"agent": "workshop-pi", "kind": "part", "asset_id": aid, "media": "nonesuch"},
    )
    assert r.status_code == 422, r.text


# --- the label ---------------------------------------------------------------


def test_the_label_is_rendered_when_it_is_fetched(client, queued, agents, db):
    """A job is a request to print an item, not a copy of one -- so a label printed
    two minutes after a correction carries the correction, and the queue does not
    become a second place the register's data lives."""
    from app.common import to_dict
    from app.models import Part

    job, card = queued(format="png")
    aid = card["asset_id"]
    assert claim(client).status_code == 200
    r = client.patch(f"/api/parts/{aid}", json={"model": "ST-251"})
    assert r.status_code == 200, r.text
    got = client.get(
        f"/api/print/agent/jobs/{job['id']}/label.png", headers={"Authorization": "Bearer key-one"}
    )
    assert got.status_code == 200, got.text
    fresh = labels.render_png(
        to_dict(db.get(Part, aid)), [], labels.PART, labels.MEDIA["dymo-11355"]
    )
    assert got.content == fresh


def test_the_label_can_be_fetched_as_either_a_page_or_dots(client, queued, agents):
    """The job says which the printer would rather have and the claim passes that
    on, but the URL is what decides: an agent proving a connection wants to ask for
    the other one without a second job being made for it."""
    job, _ = queued()
    assert claim(client).status_code == 200
    head = {"Authorization": "Bearer key-one"}
    pdf = client.get(f"/api/print/agent/jobs/{job['id']}/label.pdf", headers=head)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    png = client.get(f"/api/print/agent/jobs/{job['id']}/label.png", headers=head)
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")


def test_an_item_deleted_before_it_prints_fails_the_job_rather_than_the_agent(
    client, queued, agents
):
    """The agent must be told that this one is never going to work, not handed a
    traceback to decide about."""
    job, card = queued()
    assert claim(client).status_code == 200
    assert client.delete(f"/api/parts/{card['asset_id']}").status_code == 200
    got = client.get(
        f"/api/print/agent/jobs/{job['id']}/label.pdf", headers={"Authorization": "Bearer key-one"}
    )
    assert got.status_code == 410, got.text
    # And the job is closed rather than left claimed for the lease to hand back to
    # an agent that would fail on it again.
    listed = client.get("/api/print/jobs").json()
    assert listed[0]["state"] == "failed"
    assert "no longer in the register" in listed[0]["error"]


# --- reporting ---------------------------------------------------------------


def test_an_agent_says_how_it_went(client, queued, agents):
    job, _ = queued()
    assert claim(client).status_code == 200
    assert finish(client, job["id"]).status_code == 200
    listed = client.get("/api/print/jobs").json()
    assert [j["state"] for j in listed] == ["done"]


def test_a_failure_keeps_what_went_wrong(client, queued, agents):
    """So the answer to "why has nothing come out" is on the screen in the room the
    label was sent from, rather than in a log on the Pi."""
    job, _ = queued()
    assert claim(client).status_code == 200
    assert finish(client, job["id"], ok=False, error="no such printer").status_code == 200
    listed = client.get("/api/print/jobs").json()
    assert listed[0]["state"] == "failed"
    assert listed[0]["error"] == "no such printer"


def test_a_job_can_be_taken_off_the_queue_before_it_is_claimed(client, queued, agents):
    job, _ = queued()
    assert client.delete(f"/api/print/jobs/{job['id']}").status_code == 200
    assert claim(client).status_code == 204


# --- the lease ---------------------------------------------------------------


def test_a_claimed_job_that_is_never_finished_comes_back(client, queued, agents, db):
    """An agent takes a lease, not the job. If its Pi reboots mid-print the job
    returns rather than sitting claimed by a machine that is not coming back -- the
    cost of being wrong this way is a label printed twice, and of being wrong the
    other way a job lost in silence."""
    from datetime import timedelta

    from app.models import PrintJob

    job, _ = queued()
    assert claim(client).status_code == 200
    assert claim(client).status_code == 204
    row = db.get(PrintJob, job["id"])
    row.claimed_at = row.claimed_at - timedelta(seconds=printing.LEASE_SECONDS + 1)
    db.commit()
    assert claim(client).status_code == 200


def test_a_finished_job_does_not_come_back(client, queued, agents, db):
    from datetime import timedelta

    from app.models import PrintJob

    job, _ = queued()
    assert claim(client).status_code == 200
    assert finish(client, job["id"]).status_code == 200
    row = db.get(PrintJob, job["id"])
    row.claimed_at = row.claimed_at - timedelta(seconds=printing.LEASE_SECONDS + 1)
    db.commit()
    assert claim(client).status_code == 204


def test_what_has_finished_is_swept_after_a_week(client, queued, agents, db):
    """The queue is a list of what is about to happen, not an archive. A label
    being printed is not an event in the life of a machine, so the item's history
    is not where it belongs either."""
    from datetime import timedelta

    from app.models import PrintJob

    job, _ = queued()
    assert claim(client).status_code == 200
    assert finish(client, job["id"]).status_code == 200
    row = db.get(PrintJob, job["id"])
    row.finished_at = row.finished_at - timedelta(days=printing.KEEP_DAYS + 1)
    db.commit()
    queued()
    assert db.get(PrintJob, job["id"]) is None


def test_what_is_still_waiting_is_never_swept(client, queued, agents, db):
    """An agent switched off for a fortnight is an ordinary state, not a reason to
    throw its work away."""
    from datetime import timedelta

    from app.models import PrintJob

    job, _ = queued()
    row = db.get(PrintJob, job["id"])
    row.created_at = row.created_at - timedelta(days=printing.KEEP_DAYS + 30)
    db.commit()
    queued()
    assert db.get(PrintJob, job["id"]) is not None


# --- the door itself ---------------------------------------------------------


def every_route(app):
    """Every route the app serves, walked rather than read off `app.routes`.

    An included router is a wrapper here rather than a list of routes flattened
    into the app, and it keeps the router it wrapped under `original_router`. So
    the top level of `app.routes` holds none of the application's own paths, which
    reads -- to a test that looks only there -- as an app with no routes at all
    rather than as a test looking in the wrong place."""
    found, stack = [], list(app.routes)
    while stack:
        route = stack.pop()
        inner = getattr(route, "original_router", None)
        stack.extend(getattr(inner, "routes", None) or getattr(route, "routes", None) or [])
        if getattr(route, "path", None) and hasattr(route, "dependant"):
            found.append(route)
    return found


def test_every_route_behind_the_agent_prefix_asks_for_a_key():
    """The gate lets this prefix through without a login, because which agent is
    asking is the route's answer and not the gate's (ADR-0025). That makes the
    dependency the only thing standing there -- so a route added under the prefix
    and given no key check would be public, and nothing about the URL would say so.
    """
    from app import auth, main
    from app.routers.print_queue import agent_from_key

    behind = [r for r in every_route(main.app) if r.path.startswith(auth.AGENT_PREFIX.rstrip("/"))]
    assert behind, "no routes under the agent prefix -- has it moved?"
    for route in behind:
        takes = [d.call for d in getattr(route, "dependant", None).dependencies]
        assert agent_from_key in takes, f"{route.path} does not ask for an agent's key"


def test_the_prefix_the_gate_opens_is_the_one_the_routes_are_under():
    """Two strings written in two modules that have to agree, and nothing else
    would notice if they stopped: the gate would send an agent to the login page,
    or -- the way that matters -- open a door the routes are not behind."""
    from app import auth, main

    assert auth.AGENT_PREFIX == "/api/print/agent/"
    assert any(r.path.startswith(auth.AGENT_PREFIX) for r in every_route(main.app))


def test_an_agent_named_with_no_key_is_not_an_agent(monkeypatch):
    """An empty key must never match anything. `name::stock:format` is a plausible
    typo in a variable that is edited by hand, and read carelessly it is an agent
    whose key is the empty string -- which every request that sends no key has."""
    monkeypatch.setenv("RHDB_PRINT_AGENTS", "ghost::dymo-11355:pdf,real:key-one:dymo-11355:pdf")
    assert "ghost" not in printing.agents()
    assert printing.agent_for("") is None


def test_an_entry_naming_a_stock_that_does_not_exist_is_dropped(monkeypatch):
    """Rather than printing the wrong size on a printer somebody is not watching."""
    monkeypatch.setenv("RHDB_PRINT_AGENTS", "bad:key-x:no-such-stock:pdf,good:key-y::pdf")
    named = printing.agents()
    assert "bad" not in named
    assert named["good"].media == labels.SMALL


def test_a_key_is_not_a_password_and_a_password_is_not_a_key(client, agents, monkeypatch):
    """The two doors do not open each other: the owner's credentials are not an
    agent's key, and an agent's key is not the owner's credentials."""
    from app import main

    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(main.auth, "AUTH_USER", "henry")
    monkeypatch.setattr(main.auth, "AUTH_PASS", "hunter2")
    assert claim(client, "hunter2").status_code == 401
    assert client.get("/api/print/jobs", auth=("henry", "hunter2")).status_code == 200
    assert client.get("/api/print/jobs", auth=("henry", "key-one")).status_code == 401
