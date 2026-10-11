"""Offline ingress prototype: disposable SQLite and deterministic task barriers."""
import asyncio
import sqlite3

import pytest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database
from services.ordered_admission_prototype import (
    AdmissionResult,
    IngressMessage,
    OrderedAdmissionPrototype,
)


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "ordered.db"))
    asyncio.run(database.init_db())
    return tmp_path / "ordered.db"


def event(sequence, message_id, kind="normal_text", user_id=41, text=None):
    return IngressMessage(
        polling_sequence=sequence,
        user_id=user_id,
        chat_id=user_id,
        message_id=message_id,
        kind=kind,
        text=text,
    )


def real_ports(ack=None, downstream=None):
    async def admit(update):
        return await database.admit_user_message(
            update.user_id, "Fixture", "", update.text or "offline",
            update.chat_id, update.message_id,
        )

    async def rotate(update):
        return await database.rotate_conversation(
            update.user_id, update.chat_id, update.message_id,
        )

    async def no_op(_result):
        return None

    return OrderedAdmissionPrototype(
        admit, rotate, ack or no_op, downstream or no_op,
    )


def run(coro):
    return asyncio.run(coro)


def test_101_102_103_ingress_order_captures_a_then_b(db):
    async def scenario():
        pipeline = real_ports()
        tasks = [
            pipeline.offer(event(1, 101, text="old")),
            pipeline.offer(event(2, 102, "new")),
            pipeline.offer(event(3, 103, text="new")),
        ]
        old, reset, new = await asyncio.gather(*tasks)
        assert [item.status for item in (old, reset, new)] == [
            "admitted", "reset", "admitted",
        ]
        assert old.conversation_id != reset.conversation_id
        assert new.conversation_id == reset.conversation_id
        assert await database.get_recent_history(
            41, new.conversation_id, limit=20,
        ) == [{"role": "user", "content": "new"}]
        await pipeline.wait_for_downstream()

    run(scenario())


def test_103_downstream_can_start_before_reset_downstream(db):
    async def scenario():
        started = {number: asyncio.Event() for number in (101, 102, 103)}
        release = {number: asyncio.Event() for number in (101, 102, 103)}
        completed = []

        async def downstream(result):
            number = result.marker[1]
            started[number].set()
            await release[number].wait()
            completed.append(number)

        pipeline = real_ports(downstream=downstream)
        tasks = [
            pipeline.offer(event(1, 101)),
            pipeline.offer(event(2, 102, "new")),
            pipeline.offer(event(3, 103)),
        ]
        old, reset, newer = await asyncio.gather(*tasks)
        for gate in started.values():
            await asyncio.wait_for(gate.wait(), 1)
        assert newer.conversation_id == reset.conversation_id
        assert old.conversation_id != newer.conversation_id

        release[103].set()
        release[102].set()
        release[101].set()
        await pipeline.wait_for_downstream()
        assert completed == [103, 102, 101]

    run(scenario())


def test_long_101_generation_does_not_block_reset_or_103(db):
    async def scenario():
        generating = asyncio.Event()
        finish = asyncio.Event()

        async def downstream(result):
            if result.marker[1] == 101:
                generating.set()
                await finish.wait()

        pipeline = real_ports(downstream=downstream)
        old = await pipeline.offer(event(1, 101))
        await asyncio.wait_for(generating.wait(), 1)
        reset_task = pipeline.offer(event(2, 102, "new"))
        new_task = pipeline.offer(event(3, 103))
        reset, newer = await asyncio.wait_for(
            asyncio.gather(reset_task, new_task), 2,
        )
        assert old.conversation_id != newer.conversation_id
        assert reset.conversation_id == newer.conversation_id
        assert not finish.is_set()
        finish.set()
        await pipeline.wait_for_downstream()

    run(scenario())


def test_late_101_after_reset_is_rejected_not_reassigned(db):
    async def scenario():
        acked = []

        async def acknowledge(result):
            acked.append(result.marker[1])

        pipeline = real_ports(ack=acknowledge)
        reset = await pipeline.offer(event(1, 102, "new"))
        stale = await pipeline.offer(event(2, 101))
        assert stale == AdmissionResult(
            2, 41, "normal_text", (41, 101), "rejected", None, "stale",
        )
        assert await database.get_recent_history(
            41, reset.conversation_id, limit=20,
        ) == []
        await pipeline.wait_for_downstream()
        assert acked == [102]

    run(scenario())


def test_voice_marker_uses_same_ordered_phase_with_reservation_port():
    async def scenario():
        # This fake models an atomic voice-marker reservation. Current runtime
        # DB lacks that operation; no fabricated transcript is persisted here.
        current = {}
        reservations = []
        counter = 0

        async def rotate(update):
            nonlocal counter
            counter += 1
            current[update.user_id] = f"session-{counter}"
            return current[update.user_id]

        async def admit(update):
            session = current.setdefault(update.user_id, "session-A")
            if update.kind == "voice":
                reservations.append((update.message_id, session))
            return session, None

        async def no_op(_result):
            return None

        pipeline = OrderedAdmissionPrototype(admit, rotate, no_op, no_op)
        reset = pipeline.offer(event(1, 102, "new"))
        voice = pipeline.offer(event(2, 103, "voice"))
        reset_result, voice_result = await asyncio.gather(reset, voice)
        assert voice_result.conversation_id == reset_result.conversation_id
        assert reservations == [(103, reset_result.conversation_id)]
        await pipeline.wait_for_downstream()

    run(scenario())


def test_two_users_have_independent_admission_lanes():
    async def scenario():
        waiting = asyncio.Event()
        release = asyncio.Event()

        async def admit(update):
            if update.user_id == 41:
                waiting.set()
                await release.wait()
            return f"session-{update.user_id}", None

        async def rotate(_update):
            raise AssertionError("unused")

        async def no_op(_result):
            return None

        pipeline = OrderedAdmissionPrototype(admit, rotate, no_op, no_op)
        slow = pipeline.offer(event(1, 101, user_id=41))
        await waiting.wait()
        fast = pipeline.offer(event(2, 901, user_id=42))
        assert (await asyncio.wait_for(fast, 1)).conversation_id == "session-42"
        assert not slow.done()
        release.set()
        assert (await slow).conversation_id == "session-41"
        await pipeline.wait_for_downstream()

    run(scenario())


def test_rapid_new_preserves_latest_cutoff(db):
    async def scenario():
        pipeline = real_ports()
        first = pipeline.offer(event(1, 102, "new"))
        second = pipeline.offer(event(2, 104, "new"))
        a, b = await asyncio.gather(first, second)
        assert a.status == b.status == "reset"
        assert a.conversation_id != b.conversation_id
        assert await database.get_or_create_conversation_id(41) == b.conversation_id
        assert (await pipeline.offer(event(3, 103))).reason == "stale"
        assert (await pipeline.offer(event(4, 105))).conversation_id == b.conversation_id
        await pipeline.wait_for_downstream()

    run(scenario())


def test_admission_db_failure_has_no_ack_or_downstream(db):
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TRIGGER fail_admit BEFORE INSERT ON chat_messages
                        BEGIN SELECT RAISE(ABORT, 'fixture failure'); END""")

    async def scenario():
        acked, worked = [], []

        async def acknowledge(result):
            acked.append(result)

        async def downstream(result):
            worked.append(result)

        pipeline = real_ports(ack=acknowledge, downstream=downstream)
        result = await pipeline.offer(event(1, 101))
        await pipeline.wait_for_downstream()
        assert (result.status, result.reason) == ("rejected", "db_failure")
        assert acked == worked == []
        with sqlite3.connect(db) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM chat_messages"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM active_chat_sessions"
            ).fetchone()[0] == 0

    run(scenario())


def test_reset_db_failure_has_no_ack_or_downstream(db):
    async def scenario():
        acked = []

        async def acknowledge(result):
            acked.append(result.marker[1])

        pipeline = real_ports(ack=acknowledge)
        admitted = await pipeline.offer(event(1, 101))
        await pipeline.wait_for_downstream()
        with sqlite3.connect(db) as conn:
            conn.execute("""CREATE TRIGGER fail_reset BEFORE DELETE ON chat_messages
                            BEGIN SELECT RAISE(ABORT, 'fixture failure'); END""")
        failed = await pipeline.offer(event(2, 102, "new"))
        assert (failed.status, failed.reason) == ("rejected", "db_failure")
        assert await database.get_or_create_conversation_id(41) == admitted.conversation_id
        assert await database.get_recent_history(
            41, admitted.conversation_id, limit=20,
        ) == [{"role": "user", "content": "offline"}]
        await pipeline.wait_for_downstream()
        assert acked == [101]

    run(scenario())


def test_acknowledgement_happens_after_commit_and_before_downstream(db):
    async def scenario():
        events = []

        async def acknowledge(result):
            history = await database.get_recent_history(
                41, result.conversation_id, limit=20,
            )
            assert history == [{"role": "user", "content": "accepted"}]
            events.append("ack")

        async def downstream(_result):
            events.append("work")

        pipeline = real_ports(ack=acknowledge, downstream=downstream)
        admitted = await pipeline.offer(event(1, 101, text="accepted"))
        assert admitted.status == "admitted"
        await pipeline.wait_for_downstream()
        assert events == ["ack", "work"]

    run(scenario())


def test_new_acknowledgement_happens_after_reset_commit(db):
    async def scenario():
        old, _ = await database.admit_user_message(
            41, "Fixture", "", "old", 41, 101,
        )
        seen = []

        async def acknowledge(result):
            assert result.conversation_id != old
            assert await database.get_recent_history(
                41, result.conversation_id, limit=20,
            ) == []
            seen.append(result.status)

        pipeline = real_ports(ack=acknowledge)
        assert (await pipeline.offer(event(1, 102, "new"))).status == "reset"
        await pipeline.wait_for_downstream()
        assert seen == ["reset"]

    run(scenario())


def test_missing_message_ids_are_not_inferred(db):
    async def scenario():
        pipeline = real_ports()
        first = await pipeline.offer(event(1, 101))
        reset = await pipeline.offer(event(2, 250, "new"))
        later = await pipeline.offer(event(3, 900))
        assert first.conversation_id != reset.conversation_id
        assert later.conversation_id == reset.conversation_id
        await pipeline.wait_for_downstream()

    run(scenario())


def test_reordered_offer_is_rejected_instead_of_sorting_tasks(db):
    async def scenario():
        pipeline = real_ports()
        first = pipeline.offer(event(20, 101))
        with pytest.raises(ValueError, match="ingress order"):
            pipeline.offer(event(19, 102, "new"))
        assert (await first).status == "admitted"
        await pipeline.wait_for_downstream()

    run(scenario())


def test_invalid_private_marker_is_rejected_without_ack(db):
    async def scenario():
        acked = []

        async def acknowledge(result):
            acked.append(result)

        pipeline = real_ports(ack=acknowledge)
        invalid = IngressMessage(1, 41, 900, 103, "normal_text")
        rejected = await pipeline.offer(invalid)
        assert (rejected.status, rejected.reason) == ("rejected", "incomparable")
        await pipeline.wait_for_downstream()
        assert acked == []

    run(scenario())


def test_commit_survives_downstream_crash_without_cross_session_corruption(db):
    async def scenario():
        started = asyncio.Event()
        never = asyncio.Event()

        async def downstream(_result):
            started.set()
            await never.wait()

        pipeline = real_ports(downstream=downstream)
        admitted = await pipeline.offer(event(1, 101))
        await started.wait()
        for task in pipeline._work:  # simulate process death after admission
            task.cancel()
        await asyncio.gather(*pipeline._work, return_exceptions=True)
        assert await database.get_recent_history(
            41, admitted.conversation_id, limit=20,
        ) == [{"role": "user", "content": "offline"}]
        reset = await pipeline.offer(event(2, 102, "new"))
        assert reset.conversation_id != admitted.conversation_id

    run(scenario())


def test_103_downstream_starts_while_102_downstream_is_delayed(db):
    async def scenario():
        release_reset_ack = asyncio.Event()
        started_103 = asyncio.Event()
        downstream_started = []

        async def acknowledge(result):
            if result.marker[1] == 102:
                await release_reset_ack.wait()

        async def downstream(result):
            downstream_started.append(result.marker[1])
            if result.marker[1] == 103:
                started_103.set()

        pipeline = real_ports(ack=acknowledge, downstream=downstream)
        reset = pipeline.offer(event(1, 102, "new"))
        newer = pipeline.offer(event(2, 103))
        reset_result, newer_result = await asyncio.gather(reset, newer)
        assert newer_result.conversation_id == reset_result.conversation_id
        await asyncio.wait_for(started_103.wait(), 1)
        assert downstream_started == [103]
        release_reset_ack.set()
        await pipeline.wait_for_downstream()
        assert downstream_started == [103, 102]

    run(scenario())
