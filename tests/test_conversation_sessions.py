"""Offline SQLite checks for the DEV logical conversation fence."""
import asyncio
from itertools import count
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import database
from services.coaching_generator import DEFAULT_MAX_TOKENS, build_messages
from services.conversation_state import build_carry_forward
from prompts.coaching import DEFAULT_SYSTEM_PROMPT


@pytest.fixture
def db(monkeypatch, tmp_path):
    path = tmp_path / "sessions.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    asyncio.run(database.init_db())
    return path


def run(coro):
    return asyncio.run(coro)


_reset_messages = count(1000)


async def reset(user_id):
    return await database.rotate_conversation(user_id, user_id, next(_reset_messages))


def test_first_use_is_stable_db_id_and_users_are_isolated(db):
    async def scenario():
        first = await database.get_or_create_conversation_id(41)
        assert first == await database.get_or_create_conversation_id(41)
        other = await database.get_or_create_conversation_id(42)
        assert first != other and len(first) == len(other) == 32
        assert await database.add_chat_message(41, "A", "", "user", "User A", first)
        assert await database.add_chat_message(42, "B", "", "user", "User B", other)
        assert await database.get_recent_history(41, first) == [{"role": "user", "content": "User A"}]
        assert await database.get_recent_history(42, other) == [{"role": "user", "content": "User B"}]
    run(scenario())


def test_user_assistant_same_id_and_latest_twenty_in_order(db):
    async def scenario():
        cid = await database.get_or_create_conversation_id(41)
        for i in range(26):
            assert await database.add_chat_message(
                41, "A", "", "user" if i % 2 == 0 else "assistant", f"turn {i}", cid
            )
        history = await database.get_recent_history(41, cid, limit=20)
        assert [m["content"] for m in history] == [f"turn {i}" for i in range(6, 26)]
        assert [m["role"] for m in history] == ["user" if i % 2 == 0 else "assistant" for i in range(6, 26)]
        with sqlite3.connect(db) as conn:
            assert {row[0] for row in conn.execute("SELECT conversation_id FROM chat_messages")} == {cid}
    run(scenario())


def test_new_rotates_deletes_rows_and_drafts_and_rejects_late_a_write(db):
    async def scenario():
        a = await database.get_or_create_conversation_id(41)
        assert await database.add_chat_message(41, "A", "", "user", "A turn", a)
        draft = await database.create_pending_draft(41, "A", "A turn", "A answer", a)
        assert draft
        b = await reset(41)
        assert b != a
        assert await database.get_or_create_conversation_id(41) == b
        assert await database.get_recent_history(41, b, limit=20) == []
        assert await database.get_conversation_history_with_ids(41, b) == []
        assert await database.get_pending_draft(draft) is None
        assert not await database.add_chat_message(41, "A", "", "assistant", "late A", a)
        assert await database.create_pending_draft(41, "A", "A turn", "late A", a) is None
        assert not await database.save_approved_draft_message(draft, "N/A", "late A", "APPROVED")
        assert await database.add_chat_message(41, "A", "", "user", "B turn", b)
        assert await database.get_recent_history(41, b, limit=20) == [{"role": "user", "content": "B turn"}]
    run(scenario())


def test_ledger_and_history_require_both_user_and_conversation(db):
    async def scenario():
        a = await database.get_or_create_conversation_id(41)
        assert await database.add_chat_message(41, "A", "", "user", "Не хочу возвращаться к этой теме.", a)
        b = await reset(41)
        # Deliberately retain an A-tagged fixture row to prove filters, independent of deletion.
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO chat_messages(user_id, role, content, conversation_id) VALUES (?,?,?,?)",
                (41, "user", "Не хочу возвращаться к этой теме.", a),
            )
        for i in range(26):
            assert await database.add_chat_message(41, "A", "", "user", f"B {i}", b)
        recent = await database.get_recent_history(41, b, limit=20)
        rows = await database.get_conversation_history_with_ids(41, b)
        assert len(rows) == 26
        assert build_carry_forward(rows, recent) == []
        assert all("Не хочу" not in m["content"] for m in recent)
        assert len(await database.get_conversation_history_with_ids(41, a)) == 1
    run(scenario())


def test_two_rapid_new_commands_leave_only_latest_id(db):
    async def scenario():
        a = await database.get_or_create_conversation_id(41)
        b = await reset(41)
        c = await reset(41)
        assert len({a, b, c}) == 3
        assert await database.get_or_create_conversation_id(41) == c
        assert not await database.add_chat_message(41, "A", "", "assistant", "A", a)
        assert not await database.add_chat_message(41, "A", "", "assistant", "B", b)
        assert await database.add_chat_message(41, "A", "", "user", "C", c)
        assert [m["content"] for m in await database.get_recent_history(41, c)] == ["C"]
    run(scenario())


def test_pending_draft_approval_is_bound_to_active_id(db):
    async def scenario():
        cid = await database.get_or_create_conversation_id(41)
        draft = await database.create_pending_draft(41, "A", "question", "answer", cid)
        assert await database.is_pending_draft_active(draft)
        assert await database.save_approved_draft_message(draft, "N/A", "answer", "APPROVED")
        assert not await database.save_approved_draft_message(draft, "N/A", "answer", "APPROVED")
        assert await database.get_recent_history(41, cid) == [{"role": "assistant", "content": "answer"}]
        stale = await database.create_pending_draft(41, "A", "later", "later answer", cid)
        await reset(41)
        assert not await database.is_pending_draft_active(stale)
        assert not await database.save_approved_draft_message(stale, "N/A", "later answer", "APPROVED")
    run(scenario())


def test_legacy_null_rows_and_drafts_fail_closed_on_repeatable_upgrade(monkeypatch, tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, full_name TEXT, username TEXT, role TEXT, content TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE pending_drafts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, full_name TEXT, user_message TEXT, ai_draft TEXT, status TEXT DEFAULT 'PENDING', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO chat_messages (user_id, role, content) VALUES (41, 'user', 'legacy boundary')")
        conn.execute("INSERT INTO pending_drafts (user_id, ai_draft) VALUES (41, 'legacy answer')")
    monkeypatch.setattr(database, "DB_PATH", str(path))
    run(database.init_db())
    run(database.init_db())
    async def scenario():
        cid = await database.get_or_create_conversation_id(41)
        assert await database.get_recent_history(41, cid, limit=20) == []
        assert await database.get_conversation_history_with_ids(41, cid) == []
        assert not await database.is_pending_draft_active(1)
        assert not await database.save_approved_draft_message(1, "N/A", "legacy answer", "APPROVED")
        assert await database.add_chat_message(41, "A", "", "user", "new", cid)
        assert [m["content"] for m in await database.get_recent_history(41, cid)] == ["new"]
        await reset(41)
    run(scenario())
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_messages WHERE user_id = 41").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM pending_drafts WHERE user_id = 41").fetchone()[0] == 0
        assert all("conversation_id" in {r[1] for r in conn.execute(f"PRAGMA table_info({name})")}
                   for name in ("chat_messages", "pending_drafts"))


def test_restart_reuses_active_id_without_fsm(db):
    first = run(database.get_or_create_conversation_id(41))
    assert run(database.get_or_create_conversation_id(41)) == first


def test_prompt_model_contract_unchanged():
    assert DEFAULT_MAX_TOKENS == 350
    assert "Если человек говорит «я не знаю»" in DEFAULT_SYSTEM_PROMPT
    history = [{"role": "user", "content": "Я не знаю."}]
    assert build_messages(DEFAULT_SYSTEM_PROMPT, history) == [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT}, *history
    ]


def test_admin_approve_rejects_stale_draft_before_send(db, monkeypatch):
    import importlib.util
    import types
    from unittest.mock import AsyncMock

    class Expression:
        def __getattr__(self, _name): return self
        def startswith(self, *_args): return self

    aiogram = types.ModuleType("aiogram")
    aiogram.Bot = aiogram.Dispatcher = object
    aiogram.types = types.SimpleNamespace(Message=object, CallbackQuery=object)
    aiogram.F = Expression()
    filters = types.ModuleType("aiogram.filters")
    filters.Command = lambda *_args: object()
    filters.CommandObject = object
    fsm = types.ModuleType("aiogram.fsm.context")
    fsm.FSMContext = object
    tgtypes = types.ModuleType("aiogram.types")
    tgtypes.InlineKeyboardButton = tgtypes.InlineKeyboardMarkup = object
    for name, module in {
        "aiogram": aiogram, "aiogram.filters": filters,
        "aiogram.fsm.context": fsm, "aiogram.types": tgtypes,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location("session_test_admin", ROOT / "handlers/admin.py")
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)
    callbacks = {}

    class Registrar:
        def __call__(self, *_args):
            def capture(function):
                callbacks[function.__name__] = function
                return function
            return capture

    dp = types.SimpleNamespace(message=Registrar(), callback_query=Registrar())
    bot = types.SimpleNamespace(send_message=AsyncMock())
    admin.register_admin(
        dp, bot, object(), "offline", [99], types.SimpleNamespace(WAITING_FOR_EDIT=object()),
        database.get_pending_draft, database.update_draft_status,
        database.is_pending_draft_active, database.save_approved_draft_message,
    )

    async def scenario():
        old = await database.get_or_create_conversation_id(41)
        await reset(41)
        # Simulate a legacy/stale draft surviving from an older writer.
        with sqlite3.connect(db) as conn:
            cursor = conn.execute(
                "INSERT INTO pending_drafts(user_id, full_name, ai_draft, conversation_id) VALUES (?,?,?,?)",
                (41, "A", "old answer", old),
            )
            draft_id = cursor.lastrowid
        callback = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=99), data=f"approve_{draft_id}",
            answer=AsyncMock(), message=types.SimpleNamespace(edit_text=AsyncMock()),
        )
        await callbacks["approve_draft"](callback)
        assert not await database.is_pending_draft_active(draft_id)
        assert await database.get_recent_history(
            41, await database.get_or_create_conversation_id(41), limit=20
        ) == []
        callback.answer.assert_awaited_once()
        callback.message.edit_text.assert_not_awaited()

    run(scenario())
    bot.send_message.assert_not_awaited()


def _exact_legacy_fixture(path):
    """DDL copied from the pre-change database.py init_db, with representative rows."""
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                subscription_status TEXT DEFAULT 'PENDING',
                test_result TEXT,
                answers TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE knowledge_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT,
                category TEXT,
                title TEXT,
                content TEXT,
                status TEXT DEFAULT 'PENDING',
                approved_by TEXT,
                approved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                username TEXT,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE pending_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                user_message TEXT,
                ai_draft TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE channel_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                message_id INTEGER,
                text TEXT,
                updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.executemany("INSERT INTO users(user_id, full_name) VALUES (?,?)",
                         [(41, "Legacy A"), (42, "Legacy B")])
        conn.executemany(
            "INSERT INTO chat_messages(user_id, role, content) VALUES (?,?,?)",
            [(41, "user", "Не хочу возвращаться к этой теме."),
             (41, "assistant", "Прежний ответ."),
             (42, "user", "Отдельный старый разговор.")],
        )
        conn.executemany(
            "INSERT INTO pending_drafts(user_id, ai_draft, status) VALUES (?,?,?)",
            [(41, "Ожидающий A", "PENDING"),
             (41, "Отправленный A", "APPROVED"),
             (42, "Ожидающий B", "PENDING")],
        )
        conn.execute("INSERT INTO channel_posts(name, message_id, text) VALUES ('test', 7, 'post')")


def _schema_and_legacy_data(path):
    with sqlite3.connect(path) as conn:
        schema = tuple(conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ))
        columns = {
            name: tuple(row[1:3] for row in conn.execute(f"PRAGMA table_info({name})"))
            for name in ("users", "knowledge_proposals", "chat_messages",
                         "pending_drafts", "channel_posts")
        }
        rows = {
            "users": tuple(conn.execute("SELECT user_id, full_name FROM users ORDER BY user_id")),
            "chat_messages": tuple(conn.execute(
                "SELECT id, user_id, role, content, timestamp FROM chat_messages ORDER BY id"
            )),
            "pending_drafts": tuple(conn.execute(
                "SELECT id, user_id, ai_draft, status, created_at FROM pending_drafts ORDER BY id"
            )),
            "channel_posts": tuple(conn.execute("SELECT name, message_id, text FROM channel_posts")),
        }
        return schema, columns, rows


def test_exact_legacy_upgrade_preserves_rows_and_is_idempotent(monkeypatch, tmp_path):
    path = tmp_path / "exact_legacy.db"
    _exact_legacy_fixture(path)
    before_schema, before_columns, before_rows = _schema_and_legacy_data(path)
    assert {name for name in before_columns} == {
        "users", "knowledge_proposals", "chat_messages", "pending_drafts", "channel_posts"
    }
    assert "conversation_id" not in dict(before_columns["chat_messages"])
    assert "conversation_id" not in dict(before_columns["pending_drafts"])
    monkeypatch.setattr(database, "DB_PATH", str(path))
    run(database.init_db())
    first_schema, first_columns, first_rows = _schema_and_legacy_data(path)
    assert before_rows == first_rows
    assert {name for name in before_columns if before_columns[name] != first_columns[name]} == {
        "users", "chat_messages", "pending_drafts"
    }
    assert first_columns["users"] == before_columns["users"] + (("coaching_eligible", "INTEGER"),)
    for name in ("chat_messages", "pending_drafts"):
        assert first_columns[name] == before_columns[name] + (("conversation_id", "TEXT"),)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM active_chat_sessions").fetchone()[0] == 0
        assert conn.execute(
            "SELECT coaching_eligible FROM users ORDER BY user_id"
        ).fetchall() == [(0,), (0,)]
        assert {row[0] for row in conn.execute("SELECT conversation_id FROM chat_messages")} == {None}
        assert {row[0] for row in conn.execute("SELECT conversation_id FROM pending_drafts")} == {None}
        assert [r[2] for r in conn.execute("PRAGMA index_info(idx_chat_messages_session_id)")] == [
            "user_id", "conversation_id", "id"
        ]
    assert len(first_schema) == len(before_schema) + 2  # active table + intended index
    run(database.init_db())
    assert _schema_and_legacy_data(path) == (first_schema, first_columns, first_rows)


def test_first_use_after_exact_legacy_upgrade_is_fresh_and_scoped(monkeypatch, tmp_path):
    path = tmp_path / "first_use.db"
    _exact_legacy_fixture(path)
    monkeypatch.setattr(database, "DB_PATH", str(path))
    run(database.init_db())

    async def scenario():
        current = await database.get_or_create_conversation_id(41)
        assert current and current == await database.get_or_create_conversation_id(41)
        assert await database.get_recent_history(41, current, limit=20) == []
        assert await database.get_conversation_history_with_ids(41, current) == []
        assert not await database.is_pending_draft_active(1)
        assert await database.add_chat_message(41, "A", "", "user", "Свежий вопрос.", current)
        assert await database.add_chat_message(41, "A", "", "assistant", "Свежий ответ.", current)
        recent = await database.get_recent_history(41, current, limit=20)
        rows = await database.get_conversation_history_with_ids(41, current)
        assert recent == [
            {"role": "user", "content": "Свежий вопрос."},
            {"role": "assistant", "content": "Свежий ответ."},
        ]
        assert build_carry_forward(rows, recent) == []
        assert await database.get_recent_history(
            42, await database.get_or_create_conversation_id(42), limit=20
        ) == []

    run(scenario())
    with sqlite3.connect(path) as conn:
        legacy = list(conn.execute(
            "SELECT user_id, conversation_id FROM chat_messages WHERE id <= 3 ORDER BY id"
        ))
        new = list(conn.execute(
            "SELECT conversation_id FROM chat_messages WHERE id > 3 ORDER BY id"
        ))
        assert legacy == [(41, None), (41, None), (42, None)]
        assert len(new) == 2 and new[0][0] == new[1][0] and new[0][0]


def test_new_rolls_back_identity_and_deletes_on_middle_failure(db):
    async def setup():
        a = await database.get_or_create_conversation_id(41)
        assert await database.add_chat_message(41, "A", "", "user", "keep", a)
        draft = await database.create_pending_draft(41, "A", "keep", "keep draft", a)
        return a, draft

    a, draft = run(setup())
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TRIGGER fail_pending_delete
            BEFORE DELETE ON pending_drafts
            WHEN OLD.user_id = 41 AND OLD.status = 'PENDING'
            BEGIN SELECT RAISE(ABORT, 'fixture failure'); END
        """)
    with pytest.raises(sqlite3.DatabaseError, match="fixture failure"):
        run(reset(41))

    async def verify_rollback():
        assert await database.get_or_create_conversation_id(41) == a
        assert await database.get_recent_history(41, a, limit=20) == [
            {"role": "user", "content": "keep"}
        ]
        assert await database.is_pending_draft_active(draft)
        assert (await database.get_pending_draft(draft))[5] == "PENDING"

    run(verify_rollback())
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER fail_pending_delete")
    b = run(reset(41))
    assert b != a
    assert run(database.get_recent_history(41, b, limit=20)) == []
    assert run(database.get_pending_draft(draft)) is None


def test_two_users_and_rapid_new_keep_writes_and_drafts_scoped(db):
    async def scenario():
        a = await database.get_or_create_conversation_id(41)
        y = await database.get_or_create_conversation_id(42)
        a_draft = await database.create_pending_draft(41, "A", "A", "A answer", a)
        y_draft = await database.create_pending_draft(42, "Y", "Y", "Y answer", y)
        b = await reset(41)
        b_draft = await database.create_pending_draft(41, "A", "B", "B answer", b)
        c = await reset(41)
        assert len({a, b, c, y}) == 4
        assert await database.get_or_create_conversation_id(42) == y
        assert not await database.add_chat_message(41, "A", "", "assistant", "A", a)
        assert not await database.add_chat_message(41, "A", "", "assistant", "B", b)
        assert not await database.is_pending_draft_active(a_draft)
        assert not await database.is_pending_draft_active(b_draft)
        assert not await database.save_approved_draft_message(a_draft, "", "A", "APPROVED")
        assert not await database.save_approved_draft_message(b_draft, "", "B", "APPROVED")
        assert await database.get_recent_history(41, c, limit=20) == []
        assert await database.get_conversation_history_with_ids(41, c) == []
        assert await database.is_pending_draft_active(y_draft)
        assert await database.save_approved_draft_message(y_draft, "", "Y answer", "APPROVED")
        assert await database.get_recent_history(42, y, limit=20) == [
            {"role": "assistant", "content": "Y answer"}
        ]
        assert await database.get_conversation_history_with_ids(42, c) == []
        assert await database.get_conversation_history_with_ids(41, y) == []

    run(scenario())


def test_simultaneous_same_user_first_use_keeps_one_identity(db):
    async def message(index):
        cid = await database.get_or_create_conversation_id(41)
        saved = await database.add_chat_message(41, "A", "", "user", f"message {index}", cid)
        return cid, saved

    async def scenario():
        results = await asyncio.gather(message(1), message(2))
        assert all(saved for _, saved in results)
        assert results[0][0] == results[1][0]
        assert await database.get_or_create_conversation_id(41) == results[0][0]
        assert {r["content"] for r in await database.get_recent_history(
            41, results[0][0], limit=20
        )} == {"message 1", "message 2"}

    run(scenario())


def test_partly_applied_legacy_upgrade_resumes(monkeypatch, tmp_path):
    path = tmp_path / "partial_upgrade.db"
    _exact_legacy_fixture(path)
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE chat_messages ADD COLUMN conversation_id TEXT")
    monkeypatch.setattr(database, "DB_PATH", str(path))
    run(database.init_db())
    with sqlite3.connect(path) as conn:
        assert [r[1] for r in conn.execute("PRAGMA table_info(chat_messages)")].count(
            "conversation_id"
        ) == 1
        assert [r[1] for r in conn.execute("PRAGMA table_info(pending_drafts)")].count(
            "conversation_id"
        ) == 1
        assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM pending_drafts").fetchone()[0] == 3


def test_approved_draft_insert_and_status_roll_back_together(db):
    async def setup():
        cid = await database.get_or_create_conversation_id(41)
        draft = await database.create_pending_draft(41, "A", "question", "answer", cid)
        return cid, draft

    cid, draft = run(setup())
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TRIGGER fail_approval_status
            BEFORE UPDATE OF status ON pending_drafts
            WHEN NEW.status = 'APPROVED'
            BEGIN SELECT RAISE(ABORT, 'fixture approval failure'); END
        """)
    with pytest.raises(sqlite3.DatabaseError, match="fixture approval failure"):
        run(database.save_approved_draft_message(draft, "", "answer", "APPROVED"))
    assert run(database.get_recent_history(41, cid, limit=20)) == []
    assert run(database.get_pending_draft(draft))[5] == "PENDING"
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER fail_approval_status")
    assert run(database.save_approved_draft_message(draft, "", "answer", "APPROVED"))
    assert run(database.get_pending_draft(draft))[5] == "APPROVED"


def test_draft_cannot_borrow_another_users_active_id(db):
    async def scenario():
        x = await database.get_or_create_conversation_id(41)
        y = await database.get_or_create_conversation_id(42)
        assert x != y
        with sqlite3.connect(db) as conn:
            draft = conn.execute(
                "INSERT INTO pending_drafts(user_id, ai_draft, status, conversation_id) "
                "VALUES (?, ?, 'PENDING', ?)",
                (41, "wrongly tagged", y),
            ).lastrowid
        assert not await database.is_pending_draft_active(draft)
        assert not await database.save_approved_draft_message(
            draft, "", "wrongly tagged", "APPROVED"
        )
        assert await database.get_recent_history(41, x, limit=20) == []
        assert await database.get_recent_history(42, y, limit=20) == []
        assert (await database.get_pending_draft(draft))[5] == "PENDING"

    run(scenario())
