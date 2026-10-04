"""Durable browser drafts: one per unsaved document, recovered by explicit choice."""

from __future__ import annotations

import errno
import http.client
import json
import os
import threading
import time
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import pytest

from chemvas.bootstrap import web_adapter, web_drafts
from chemvas.bootstrap.web_adapter import (
    SESSION_IDLE_SECONDS,
    BrowserServer,
    new_document,
)
from chemvas.bootstrap.web_drafts import (
    DRAFT_FORMAT,
    BrowserDraftStore,
    DraftError,
    default_drafts_root,
)
from chemvas.core.document_io import ATOMIC_STAGING_PREFIX, ATOMIC_STAGING_SUFFIX
from chemvas.domain.document import extract_document_state

BOND = {"kind": "bond", "start": [0, 0], "end": [20, 0], "style": "single"}


def bond_at(y: float) -> dict:
    return {**BOND, "start": [0, y], "end": [20, y]}


@contextmanager
def running(root: Path):
    with BrowserServer(drafts=BrowserDraftStore(root)) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)


def post(server: BrowserServer, body: dict) -> tuple[int, dict]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(
            "POST",
            "/api/session",
            body=json.dumps(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + server.token,
            },
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class Window:
    """One browser window: its session, the last accepted reply and requests."""

    def __init__(self, server: BrowserServer, document: dict | None = None) -> None:
        self.server = server
        status, self.info = post(
            server,
            {
                "revision": 0,
                "action": "load",
                "document": document or new_document(),
                "name": "Work.chemvas",
            },
        )
        assert status == 200, self.info

    def request(self, action: str, **fields) -> tuple[int, dict]:
        body = {
            "session": self.info["session"],
            "revision": self.info["revision"],
            "action": action,
            **fields,
        }
        status, reply = post(self.server, body)
        # Only replies with the window's accepted state replace it.
        if status == 200 and "dirty" in reply:
            self.info = reply
        return status, reply

    def send(self, action: str, **fields) -> dict:
        status, reply = self.request(action, **fields)
        assert status == 200, reply
        return reply

    def edit(self, edit: dict) -> dict:
        return self.send("edit", edit=edit)

    def drafts(self) -> list[dict]:
        return self.send("drafts")["drafts"]

    def close(self) -> None:
        status, _ = post(
            self.server, {"session": self.info["session"], "action": "close"}
        )
        assert status == 200


def draft_files(root: Path) -> list[Path]:
    return sorted(root.glob("*.json"))


def state_of(document: dict) -> dict:
    return json.loads(json.dumps(document["state"]))


def test_one_draft_survives_close_and_restarts_and_recovers_without_copies(tmp_path):
    root = tmp_path / "drafts"
    with running(root) as server:
        window = Window(server)
        edited = window.edit(BOND)
        assert edited["recovery"] == {
            "available": True,
            "state": "saved",
            "message": None,
        }
        [path] = draft_files(root)
        text = path.read_text(encoding="utf-8")
        stored = json.loads(text)
        assert stored["format"] == DRAFT_FORMAT
        assert stored["name"] == "Work.chemvas"
        # The complete document in the existing representation, no credential.
        assert state_of(stored["document"]) == state_of(edited["document"])
        extract_document_state(stored["document"])
        assert server.token not in text
        window.close()
        # Closing the window keeps its draft for explicit recovery.
        assert draft_files(root) == [path]
    draft_id = path.stem
    for restart in range(3):
        with running(root) as server:
            window = Window(server)
            # Startup offers the draft; nothing replaced this window's drawing.
            listed = [
                (entry["id"], entry["name"], entry["open"], entry["problem"])
                for entry in window.drafts()
            ]
            assert listed == [(draft_id, "Work.chemvas", False, None)]
            assert state_of(window.info["document"]) == state_of(new_document())
            recovered = window.send("recover_draft", draft=draft_id)
            assert state_of(recovered["document"]) == state_of(edited["document"])
            assert recovered["dirty"] is True
            assert recovered["can_undo"] is False
            assert recovered["name"] == "Work.chemvas"
            # Recovering again elsewhere cannot make a second copy.
            other = Window(server)
            status, refused = other.request("recover_draft", draft=draft_id)
            assert status == 400
            assert "still open in another window" in refused["error"]
            status, refused = window.request("recover_draft", draft=draft_id)
            assert status == 400
            assert "already open in this window" in refused["error"]
            assert draft_files(root) == [path]
            # Odd restarts close the window; even ones stop the server under it.
            if restart % 2:
                window.close()
    assert draft_files(root) == [path]


def test_clean_state_removes_the_draft_and_a_download_does_not(tmp_path):
    root = tmp_path / "drafts"
    with running(root) as server:
        window = Window(server)
        window.edit(BOND)
        assert len(draft_files(root)) == 1
        # Save copy is a download request: no proof of a saved file.
        exported = window.send("export")
        assert exported["document"]
        assert len(draft_files(root)) == 1
        assert window.send("read")["dirty"] is True
        undone = window.send("undo")
        assert undone["dirty"] is False
        assert undone["recovery"]["state"] == "clean"
        assert draft_files(root) == []
        redone = window.send("redo")
        assert redone["recovery"]["state"] == "saved"
        assert len(draft_files(root)) == 1


def test_opened_originals_are_never_written(tmp_path):
    root = tmp_path / "drafts"
    original = tmp_path / "original.chemvas"
    original.write_text(json.dumps(new_document()), encoding="utf-8")
    before = original.read_bytes()
    with running(root) as server:
        window = Window(server, json.loads(before))
        window.edit(BOND)
        window.edit(bond_at(40))
        window.send("undo")
        window.close()
    assert original.read_bytes() == before
    written = {path for path in tmp_path.rglob("*") if path.is_file()}
    assert written == {original, root / web_drafts.LOCK_NAME, *draft_files(root)}


def test_replacing_a_drawing_discards_its_draft_and_stale_requests_change_nothing(
    tmp_path,
):
    root = tmp_path / "drafts"
    with running(root) as server:
        window = Window(server)
        window.edit(BOND)
        [first] = draft_files(root)
        # The browser asked before replacing: the replaced work's draft goes.
        window.send("load", document=new_document(), name="Next.chemvas")
        assert draft_files(root) == []
        stale_revision = window.info["revision"]
        window.edit(bond_at(40))
        [second] = draft_files(root)
        assert second != first
        content = second.read_bytes()
        status, _ = post(
            server,
            {
                "session": window.info["session"],
                "revision": stale_revision,
                "action": "edit",
                "edit": bond_at(80),
            },
        )
        assert status == 409
        assert second.read_bytes() == content
        assert draft_files(root) == [second]


def test_a_failed_write_keeps_the_edit_and_the_previous_draft(tmp_path, monkeypatch):
    root = tmp_path / "drafts"
    with running(root) as server:
        window = Window(server)
        window.edit(BOND)
        [path] = draft_files(root)
        previous = path.read_bytes()

        def full_disk(*_args, **_kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(web_drafts, "atomic_write_text", full_disk)
        failed = window.edit(bond_at(40))
        assert len(state_of(failed["document"])["model"]["atoms"]) == 4
        assert failed["recovery"]["state"] == "failed"
        assert "could not be written" in failed["recovery"]["message"]
        assert path.read_bytes() == previous
        monkeypatch.undo()
        saved = window.edit(bond_at(80))
        assert saved["recovery"]["state"] == "saved"
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert state_of(stored["document"]) == state_of(saved["document"])


def test_the_draft_limit_refuses_new_drafts_visibly(tmp_path, monkeypatch):
    root = tmp_path / "drafts"
    monkeypatch.setattr(web_drafts, "MAX_DRAFTS", 2)
    with running(root) as server:
        first, second, third = Window(server), Window(server), Window(server)
        first.edit(BOND)
        second.edit(BOND)
        kept = {path: path.read_bytes() for path in draft_files(root)}
        refused = third.edit(BOND)
        assert refused["recovery"]["state"] == "failed"
        assert "already holds 2 drafts" in refused["recovery"]["message"]
        assert {path: path.read_bytes() for path in draft_files(root)} == kept
        # A clean window frees its place; the next edit is protected again.
        first.send("undo")
        assert third.edit(bond_at(40))["recovery"]["state"] == "saved"
        assert len(draft_files(root)) == 2


def test_a_second_running_server_works_without_drafts(tmp_path):
    root = tmp_path / "drafts"
    with running(root) as server:
        owner = Window(server)
        owner.edit(BOND)
        with running(root) as second:
            assert second.drafts is not None
            assert not second.drafts.available
            assert "another running Chemvas browser server" in second.drafts.problem
            window = Window(second)
            reply = window.edit(BOND)
            assert reply["recovery"]["state"] == "off"
            assert reply["recovery"]["message"] == second.drafts.problem
            listing = window.send("drafts")
            assert listing["drafts"] == []
            assert listing["available"] is False
            assert listing["message"] == second.drafts.problem
            assert len(draft_files(root)) == 1
    # The owner's lock ended with it: a later server owns the folder.
    later = BrowserDraftStore(root)
    try:
        assert later.available
        assert [entry.name for entry in later.entries()] == ["Work.chemvas"]
    finally:
        later.close()


def test_recovering_an_open_window_needs_takeover_and_closes_it(tmp_path):
    root = tmp_path / "drafts"
    with running(root) as server:
        holder = Window(server)
        edited = holder.edit(BOND)
        [path] = draft_files(root)
        rescuer = Window(server)
        [entry] = rescuer.drafts()
        assert entry["open"] is True
        assert isinstance(entry["idle_seconds"], float)
        status, refused = rescuer.request("recover_draft", draft=path.stem)
        assert status == 400
        assert rescuer.info["document"]["state"]["model"]["atoms"] == {}
        recovered = rescuer.send("recover_draft", draft=path.stem, takeover=True)
        assert state_of(recovered["document"]) == state_of(edited["document"])
        status, ended = holder.request("read")
        assert status == 400
        assert "ended" in ended["error"]
        assert draft_files(root) == [path]
        # The draft is now this window's: later edits update the same file.
        rescuer.edit(bond_at(40))
        assert draft_files(root) == [path]
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert state_of(stored["document"]) == state_of(rescuer.info["document"])


def live_session(server: BrowserServer, window: Window):
    with server.session_lock:
        return server.sessions[window.info["session"]]


def assert_holder_intact(server, holder: Window, path: Path, content: bytes) -> None:
    """The holder still owns its drawing, its draft and its file."""
    session = live_session(server, holder)
    assert not session.closed
    assert server.drafts.owner_of(path.stem) is session
    assert path.read_bytes() == content
    document = holder.info["document"]
    assert holder.send("read")["document"] == document


def test_refused_takeovers_leave_the_holder_open_and_unchanged(tmp_path, monkeypatch):
    root = tmp_path / "drafts"
    with running(root) as server:
        holder = Window(server)
        holder.edit(BOND)
        [path] = draft_files(root)
        content = path.read_bytes()
        rescuer = Window(server)
        before = rescuer.info
        session = rescuer.info["session"]
        # Stale, malformed and new-window requests are refused before any
        # other window is touched.
        for change, expected in [
            ({"revision": before["revision"] - 1}, 409),
            ({"takeover": "yes"}, 400),
            ({"draft": "../outside"}, 400),
            ({"extra": 1}, 400),
            ({"session": None, "revision": 0}, 400),
        ]:
            request = {
                "session": session,
                "revision": before["revision"],
                "action": "recover_draft",
                "draft": path.stem,
                "takeover": True,
                **change,
            }
            body = {key: value for key, value in request.items() if value is not None}
            status, _ = post(server, body)
            assert status == expected, change
            assert_holder_intact(server, holder, path, content)
        assert rescuer.send("read")["revision"] == before["revision"]
        # A draft file that no longer opens as a drawing: refused, claim kept.
        damaged = json.loads(content)
        damaged["document"] = {"type": "chemvas", "version": 9, "state": {}}
        path.write_text(json.dumps(damaged), encoding="utf-8")
        status, refused = rescuer.request(
            "recover_draft", draft=path.stem, takeover=True
        )
        assert status == 400 and "damaged" in refused["error"]
        assert_holder_intact(server, holder, path, path.read_bytes())
        assert rescuer.send("read")["document"] == before["document"]
        # The holder keeps writing its own draft.
        assert holder.edit(bond_at(40))["recovery"]["state"] == "saved"
        content = path.read_bytes()
        assert json.loads(content)["document"]["state"] == state_of(
            holder.info["document"]
        )

        # The holder's newest edit is not in its draft: closing it would lose it.
        def full_disk(*_args, **_kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(web_drafts, "atomic_write_text", full_disk)
        newest = holder.edit(bond_at(80))
        assert newest["recovery"]["state"] == "failed"
        monkeypatch.undo()
        status, refused = rescuer.request(
            "recover_draft", draft=path.stem, takeover=True
        )
        assert status == 400 and "could not keep" in refused["error"]
        assert_holder_intact(server, holder, path, content)
        assert holder.info["document"] == newest["document"]
        assert rescuer.send("read")["document"] == before["document"]


def test_takeover_of_a_busy_window_gives_up_in_bounded_time(tmp_path, monkeypatch):
    root = tmp_path / "drafts"
    monkeypatch.setattr(web_adapter, "DRAFT_TAKEOVER_WAIT_SECONDS", 0.2)
    with running(root) as server:
        holder = Window(server)
        holder.edit(BOND)
        [path] = draft_files(root)
        content = path.read_bytes()
        rescuer = Window(server)
        session = live_session(server, holder)
        with session.lock:
            started = time.monotonic()
            status, refused = rescuer.request(
                "recover_draft", draft=path.stem, takeover=True
            )
            assert time.monotonic() - started < 4
        assert status == 400 and "busy" in refused["error"]
        assert_holder_intact(server, holder, path, content)


def test_concurrent_takeovers_and_a_delayed_edit_hand_the_draft_over_once(
    tmp_path, monkeypatch
):
    root = tmp_path / "drafts"
    with running(root) as server:
        holder = Window(server)
        holder.edit(BOND)
        [path] = draft_files(root)
        rescuers = [Window(server), Window(server)]
        results: dict[str, tuple[int, dict]] = {}

        def attempt(label: str, call) -> None:
            results[label] = call()

        calls = {
            "edit": lambda: holder.request("edit", edit=bond_at(40)),
            **{
                f"rescuer{index}": partial(
                    rescuer.request, "recover_draft", draft=path.stem, takeover=True
                )
                for index, rescuer in enumerate(rescuers)
            },
        }
        session = live_session(server, holder)
        # The real lookup, counted when it names the original holder.
        observed = threading.Semaphore(0)
        owner_of = server.drafts.owner_of

        def observing_owner_of(draft_id: str) -> object | None:
            owner = owner_of(draft_id)
            if owner is session:
                observed.release()
            return owner

        monkeypatch.setattr(server.drafts, "owner_of", observing_owner_of)
        # Both takeovers have found the holder before it is free; the edit
        # may arrive at any point, so every ordering stays possible.
        with session.lock:
            threads = [
                threading.Thread(target=attempt, args=item, daemon=True)
                for item in calls.items()
            ]
            for thread in threads:
                thread.start()
            for _ in range(2):
                assert observed.acquire(timeout=10)
        monkeypatch.undo()
        for thread in threads:
            thread.join(timeout=10)
        assert not any(thread.is_alive() for thread in threads)
        statuses = [results[f"rescuer{index}"][0] for index in range(2)]
        winners = [index for index, status in enumerate(statuses) if status == 200]
        assert len(winners) == 1, results
        loser = results[f"rescuer{1 - winners[0]}"]
        assert loser[0] == 400 and "another window" in loser[1]["error"]
        winner = rescuers[winners[0]]
        assert server.drafts.owner_of(path.stem) is live_session(server, winner)
        assert holder.info["session"] not in server.sessions
        # Whatever the order, the recovered drawing is the holder's last
        # accepted one and an edit after the handover was refused.
        edit_status, edit_reply = results["edit"]
        recovered = state_of(winner.info["document"])
        if edit_status == 200:
            assert recovered == state_of(edit_reply["document"])
        else:
            assert "ended" in edit_reply["error"]
            assert len(recovered["model"]["atoms"]) == 2
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert state_of(stored["document"]) == recovered
        assert draft_files(root) == [path]


def test_a_failed_removal_of_the_replaced_draft_stays_visible_and_listed(
    tmp_path, monkeypatch
):
    root = tmp_path / "drafts"
    with running(root) as server:
        window = Window(server)
        window.edit(BOND)
        [old] = draft_files(root)
        unlink = Path.unlink

        def refuse(self, *args, **kwargs):
            if self == old:
                raise PermissionError(errno.EACCES, "Permission denied")
            return unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", refuse)
        replaced = window.send("load", document=new_document(), name="Next.chemvas")
        monkeypatch.undo()
        assert replaced["recovery"]["state"] == "failed"
        assert "could not be removed" in replaced["recovery"]["message"]
        assert "Recover Unsaved Work" in replaced["recovery"]["message"]
        assert window.send("read")["recovery"]["state"] == "failed"
        # Released, so this window lists it and it can be discarded or recovered.
        assert old.exists()
        assert server.drafts.owner_of(old.stem) is None
        assert [(entry["id"], entry["open"]) for entry in window.drafts()] == [
            (old.stem, False)
        ]
        other = Window(server)
        assert [entry["open"] for entry in other.drafts()] == [False]
        window.send("discard_draft", draft=old.stem)
        assert draft_files(root) == []


def test_an_unreadable_recovery_folder_is_reported_not_empty(tmp_path, monkeypatch):
    root = tmp_path / "drafts"
    with running(root) as server:
        holder = Window(server)
        holder.edit(BOND)
        [path] = draft_files(root)
        iterdir = Path.iterdir

        def no_listing(self):
            if self == root:
                raise PermissionError(errno.EACCES, "Permission denied")
            return iterdir(self)

        monkeypatch.setattr(Path, "iterdir", no_listing)
        window = Window(server)
        listing = window.send("drafts")
        assert listing["available"] is False
        assert listing["drafts"] == []
        assert "could not be read" in listing["message"]
        # A first draft cannot be counted against the bound: the edit stays,
        # with a visible failure instead of a dropped connection.
        edited = window.edit(BOND)
        assert len(state_of(edited["document"])["model"]["atoms"]) == 2
        assert edited["recovery"]["state"] == "failed"
        assert "could not be read" in edited["recovery"]["message"]
        monkeypatch.undo()

        def denied_in_root(original):
            def call(path, *args, **kwargs):
                if isinstance(path, (str, os.PathLike)) and Path(path).parent == root:
                    raise PermissionError(errno.EACCES, "Permission denied")
                return original(path, *args, **kwargs)

            return call

        holder.close()
        # A folder that lists but cannot be searched: every stat of a file in
        # it fails, whichever call reads it, and some Path methods hide that.
        monkeypatch.setattr(os, "stat", denied_in_root(os.stat))
        monkeypatch.setattr(os, "lstat", denied_in_root(os.lstat))
        status, refused = window.request("recover_draft", draft=path.stem)
        assert status == 400
        assert "could not be read" in refused["error"]
        monkeypatch.undo()
        assert server.drafts.owner_of(path.stem) is None
        assert path.exists()


def test_undo_to_the_drafted_drawing_clears_a_failed_write(tmp_path, monkeypatch):
    root = tmp_path / "drafts"
    with running(root) as server:
        window = Window(server)
        window.edit(BOND)
        [path] = draft_files(root)

        def full_disk(*_args, **_kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(web_drafts, "atomic_write_text", full_disk)
        assert window.edit(bond_at(40))["recovery"]["state"] == "failed"
        # Back at the drawing the draft holds; no write is needed or made.
        undone = window.send("undo")
        assert undone["recovery"] == {
            "available": True,
            "state": "saved",
            "message": None,
        }
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["document"]["state"] == state_of(undone["document"])


def full_disk(*_args, **_kwargs):
    raise OSError(errno.ENOSPC, "No space left on device")


CLEAN = {"available": True, "state": "clean", "message": None}


def test_a_failed_first_write_is_not_reported_once_its_drawing_is_gone(
    tmp_path, monkeypatch
):
    root = tmp_path / "drafts"
    with running(root) as server:
        released = Window(server)
        released.edit(BOND)
        [other] = draft_files(root)
        released.close()
        window = Window(server)
        monkeypatch.setattr(web_drafts, "atomic_write_text", full_disk)
        assert window.edit(BOND)["recovery"]["state"] == "failed"
        # Undo back to the clean drawing: nothing is unprotected.
        assert window.send("undo")["recovery"] == CLEAN
        assert window.send("read")["recovery"] == CLEAN
        # File > New after the browser asked to discard the unprotected work.
        assert window.edit(BOND)["recovery"]["state"] == "failed"
        renewed = window.send("load", document=new_document(), name="New.chemvas")
        assert renewed["recovery"] == CLEAN
        # File > Open.
        assert window.edit(BOND)["recovery"]["state"] == "failed"
        opened = window.send(
            "load", document=renewed["document"], name="Opened.chemvas"
        )
        assert opened["recovery"] == CLEAN
        # Recovering another draft needs no write; it is protected as it is.
        assert window.edit(BOND)["recovery"]["state"] == "failed"
        recovered = window.send("recover_draft", draft=other.stem)
        assert recovered["recovery"] == {
            "available": True,
            "state": "saved",
            "message": None,
        }
        assert draft_files(root) == [other]


def test_a_failed_removal_replaces_an_earlier_failed_write_report(
    tmp_path, monkeypatch
):
    root = tmp_path / "drafts"
    with running(root) as server:
        window = Window(server)
        window.edit(BOND)
        [old] = draft_files(root)
        monkeypatch.setattr(web_drafts, "atomic_write_text", full_disk)
        assert window.edit(bond_at(40))["recovery"]["state"] == "failed"
        unlink = Path.unlink

        def refuse(self, *args, **kwargs):
            if self == old:
                raise PermissionError(errno.EACCES, "Permission denied")
            return unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", refuse)
        replaced = window.send("load", document=new_document(), name="Next.chemvas")
        monkeypatch.undo()
        assert replaced["recovery"]["state"] == "failed"
        assert "could not be removed" in replaced["recovery"]["message"]
        read = window.send("read")["recovery"]
        assert read["state"] == "failed"
        assert "could not be removed" in read["message"]
        assert old.exists()
        assert server.drafts.owner_of(old.stem) is None


def test_startup_keeps_staging_files_it_cannot_prove_are_its_own(tmp_path):
    root = tmp_path / "drafts"
    root.mkdir()
    # Another program's save in progress in a shared --drafts-dir.
    staging = root / f"{ATOMIC_STAGING_PREFIX}k2j4h8{ATOMIC_STAGING_SUFFIX}"
    staging.write_bytes(b'{"type": "chemvas", "partial')
    content = staging.read_bytes()
    for _restart in range(2):
        with running(root) as server:
            window = Window(server)
            window.edit(BOND)
            assert staging.read_bytes() == content
    assert len(draft_files(root)) == 2


def test_links_and_unsafe_names_in_the_folder_are_not_drafts(tmp_path):
    root = tmp_path / "drafts"
    root.mkdir()
    envelope = json.dumps(
        {
            "format": DRAFT_FORMAT,
            "version": 1,
            "name": "Elsewhere.chemvas",
            "saved_at": time.time(),
            "document": new_document(),
        }
    )
    target = tmp_path / "elsewhere.json"
    target.write_text(envelope, encoding="utf-8")
    link = root / ("e" * 24 + ".json")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are not available here")
    unsafe = root / "not a draft.json"
    unsafe.write_text(envelope, encoding="utf-8")
    contents = {path: path.read_bytes() for path in (target, unsafe)}
    with running(root) as server:
        window = Window(server)
        assert window.drafts() == []
        status, refused = window.request("recover_draft", draft=link.stem)
        assert status == 400 and "no longer exists" in refused["error"]
        status, _ = window.request("recover_draft", draft=unsafe.stem)
        assert status == 400
        assert window.send("read")["document"]["state"]["model"]["atoms"] == {}
    assert link.is_symlink() and link.resolve() == target.resolve()
    assert {path: path.read_bytes() for path in contents} == contents


def test_idle_windows_release_their_drafts(tmp_path):
    root = tmp_path / "drafts"
    with running(root) as server:
        idle = Window(server)
        idle.edit(BOND)
        watcher = Window(server)
        assert [entry["open"] for entry in watcher.drafts()] == [True]
        with server.session_lock:
            server.sessions[idle.info["session"]].last_used -= SESSION_IDLE_SECONDS
            server.drop_idle_sessions()
        assert [entry["open"] for entry in watcher.drafts()] == [False]


def test_damaged_and_foreign_drafts_are_kept_until_discarded(tmp_path):
    root = tmp_path / "drafts"
    root.mkdir()
    damaged = root / ("a" * 24 + ".json")
    damaged.write_text("{", encoding="utf-8")
    newer = root / ("b" * 24 + ".json")
    newer.write_text(
        json.dumps(
            {
                "format": DRAFT_FORMAT,
                "version": 2,
                "name": "Future.chemvas",
                "saved_at": time.time(),
                "document": new_document(),
            }
        ),
        encoding="utf-8",
    )
    invalid = root / ("c" * 24 + ".json")
    invalid.write_text(
        json.dumps(
            {
                "format": DRAFT_FORMAT,
                "version": 1,
                "name": "Broken.chemvas",
                "saved_at": time.time(),
                "document": {"type": "chemvas", "version": 9, "state": {}},
            }
        ),
        encoding="utf-8",
    )
    unrelated = root / "notes.txt"
    unrelated.write_text("mine", encoding="utf-8")
    contents = {path: path.read_bytes() for path in (damaged, newer, invalid)}
    with running(root) as server:
        window = Window(server)
        listed = {entry["id"]: entry for entry in window.drafts()}
        assert "damaged" in listed[damaged.stem]["problem"]
        assert "another Chemvas version" in listed[newer.stem]["problem"]
        assert listed[invalid.stem]["problem"] is None
        for path in (damaged, newer, invalid):
            status, refused = window.request("recover_draft", draft=path.stem)
            assert status == 400, path
            assert "kept" in refused["error"]
        assert {path: path.read_bytes() for path in contents} == contents
        # A refused recovery leaves the draft free for a later choice.
        assert not listed[invalid.stem]["open"]
        assert [entry["open"] for entry in window.drafts()] == [False] * 3
        remaining = window.send("discard_draft", draft=damaged.stem)["drafts"]
        assert damaged.stem not in {entry["id"] for entry in remaining}
        assert not damaged.exists()
    assert newer.exists() and invalid.exists()
    assert unrelated.read_text(encoding="utf-8") == "mine"


def test_discarding_needs_a_closed_window_and_a_draft_name(tmp_path):
    root = tmp_path / "drafts"
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with running(root) as server:
        holder = Window(server)
        holder.edit(BOND)
        [path] = draft_files(root)
        other = Window(server)
        status, refused = other.request("discard_draft", draft=path.stem)
        assert status == 400
        assert "open in a window" in refused["error"]
        for name in ("../outside", "outside", "", None):
            status, _ = other.request("discard_draft", draft=name)
            assert status == 400
        assert outside.exists()
        holder.close()
        other.send("discard_draft", draft=path.stem)
        assert draft_files(root) == []


def test_store_refuses_writers_that_do_not_hold_the_draft(tmp_path):
    store = BrowserDraftStore(tmp_path)
    draft, document = "d" * 24, new_document()
    try:
        owner, stranger = object(), object()
        store.write(draft, owner, name="A.chemvas", document=document)
        path = tmp_path / f"{draft}.json"
        content = path.read_bytes()
        with pytest.raises(DraftError, match="Another window"):
            store.write(draft, stranger, name="B.chemvas", document=document)
        # A closed window's released draft cannot be written by anyone.
        store.release(draft, owner)
        with pytest.raises(DraftError, match="Another window"):
            store.write(draft, owner, name="C.chemvas", document=document)
        assert path.read_bytes() == content
        # A stale discard from a non-owner removes nothing.
        store.discard(draft, stranger)
        assert path.exists()
    finally:
        store.close()


@pytest.mark.parametrize(
    ("platform", "environment", "expected"),
    [
        ("darwin", {}, ("Library", "Application Support")),
        ("linux", {"XDG_DATA_HOME": "relative"}, (".local", "share")),
        ("win32", {"LOCALAPPDATA": "{home}/Local"}, ("Local",)),
    ],
)
def test_default_drafts_root_is_per_user_without_qt(
    tmp_path, monkeypatch, platform, environment, expected
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(web_drafts.sys, "platform", platform)
    for key in ("XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value.format(home=tmp_path))
    expected_root = tmp_path.joinpath(*expected, "Chemvas", "browser-drafts")
    assert default_drafts_root() == expected_root
