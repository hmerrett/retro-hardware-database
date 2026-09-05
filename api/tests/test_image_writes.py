"""A photograph while it is changing: two writers, and one URL.

Every image here is written while something else may be writing the same one. A
crop and a page reload are the ordinary case: the moment a photograph changes,
every copy made from it -- the watermarked one, and one per width in the srcset --
is stale, and the reloaded page asks for several of them at once. Each of those
requests rebuilds the *same* watermarked file.

They were all writing to one temporary path, `<name>.part`, so the second writer
truncated the first's file underneath it. Worse: once the first renamed that
temporary into place, the second went on writing into the file now being served,
so a reader in that window was handed a fragment -- which is a photograph that is
half grey. A refresh a moment later found the caches settled and looked fine,
which is exactly what made it look like a browser problem.

The rule is one temporary file per writer. os.replace then means last-writer-wins
with whole files, and nobody ever writes into the file being served.

The second half of this file is the other reason a photograph could look wrong
after an edit and right after a refresh, and it is not a race at all: the ?v= stamp
that lets a photograph be cached for a year was the mtime in whole seconds, so two
edits inside one second produced the same URL for two different pictures.
"""
import os
import threading

from app import main, thumbs


def racing_writers(call, dst, n=2):
    """Run `call(dst, write)` in n threads, each held inside its write until all of
    them are in there together, and report what happened.

    The barrier is what makes this a test rather than a coin toss: without it the
    writers would have to be caught overlapping by luck."""
    barrier = threading.Barrier(n)
    temps, errors = [], []

    def run(marker):
        def write(tmp):
            temps.append(str(tmp))
            with open(tmp, "wb") as f:
                f.write(marker * 200_000)
                f.flush()
                barrier.wait()
                f.write(marker * 200_000)
        try:
            call(dst, write)
        except Exception as exc:  # reported below rather than swallowed
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(bytes([b],),))
               for b in (b"A"[0], b"B"[0])[:n]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return temps, errors


def test_two_writers_do_not_share_a_temporary_file(tmp_path):
    temps, _ = racing_writers(main._write_atomically, tmp_path / "photo.jpg")
    assert len(set(temps)) == 2, temps


def test_the_photograph_left_behind_is_one_of_them_whole(tmp_path):
    """Not a mixture of the two. A file holding some of each is not a photograph at
    all, and it is what a reader who arrived at the wrong moment was being sent."""
    dst = tmp_path / "photo.jpg"
    racing_writers(main._write_atomically, dst)
    written = set(dst.read_bytes())
    assert len(written) == 1, sorted(written)


def test_neither_writer_is_left_holding_nothing(tmp_path):
    """The loser used to fail on the rename, because the winner had already moved
    the temporary file they were both using."""
    _, errors = racing_writers(main._write_atomically, tmp_path / "photo.jpg")
    assert errors == []


def test_a_temporary_file_is_never_left_behind(tmp_path):
    dst = tmp_path / "photo.jpg"
    racing_writers(main._write_atomically, dst)
    assert [p.name for p in tmp_path.iterdir()] == ["photo.jpg"]


def test_the_sized_copies_follow_the_same_rule(tmp_path):
    """thumbs makes its own copies and had its own `.part`, so it had the same race
    on the same reload -- two widths of one photograph are two destinations, but a
    browser asking for one width twice is one."""
    temps, errors = racing_writers(thumbs._write_atomically, tmp_path / "c.jpg")
    assert len(set(temps)) == 2 and errors == []


def test_a_photograph_asked_for_by_several_requests_at_once_is_whole(client,
                                                                     computer):
    """The whole gesture, through the app: a photograph uploaded, then asked for by
    several requests together the way a reloaded page asks for it. Every one of them
    must be a picture that decodes."""
    import io
    from concurrent.futures import ThreadPoolExecutor

    from PIL import Image
    aid = computer()["asset_id"]
    buf = io.BytesIO()
    # Big enough that encoding a copy takes long enough to overlap.
    Image.effect_noise((1600, 1200), 90).convert("RGB").save(buf, "JPEG")
    buf.seek(0)
    client.post(f"/computers/{aid}/photo",
                files={"photos": ("shot.jpg", buf, "image/jpeg")},
                follow_redirects=False)
    rel = main.detect_images("computers", aid)[0]
    # Every copy made from this photograph is now stale, which is the state a crop
    # leaves it in.
    main._wm_forget(rel)

    def fetch(width):
        return client.get(f"/images/{rel}?v=1&w={width}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        got = list(pool.map(fetch, [400, 800, 1200, 400, 800, 1200]))
    for r in got:
        assert r.status_code == 200
        with Image.open(io.BytesIO(r.content)) as im:
            im.verify()


# --- and the URL that says which version this is ------------------------------


def test_two_edits_in_the_same_second_get_different_urls(tmp_path, monkeypatch):
    """A photograph's URL carries a stamp so it can be kept for a year and still
    never be stale: editing it changes the stamp, so the browser asks again. The
    stamp was whole seconds, and rotating twice takes rather less than one -- so the
    second turn produced the URL the browser already had, marked immutable, and it
    went on showing the first. Which is why the picture came right on a refresh and
    nowhere else.
    """
    monkeypatch.setattr(main, "IMAGES_DIR", tmp_path)
    rel = "computers/RH-0001.jpg"
    photo = tmp_path / rel
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"as taken")
    # Two edits four tenths of a second apart, set exactly rather than raced for:
    # the same whole second, and a different photograph.
    when = 1_600_000_000_000_000_000
    os.utime(photo, ns=(when, when))
    before = main.img_url(rel, 800)
    photo.write_bytes(b"cropped")
    os.utime(photo, ns=(when + 400_000_000, when + 400_000_000))
    assert main.img_url(rel, 800) != before
