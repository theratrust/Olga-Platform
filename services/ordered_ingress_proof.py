"""Offline ordered-ingress proof. Never imported by the running bot."""
import asyncio
from collections import deque
from dataclasses import dataclass
import json
import sqlite3
from uuid import uuid4


@dataclass(frozen=True)
class Incoming:
    user_id: int
    chat_id: int
    message_id: int
    kind: str
    text: str | None = None


@dataclass(frozen=True)
class Decision:
    status: str
    conversation_id: str | None
    marker: tuple[int, int]
    kind: str
    reason: str | None = None


class ProofStore:
    """Disposable SQLite model of proposed primitives, not a runtime migration."""

    def __init__(self, connection=None):
        self.db = connection or sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS active (user_id INTEGER PRIMARY KEY, cid TEXT NOT NULL,
                                 cutoff_chat INTEGER, cutoff_message INTEGER);
            CREATE TABLE IF NOT EXISTS admissions (user_id INTEGER, chat_id INTEGER, message_id INTEGER,
                                     cid TEXT, kind TEXT, status TEXT,
                                     PRIMARY KEY (user_id, chat_id, message_id));
            CREATE TABLE IF NOT EXISTS history (user_id INTEGER, cid TEXT, content TEXT);
        """)
        self.events = []
        self.fail_marker = None

    def _active(self, user_id):
        row = self.db.execute("SELECT cid, cutoff_chat, cutoff_message FROM active WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            cid = uuid4().hex
            self.db.execute("INSERT INTO active(user_id,cid) VALUES (?,?)", (user_id, cid))
            return cid, None, None
        return row

    def admit(self, incoming: Incoming) -> Decision:
        marker = (incoming.chat_id, incoming.message_id)
        if incoming.chat_id != incoming.user_id or incoming.message_id <= 0:
            return Decision("rejected", None, marker, incoming.kind, "incomparable")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if marker == self.fail_marker:
                raise sqlite3.OperationalError("injected admission failure")
            prior = self.db.execute(
                "SELECT cid, kind FROM admissions WHERE user_id=? AND chat_id=? AND message_id=?",
                (incoming.user_id, *marker),
            ).fetchone()
            if prior:
                self.db.rollback()
                return Decision("rejected", prior[0], marker, incoming.kind, "duplicate")
            cid, cutoff_chat, cutoff_message = self._active(incoming.user_id)
            if cutoff_chat is not None and (cutoff_chat != incoming.chat_id or cutoff_message is None):
                self.db.rollback()
                return Decision("rejected", None, marker, incoming.kind, "incomparable")
            if cutoff_message is not None and incoming.message_id <= cutoff_message:
                self.db.rollback()
                return Decision("rejected", None, marker, incoming.kind, "stale")
            if incoming.kind == "new":
                cid = uuid4().hex
                self.db.execute("UPDATE active SET cid=?, cutoff_chat=?, cutoff_message=? WHERE user_id=?",
                                (cid, *marker, incoming.user_id))
                self.db.execute("DELETE FROM history WHERE user_id=?", (incoming.user_id,))
                status, persisted_status = "reset", "reset"
            elif incoming.kind in ("text", "voice"):
                status = "admitted"
                persisted_status = "committed" if incoming.kind == "text" else "reserved"
                if incoming.kind == "text":
                    self.db.execute("INSERT INTO history VALUES (?,?,?)", (incoming.user_id, cid, incoming.text))
            else:
                raise ValueError("unsupported kind")
            self.db.execute("INSERT INTO admissions VALUES (?,?,?,?,?,?)",
                            (incoming.user_id, *marker, cid, incoming.kind, persisted_status))
            self.db.commit()
            self.events.append((incoming.message_id, status, cid))
            return Decision(status, cid, marker, incoming.kind)
        except BaseException:
            self.db.rollback()
            raise

    def commit_voice(self, incoming: Incoming, transcript: str | None) -> bool:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("""SELECT a.cid, a.status, s.cid FROM admissions a
                JOIN active s ON s.user_id=a.user_id
                WHERE a.user_id=? AND a.chat_id=? AND a.message_id=? AND a.kind='voice'""",
                (incoming.user_id, incoming.chat_id, incoming.message_id)).fetchone()
            if not row or row[1] != "reserved" or row[0] != row[2]:
                self.db.rollback()
                return False
            if not transcript:
                self.db.execute("UPDATE admissions SET status='failed' WHERE user_id=? AND chat_id=? AND message_id=?",
                                (incoming.user_id, incoming.chat_id, incoming.message_id))
                self.db.commit()
                return False
            self.db.execute("INSERT INTO history VALUES (?,?,?)", (incoming.user_id, row[0], transcript))
            self.db.execute("UPDATE admissions SET status='committed' WHERE user_id=? AND chat_id=? AND message_id=?",
                            (incoming.user_id, incoming.chat_id, incoming.message_id))
            self.db.commit()
            return True
        except BaseException:
            self.db.rollback()
            raise

    def history(self, user_id):
        return self.db.execute("""SELECT content FROM history WHERE user_id=? AND cid=(SELECT cid FROM active WHERE user_id=?)""",
                               (user_id, user_id)).fetchall()


class TaskSupervisor:
    def __init__(self):
        self.tasks = set()
        self.errors = deque(maxlen=16)

    def launch(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task):
        self.tasks.discard(task)
        if not task.cancelled():
            error = task.exception()  # Observe exception; no "never retrieved" warning.
            if error is not None:
                self.errors.append(type(error).__name__)

    async def drain(self, *, cancel=False):
        pending = tuple(self.tasks)
        if cancel:
            for task in pending:
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


class OrderedIngressMiddleware:
    """Real aiogram-compatible update outer middleware; no aiogram import needed."""

    def __init__(self, store: ProofStore, supervisor: TaskSupervisor):
        self.store = store
        self.supervisor = supervisor
        self.received = []
        self.rejected = []

    async def __call__(self, handler, event, data):
        message = getattr(event, "message", None)
        if message is None:
            self.supervisor.launch(handler(event, dict(data)))
            return None
        user = getattr(message, "from_user", None)
        chat = getattr(message, "chat", None)
        if user is None or chat is None or chat.type != "private" or chat.id != user.id:
            self.supervisor.launch(handler(event, dict(data)))
            return None
        kind = "new" if message.text == "/new" else "voice" if message.voice else "text" if message.text else None
        if kind is None:
            self.supervisor.launch(handler(event, dict(data)))
            return None
        incoming = Incoming(user.id, chat.id, message.message_id, kind, message.text if kind == "text" else None)
        self.received.append(incoming.message_id)
        decision = self.store.admit(incoming)  # short committed phase; exception propagates to aiogram
        if decision.status == "rejected":
            self.rejected.append((incoming.message_id, decision.reason))
            return None
        copied = dict(data)
        copied["ordered_admission"] = decision
        self.supervisor.launch(handler(event, copied))
        return None


async def aiogram_polling_probe(*, fail=False, voice=False):
    """Fake update source drives real aiogram start_polling with no network calls."""
    import inspect
    from unittest.mock import patch, AsyncMock
    import aiogram
    from aiogram import Bot, Dispatcher
    from aiogram.types import Chat, Message, Update, User, Voice
    from datetime import datetime, timezone

    assert aiogram.__version__ == "3.30.0", aiogram.__version__
    assert "handle_as_tasks" in inspect.signature(Dispatcher.start_polling).parameters
    store = ProofStore()
    supervisor = TaskSupervisor()
    middleware = OrderedIngressMiddleware(store, supervisor)
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(middleware)
    started, completed, acknowledged = [], [], []
    release_101 = asyncio.Event()
    release_102 = asyncio.Event()

    async def downstream(message: Message, ordered_admission: Decision):
        mid = message.message_id
        started.append((mid, ordered_admission.conversation_id))
        acknowledged.append(mid)  # Only after committed admission, before long work.
        if mid == 101:
            await release_101.wait()
        if mid == 102:
            await release_102.wait()
        completed.append(mid)

    dispatcher.message.register(downstream)
    bot = Bot(token="123456:OFFLINE_FAKE_TOKEN")
    user = User(id=41, is_bot=False, first_name="Fixture")
    chat = Chat(id=41, type="private")
    ids = (101, 102, 103) if not fail else (101, 102, 103)
    updates = []
    for i, mid in enumerate(ids, 1):
        content = (
            {"voice": Voice(file_id="offline", file_unique_id="offline-unique", duration=1)}
            if voice and mid == 103 else
            {"text": "/new" if mid == 102 else "fixture"}
        )
        updates.append(Update(update_id=i, message=Message(
            message_id=mid, date=datetime.now(timezone.utc), chat=chat, from_user=user,
            **content,
        )))
    if fail:
        store.fail_marker = (41, 102)

    async def fake_listen(cls, fake_bot, **kwargs):
        assert fake_bot is bot
        for update in updates:
            yield update

    with patch.object(Dispatcher, "_listen_updates", classmethod(fake_listen)), \
         patch.object(Bot, "me", new=AsyncMock(return_value=User(id=123456, is_bot=True, first_name="Offline"))):
        await dispatcher.start_polling(bot, handle_as_tasks=False, handle_signals=False,
                                       close_bot_session=False)
    await asyncio.sleep(0)  # scheduling yield, not an ordering timer
    before_release = list(completed)
    release_102.set()
    await asyncio.sleep(0)
    release_101.set()
    await supervisor.drain()
    return {
        "version": aiogram.__version__,
        "received": middleware.received,
        "committed": [item[0] for item in store.events],
        "conversation_ids": [item[2] for item in store.events],
        "started": [item[0] for item in started],
        "completed": completed,
        "before_release": before_release,
        "acknowledged": acknowledged,
        "history": store.history(41),
        "supervised_remaining": len(supervisor.tasks),
        "supervisor_errors": list(supervisor.errors),
        "failure": fail,
        "reservation_status": store.db.execute("SELECT status FROM admissions WHERE message_id=103").fetchone()[0],
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(asyncio.run(aiogram_polling_probe(fail="--failure" in sys.argv, voice="--voice" in sys.argv))))
