"""Offline aiogram seam and disposable SQLite feasibility proof."""
import asyncio
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ordered_ingress_proof import Incoming, ProofStore, TaskSupervisor


def incoming(number, kind="text", user=41, text="fixture"):
    return Incoming(user, user, number, kind, text)


def aiogram_probe(*args):
    # The host has pytest; the running DEV image has installed aiogram 3.30.
    # docker exec runs a fake-update script only: no bot.py import or network API.
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "bot", "python", "-B",
         "services/ordered_ingress_proof.py", *args],
        cwd=ROOT, text=True, capture_output=True, check=True, timeout=30,
    )
    return json.loads(result.stdout.splitlines()[-1]), result.stderr


def test_public_aiogram_polling_seam_orders_before_concurrent_downstream():
    result, errors = aiogram_probe()
    assert result["version"] == "3.30.0"  # clear seam/version break
    assert result["received"] == result["committed"] == [101, 102, 103]
    old, reset, new = result["conversation_ids"]
    assert old != reset == new
    assert result["before_release"] == [103]
    assert result["completed"] == [103, 102, 101]
    assert result["acknowledged"] == [101, 102, 103]
    assert result["history"] == [["fixture"]]
    assert result["supervised_remaining"] == 0
    assert result["supervisor_errors"] == []
    assert errors == ""


def test_aiogram_catches_admission_exception_and_continues_polling():
    result, errors = aiogram_probe("--failure")
    assert result["received"] == [101, 102, 103]
    assert result["committed"] == [101, 103]
    assert 102 not in result["acknowledged"]
    assert "injected admission failure" in errors
    assert result["supervised_remaining"] == 0


def test_text_duplicate_unique_key_prevents_second_row():
    store = ProofStore()
    first = store.admit(incoming(101))
    duplicate = store.admit(incoming(101))
    assert first.status == "admitted"
    assert duplicate.status == "rejected" and duplicate.reason == "duplicate"
    assert store.history(41) == [("fixture",)]


def test_new_duplicate_does_not_rotate_twice():
    store = ProofStore()
    first = store.admit(incoming(102, "new"))
    second = store.admit(incoming(102, "new"))
    assert first.status == "reset"
    assert second.status == "rejected" and second.reason == "duplicate"
    assert store.db.execute("SELECT cid FROM active WHERE user_id=41").fetchone()[0] == first.conversation_id


def test_voice_reservation_then_transcript_no_placeholder():
    store = ProofStore()
    voice = incoming(103, "voice")
    result = store.admit(voice)
    assert result.status == "admitted"
    assert store.history(41) == []
    assert store.commit_voice(voice, "spoken words")
    assert store.history(41) == [("spoken words",)]
    assert not store.commit_voice(voice, "again")


def test_failed_voice_transcription_leaves_no_history():
    store = ProofStore()
    voice = incoming(103, "voice")
    store.admit(voice)
    assert not store.commit_voice(voice, None)
    assert store.history(41) == []
    assert store.db.execute("SELECT status FROM admissions WHERE message_id=103").fetchone() == ("failed",)


def test_new_after_voice_reservation_rejects_late_transcript():
    store = ProofStore()
    voice = incoming(101, "voice")
    reserved = store.admit(voice)
    reset = store.admit(incoming(102, "new"))
    assert reset.conversation_id != reserved.conversation_id
    assert not store.commit_voice(voice, "late")
    assert store.history(41) == []


def test_duplicate_voice_marker_has_single_reservation():
    store = ProofStore()
    voice = incoming(101, "voice")
    store.admit(voice)
    assert store.admit(voice).reason == "duplicate"
    assert store.db.execute("SELECT count(*) FROM admissions").fetchone() == (1,)


def test_restart_like_reload_preserves_voice_reservation(tmp_path):
    path = tmp_path / "proof.sqlite"
    store = ProofStore(sqlite3.connect(path))
    voice = incoming(101, "voice")
    store.admit(voice)
    store.db.close()
    reopened = ProofStore(sqlite3.connect(path))
    assert reopened.commit_voice(voice, "later")
    assert reopened.history(41) == [("later",)]
    reopened.db.close()


def test_cutoff_and_noncontiguous_message_ids():
    store = ProofStore()
    old = store.admit(incoming(7))
    reset = store.admit(incoming(102, "new"))
    new = store.admit(incoming(900))
    assert old.conversation_id != reset.conversation_id == new.conversation_id
    assert store.admit(incoming(101)).reason == "stale"
    assert store.history(41) == [("fixture",)]


def test_other_user_has_independent_session():
    store = ProofStore()
    one = store.admit(incoming(102, "new", user=41))
    other = store.admit(incoming(101, user=42))
    assert one.conversation_id != other.conversation_id
    assert store.history(42) == [("fixture",)]


def test_admission_failure_rolls_back():
    store = ProofStore()
    store.fail_marker = (41, 101)
    with pytest.raises(sqlite3.OperationalError):
        store.admit(incoming(101))
    assert store.db.execute("SELECT count(*) FROM active").fetchone() == (0,)
    assert store.db.execute("SELECT count(*) FROM admissions").fetchone() == (0,)
    assert store.db.execute("SELECT count(*) FROM history").fetchone() == (0,)


def test_reset_failure_rolls_back_prior_session():
    store = ProofStore()
    first = store.admit(incoming(101))
    store.fail_marker = (41, 102)
    with pytest.raises(sqlite3.OperationalError):
        store.admit(incoming(102, "new"))
    assert store.db.execute("SELECT cid FROM active WHERE user_id=41").fetchone() == (first.conversation_id,)
    assert store.history(41) == [("fixture",)]


def test_supervisor_observes_error_and_cleans_references():
    async def scenario():
        supervisor = TaskSupervisor()
        async def fail():
            raise ValueError("downstream")
        supervisor.launch(fail())
        await supervisor.drain()
        assert len(supervisor.tasks) == 0
        assert len(supervisor.errors) == 1
        assert supervisor.errors[0] == "ValueError"
    asyncio.run(scenario())


def test_supervisor_can_cancel_inflight_on_shutdown():
    async def scenario():
        supervisor = TaskSupervisor()
        started = asyncio.Event()
        async def wait_forever():
            started.set()
            await asyncio.Event().wait()
        task = supervisor.launch(wait_forever())
        await started.wait()
        await supervisor.drain(cancel=True)
        assert task.cancelled()
        assert len(supervisor.tasks) == 0
    asyncio.run(scenario())


def test_real_aiogram_voice_marker_reserved_before_transcription():
    result, errors = aiogram_probe("--voice")
    assert result["received"] == result["committed"] == [101, 102, 103]
    assert result["conversation_ids"][1] == result["conversation_ids"][2]
    assert result["reservation_status"] == "reserved"
    assert result["history"] == []
    assert result["acknowledged"] == [101, 102, 103]
    assert errors == ""
