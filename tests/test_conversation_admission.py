"""Offline admission fence tests against disposable SQLite and fake Telegram ports."""
import asyncio
import importlib.util
import io
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import database
from services.conversation_admission import admission_lock, private_message_marker
from services.conversation_state import build_carry_forward
from services.coaching_generator import ExplicitTruncationError, generate_candidate as real_generate_candidate


@pytest.fixture
def db(monkeypatch, tmp_path):
    path = tmp_path / "admission.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    asyncio.run(database.init_db())
    return path


def run(coro):
    return asyncio.run(coro)


def message(user_id=41, message_id=101, text="Вопрос.", chat_type="private", chat_id=None, voice=False):
    return types.SimpleNamespace(
        from_user=types.SimpleNamespace(id=user_id, username=None),
        chat=types.SimpleNamespace(id=user_id if chat_id is None else chat_id, type=chat_type),
        message_id=message_id, text=text,
        voice=types.SimpleNamespace(file_id="offline") if voice else None, audio=None,
        answer=AsyncMock(),
    )


def test_cutoff_101_102_103_equality_and_scoped_history(db):
    async def scenario():
        a, reason = await database.admit_user_message(41, "A", "", "Before", 41, 101)
        assert a and reason is None
        b = await database.rotate_conversation(41, 41, 102)
        assert b != a
        for number in (101, 102):
            assert await database.admit_user_message(41, "A", "", "stale", 41, number) == (None, "stale")
        assert await database.admit_user_message(41, "A", "", "wrong chat", 42, 103) == (None, "incomparable")
        assert await database.admit_user_message(41, "A", "", "missing", 41, None) == (None, "incomparable")
        assert await database.admit_user_message(41, "A", "", "new", 41, 103) == (b, None)
        assert await database.get_recent_history(41, b, limit=20) == [{"role": "user", "content": "new"}]
        assert build_carry_forward(await database.get_conversation_history_with_ids(41, b),
                                   await database.get_recent_history(41, b, limit=20)) == []
    run(scenario())


def test_two_rapid_new_reverse_order_and_user_isolation(db):
    async def scenario():
        a = await database.get_or_create_conversation_id(41)
        x = await database.get_or_create_conversation_id(42)
        c = await database.rotate_conversation(41, 41, 103)
        assert c != a
        assert await database.rotate_conversation(41, 41, 102) is None
        assert await database.rotate_conversation(41, 41, 103) is None
        assert await database.get_or_create_conversation_id(41) == c
        assert await database.get_or_create_conversation_id(42) == x
        assert await database.admit_user_message(42, "B", "", "other", 42, 101) == (x, None)
        assert not await database.add_chat_message(41, "A", "", "assistant", "stale A", a)
        assert await database.admit_user_message(41, "A", "", "after", 41, 104) == (c, None)
    run(scenario())


def test_admission_insert_failure_rolls_back_first_identity(db):
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TRIGGER fail_admit BEFORE INSERT ON chat_messages
                        BEGIN SELECT RAISE(ABORT, 'fixture admission failure'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="fixture admission failure"):
        run(database.admit_user_message(41, "A", "", "private", 41, 101))
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM active_chat_sessions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0


def test_reset_delete_failure_rolls_back_cutoff_and_rows(db):
    async def setup():
        a, _ = await database.admit_user_message(41, "A", "", "keep", 41, 101)
        draft = await database.create_pending_draft(41, "A", "keep", "answer", a)
        return a, draft
    a, draft = run(setup())
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TRIGGER fail_reset BEFORE DELETE ON pending_drafts
                        BEGIN SELECT RAISE(ABORT, 'fixture reset failure'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="fixture reset failure"):
        run(database.rotate_conversation(41, 41, 102))
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT conversation_id, cutoff_chat_id, cutoff_message_id FROM active_chat_sessions WHERE user_id=41").fetchone() == (a, None, None)
        assert conn.execute("SELECT COUNT(*) FROM chat_messages WHERE user_id=41").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM pending_drafts WHERE id=?", (draft,)).fetchone()[0] == 1


def test_repeatable_partial_migration_preserves_legacy_rows(monkeypatch, tmp_path):
    path = tmp_path / "partial.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE active_chat_sessions(user_id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL, cutoff_chat_id INTEGER)")
        conn.execute("INSERT INTO active_chat_sessions VALUES (41, 'old', NULL)")
        conn.execute("CREATE TABLE chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, full_name TEXT, username TEXT, role TEXT, content TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO chat_messages(user_id, role, content) VALUES (41, 'user', 'legacy')")
        conn.execute("CREATE TABLE pending_drafts(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, full_name TEXT, user_message TEXT, ai_draft TEXT, status TEXT DEFAULT 'PENDING', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO pending_drafts(user_id, ai_draft) VALUES (41, 'legacy draft')")
    monkeypatch.setattr(database, "DB_PATH", str(path))
    run(database.init_db())
    with sqlite3.connect(path) as conn:
        first = tuple(conn.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(active_chat_sessions)")}
        assert {"cutoff_chat_id", "cutoff_message_id"} <= cols
        assert conn.execute("SELECT conversation_id, cutoff_chat_id, cutoff_message_id FROM active_chat_sessions").fetchone() == ("old", None, None)
        assert conn.execute("SELECT content, conversation_id FROM chat_messages").fetchone() == ("legacy", None)
        assert conn.execute("SELECT ai_draft, conversation_id FROM pending_drafts").fetchone() == ("legacy draft", None)
    run(database.init_db())
    with sqlite3.connect(path) as conn:
        assert first == tuple(conn.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"))
    assert run(database.admit_user_message(41, "A", "", "new", 41, 101)) == ("old", None)
    assert run(database.get_recent_history(41, "old", limit=20)) == [{"role": "user", "content": "new"}]


def _load_handlers(monkeypatch):
    class Expression:
        def __getattr__(self, _name): return self
        def startswith(self, *_args): return self
        def __invert__(self): return self
        def __and__(self, _other): return self
        def __or__(self, _other): return self
    modules = {
        "aiogram": {"Bot": object, "Dispatcher": object, "F": Expression(),
                    "types": types.SimpleNamespace(Message=object, CallbackQuery=object)},
        "aiogram.filters": {"Command": lambda *_args: object()},
        "aiogram.fsm.context": {"FSMContext": object},
        "aiogram.types": {"InlineKeyboardButton": lambda **kw: kw, "InlineKeyboardMarkup": lambda **kw: kw,
                          "FSInputFile": lambda *_args: object()},
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    loaded = {}
    for name in ("chat", "voice", "callbacks", "start", "quiz"):
        spec = importlib.util.spec_from_file_location("admission_test_" + name, ROOT / "handlers" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


@pytest.fixture
def pipeline(monkeypatch, db):
    modules = _load_handlers(monkeypatch)
    handlers = {}
    class Registrar:
        def __call__(self, *_args):
            def capture(fn): handlers[fn.__name__] = fn; return fn
            return capture
        def register(self, fn, *_args): handlers["coaching"] = fn
    dp = types.SimpleNamespace(message=Registrar(), callback_query=Registrar())
    bot = types.SimpleNamespace(send_chat_action=AsyncMock(), send_message=AsyncMock(),
                                get_file=AsyncMock(return_value=types.SimpleNamespace(file_path="offline")),
                                download_file=AsyncMock(return_value=io.BytesIO(b"audio")))
    generated = AsyncMock(return_value="Ответ.")
    monkeypatch.setattr(modules["chat"], "generate_candidate", generated)
    state = types.SimpleNamespace(get_state=AsyncMock(return_value="chat"), get_data=AsyncMock(return_value={}),
                                  set_state=AsyncMock(), update_data=AsyncMock())
    coach = modules["chat"].register_chat(
        dp, bot, object(), "offline", [], types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")),
        lambda user: "Тест", lambda user: "Тест", database.add_chat_message,
        database.get_recent_history, database.create_pending_draft,
        database.rotate_conversation, database.get_or_create_conversation_id,
        database.is_active_conversation, direct_chat=True,
        get_conversation_history_with_ids=database.get_conversation_history_with_ids,
        admit_user_message=database.admit_user_message,
    )
    transcribe = AsyncMock(return_value="Распознанный вопрос.")
    modules["voice"].register_voice(
        dp, bot, object(), "offline", [], transcribe, coach,
        types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")),
        database.get_coaching_resume_conversation_id,
    )
    modules["callbacks"].register_callbacks(dp, bot, types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")))
    return types.SimpleNamespace(db=db, modules=modules, handlers=handlers, bot=bot, dp=dp,
                                 generated=generated, transcribe=transcribe, state=state, coach=coach)


def test_private_and_group_text_reset_and_coaching_entry(pipeline):
    p = pipeline
    async def scenario():
        group = message(chat_type="group", chat_id=900)
        await p.coach(group, p.state)
        await p.handlers["cmd_new"](message(message_id=102, text="/new", chat_type="group", chat_id=900), p.state)
        assert p.state.get_state.await_count == 0
        with sqlite3.connect(p.db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM active_chat_sessions").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
        callback = types.SimpleNamespace(from_user=types.SimpleNamespace(id=41),
            message=types.SimpleNamespace(chat=group.chat, answer=AsyncMock()), answer=AsyncMock())
        await p.handlers["enter_chat"](callback, p.state)
        assert p.state.set_state.await_count == 0
        await p.coach(message(message_id=101), p.state)
        a = await database.get_or_create_conversation_id(41)
        assert await database.get_recent_history(41, a, limit=20)
        await p.handlers["cmd_new"](message(message_id=102, text="/new", chat_type="group", chat_id=900), p.state)
        assert await database.get_or_create_conversation_id(41) == a
        await p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state)
        b = await database.get_or_create_conversation_id(41)
        assert b != a and await database.get_recent_history(41, b, limit=20) == []
        assert p.generated.await_count == 1
    run(scenario())


def test_delayed_old_handler_rejected_after_new_and_newer_admitted(pipeline, caplog):
    p = pipeline
    async def scenario():
        await p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state)
        await p.coach(message(message_id=101, text="Не хочу возвращаться к этой теме."), p.state)
        assert p.generated.await_count == 0
        await p.coach(message(message_id=103, text="Новый вопрос."), p.state)
        b = await database.get_or_create_conversation_id(41)
        rows = await database.get_conversation_history_with_ids(41, b)
        assert all("Не хочу" not in row["content"] for row in rows)
        assert p.generated.await_count == 1
    with caplog.at_level("INFO"):
        run(scenario())
    assert "ADMISSION_REJECTED_STALE operation=user" in caplog.text
    assert "Не хочу" not in caplog.text


def test_generation_does_not_hold_admission_lock(pipeline, monkeypatch):
    p = pipeline
    started, release = asyncio.Event(), asyncio.Event()
    async def held(*_args):
        started.set()
        await release.wait()
        return "Ответ."
    monkeypatch.setattr(p.modules["chat"], "generate_candidate", held)
    async def scenario():
        pending = asyncio.create_task(p.coach(message(message_id=101), p.state))
        await asyncio.wait_for(started.wait(), timeout=3)
        await asyncio.wait_for(p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state), timeout=3)
        assert not admission_lock(41).locked()
        release.set()
        await pending
        b = await database.get_or_create_conversation_id(41)
        assert await database.get_recent_history(41, b, limit=20) == []
    run(scenario())


def test_group_voice_ignored_private_voice_uses_original_marker(pipeline):
    p = pipeline
    async def scenario():
        await p.handlers["handle_voice_note"](message(message_id=101, voice=True, chat_type="group", chat_id=900), p.state)
        assert p.transcribe.await_count == 0
        await p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state)
        await p.handlers["handle_voice_note"](message(message_id=101, voice=True), p.state)
        assert p.generated.await_count == 0
        await p.handlers["handle_voice_note"](message(message_id=103, voice=True), p.state)
        b = await database.get_or_create_conversation_id(41)
        rows = await database.get_recent_history(41, b, limit=20)
        assert any(row["content"] == "Распознанный вопрос." for row in rows)
        assert p.generated.await_count == 1
    run(scenario())


def test_moderated_stale_inbound_never_creates_draft(pipeline, monkeypatch):
    p = pipeline
    drafts = AsyncMock(wraps=database.create_pending_draft)
    coach = p.modules["chat"].register_chat(
        p.dp,
        p.bot, object(), "offline", [99], types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")),
        lambda user: "Тест", lambda user: "Тест", database.add_chat_message,
        database.get_recent_history, drafts, database.rotate_conversation,
        database.get_or_create_conversation_id, database.is_active_conversation,
        direct_chat=False, admit_user_message=database.admit_user_message,
    )
    async def scenario():
        await p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state)
        await coach(message(message_id=101), p.state)
        assert drafts.await_count == 0
        await coach(message(message_id=103), p.state)
        assert drafts.await_count == 1
    run(scenario())


def test_private_marker_contract_and_distinct_user_locks():
    assert private_message_marker(message(message_id=101)) == (41, 101)
    for candidate in (message(message_id=None), message(message_id=0),
                      message(chat_type="group", chat_id=900), message(chat_id=42)):
        assert private_message_marker(candidate) is None
    assert admission_lock(41) is not admission_lock(42)


def test_clean_previous_session_schema_upgrades_without_backfill(monkeypatch, tmp_path):
    path = tmp_path / "previous.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE active_chat_sessions(user_id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL)")
        conn.execute("INSERT INTO active_chat_sessions VALUES (41, 'existing')")
    monkeypatch.setattr(database, "DB_PATH", str(path))
    run(database.init_db())
    run(database.init_db())
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT conversation_id, cutoff_chat_id, cutoff_message_id FROM active_chat_sessions").fetchone() == ("existing", None, None)
        assert [row[1] for row in conn.execute("PRAGMA table_info(active_chat_sessions)")] == [
            "user_id", "conversation_id", "cutoff_chat_id", "cutoff_message_id"
        ]


def test_two_normal_messages_same_conversation_and_different_user_not_blocked(db):
    async def scenario():
        async with admission_lock(41):
            other = await asyncio.wait_for(database.admit_user_message(42, "B", "", "other", 42, 101), 3)
            assert other[0] and other[1] is None
        first = await database.admit_user_message(41, "A", "", "first", 41, 101)
        second = await database.admit_user_message(41, "A", "", "second", 41, 102)
        assert first[0] == second[0] and first[1] is second[1] is None
        assert [x["content"] for x in await database.get_recent_history(41, first[0], limit=20)] == ["first", "second"]
        assert [x["content"] for x in await database.get_recent_history(42, other[0], limit=20)] == ["other"]
    run(scenario())


def test_competing_handler_tasks_use_cutoff_not_lock_arrival(pipeline):
    p = pipeline
    async def scenario():
        async with admission_lock(41):
            reset = asyncio.create_task(p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state))
            old = asyncio.create_task(p.coach(message(message_id=101, text="old"), p.state))
            await asyncio.sleep(0)
        await asyncio.gather(reset, old)
        b = await database.get_or_create_conversation_id(41)
        assert await database.get_recent_history(41, b, limit=20) == []
        async with admission_lock(41):
            newer = asyncio.create_task(p.coach(message(message_id=103, text="new"), p.state))
            await asyncio.sleep(0)
        await newer
        assert [x["content"] for x in await database.get_recent_history(41, b, limit=20) if x["role"] == "user"] == ["new"]
    run(scenario())


@pytest.mark.parametrize("kind", ["group", "supergroup", "channel"])
def test_nonprivate_text_and_voice_never_create_session(pipeline, kind):
    p = pipeline
    async def scenario():
        incoming = message(chat_type=kind, chat_id=900, voice=True)
        await p.coach(message(chat_type=kind, chat_id=900), p.state)
        await p.handlers["handle_voice_note"](incoming, p.state)
        await p.handlers["cmd_new"](message(text="/new", chat_type=kind, chat_id=900), p.state)
        assert p.generated.await_count == 0
        assert p.bot.get_file.await_count == 0
        assert p.state.get_state.await_count == 0
        assert p.state.set_state.await_count == 0
        with sqlite3.connect(p.db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM active_chat_sessions").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM pending_drafts").fetchone()[0] == 0
    run(scenario())


def test_nonprivate_onboarding_and_quiz_do_not_mutate_fsm(monkeypatch):
    modules = _load_handlers(monkeypatch)
    handlers = {}
    class Registrar:
        def __call__(self, *_args):
            def capture(fn): handlers[fn.__name__] = fn; return fn
            return capture
    dp = types.SimpleNamespace(message=Registrar(), callback_query=Registrar())
    bot = types.SimpleNamespace(send_message=AsyncMock(), send_chat_action=AsyncMock())
    state_cls = types.SimpleNamespace(AI_CHAT=object(), CALC=object(), QUESTION_STEP=object())
    modules["start"].register_start(dp, lambda *_: "Тест", lambda *_: object())
    modules["quiz"].register_quiz(dp, bot, state_cls, [], lambda *_: "Тест", lambda *_: object())
    modules["callbacks"].register_callbacks(dp, bot, state_cls)
    state = types.SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock(),
                                  get_state=AsyncMock(), get_data=AsyncMock())
    group = message(chat_type="group", chat_id=900, text="/start")
    callback = types.SimpleNamespace(
        from_user=types.SimpleNamespace(id=41), answer=AsyncMock(),
        message=types.SimpleNamespace(chat=group.chat, delete=AsyncMock(), answer=AsyncMock()),
    )
    async def scenario():
        await handlers["cmd_start"](group, state)
        for name in ("start_quiz", "process_answer", "show_result", "menu_learn_more_handler", "enter_chat"):
            if name == "menu_learn_more_handler":
                await handlers[name](callback, state)
            else:
                await handlers[name](callback, state)
        assert state.clear.await_count == state.update_data.await_count == state.set_state.await_count == 0
        assert bot.send_message.await_count == bot.send_chat_action.await_count == 0
        assert group.answer.await_count == 0
    run(scenario())


def test_handler_order_101_reset_102_then_103(pipeline):
    p = pipeline
    async def scenario():
        await p.coach(message(message_id=101, text="old"), p.state)
        a = await database.get_or_create_conversation_id(41)
        await p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state)
        b = await database.get_or_create_conversation_id(41)
        await p.coach(message(message_id=103, text="new"), p.state)
        assert a != b
        assert await database.get_recent_history(41, a, limit=20) == []
        assert [row["content"] for row in await database.get_recent_history(41, b, limit=20)
                if row["role"] == "user"] == ["new"]
    run(scenario())


def test_post_reset_103_overtakes_102_and_is_deleted_from_old_session(pipeline, monkeypatch):
    """Document the remaining turn-loss race through the actual handler path."""
    p = pipeline
    generating, release = asyncio.Event(), asyncio.Event()
    async def held(*_args):
        generating.set()
        await release.wait()
        return "offline answer"
    monkeypatch.setattr(p.modules["chat"], "generate_candidate", held)
    async def scenario():
        newer_message = message(message_id=103, text="post-reset turn")
        newer_task = asyncio.create_task(p.coach(newer_message, p.state))
        await asyncio.wait_for(generating.wait(), timeout=3)
        a = await database.get_or_create_conversation_id(41)
        assert [row["content"] for row in await database.get_recent_history(41, a, limit=20)
                if row["role"] == "user"] == ["post-reset turn"]
        await p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state)
        b = await database.get_or_create_conversation_id(41)
        assert b != a
        release.set()
        await newer_task
        assert await database.get_recent_history(41, b, limit=20) == []
        assert await database.get_conversation_history_with_ids(41, b) == []
        assert newer_message.answer.await_count == 1  # Acknowledged despite later deletion.
        assert p.bot.send_message.await_count == 0  # Existing stale generation check.
    run(scenario())


def test_reset_102_waits_on_lock_then_103_admits_into_new_session(pipeline):
    p = pipeline
    async def scenario():
        async with admission_lock(41):
            reset_task = asyncio.create_task(
                p.handlers["cmd_new"](message(message_id=102, text="/new"), p.state)
            )
            await asyncio.sleep(0)
            newer_task = asyncio.create_task(p.coach(message(message_id=103, text="new"), p.state))
            await asyncio.sleep(0)
        await asyncio.gather(reset_task, newer_task)
        b = await database.get_or_create_conversation_id(41)
        assert [row["content"] for row in await database.get_recent_history(41, b, limit=20)
                if row["role"] == "user"] == ["new"]
    run(scenario())


def test_handler_rapid_new_104_then_delayed_102_cannot_rotate_back(pipeline):
    p = pipeline
    async def scenario():
        newer = message(message_id=104, text="/new")
        stale = message(message_id=102, text="/new")
        await p.handlers["cmd_new"](newer, p.state)
        current = await database.get_or_create_conversation_id(41)
        await p.handlers["cmd_new"](stale, p.state)
        assert await database.get_or_create_conversation_id(41) == current
        assert newer.answer.await_count == 1
        assert stale.answer.await_count == 0
        assert await database.admit_user_message(41, "A", "", "later", 41, 105) == (current, None)
    run(scenario())


def test_admin_voice_in_group_keeps_existing_control_path(pipeline, monkeypatch):
    p = pipeline
    response = types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="Admin answer"))])
    create = AsyncMock(return_value=response)
    admin_client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
    send_long = AsyncMock()
    monkeypatch.setattr(p.modules["voice"], "send_long_message", send_long)
    p.modules["voice"].register_voice(
        p.dp, p.bot, admin_client, "offline", [41],
        AsyncMock(return_value="Admin request"), p.coach,
        types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")),
        database.get_coaching_resume_conversation_id,
    )
    async def scenario():
        await p.handlers["handle_voice_note"](message(chat_type="group", chat_id=900, voice=True), p.state)
        assert create.await_count == 1
        assert send_long.await_count == 1
        assert p.generated.await_count == 0
        with sqlite3.connect(p.db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM active_chat_sessions").fetchone()[0] == 0
    run(scenario())


@pytest.mark.parametrize("user_text", [
    "Что мне делать?",
    "Мне очень тяжело на новой работе.",
    "Я всё чаще думаю, что потеряла себя.",
    "Не знаю.",
])
def test_acknowledgement_does_not_assume_question_for_text(pipeline, user_text):
    p = pipeline
    incoming = message(text=user_text)
    run(p.coach(incoming, p.state))
    incoming.answer.assert_awaited_once_with("Спасибо, Тест! Я скоро напишу тебе... 🌺")
    assert p.generated.await_count == 1


def test_statement_voice_transcript_gets_neutral_acknowledgement(pipeline):
    p = pipeline
    p.transcribe.return_value = "Мне очень тяжело на новой работе."
    incoming = message(voice=True, text=None)
    run(p.handlers["handle_voice_note"](incoming, p.state))
    incoming.answer.assert_awaited_once_with("Спасибо, Тест! Я скоро напишу тебе... 🌺")
    assert p.transcribe.await_count == p.generated.await_count == 1
    assert incoming.text == "Мне очень тяжело на новой работе."


def test_moderated_statement_acknowledgement_and_draft_heading_are_neutral(pipeline):
    p = pipeline
    coach = p.modules["chat"].register_chat(
        p.dp, p.bot, object(), "offline", [99],
        types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")),
        lambda user: "Тест", lambda user: "Тест",
        database.add_chat_message, database.get_recent_history,
        database.create_pending_draft, database.rotate_conversation,
        database.get_or_create_conversation_id, database.is_active_conversation,
        direct_chat=False, admit_user_message=database.admit_user_message,
    )
    incoming = message(text="Я всё чаще думаю, что потеряла себя.")
    run(coach(incoming, p.state))
    incoming.answer.assert_awaited_once_with("Спасибо, Тест! Я скоро напишу тебе... 🌺")
    assert p.generated.await_count == 1
    admin_text = p.bot.send_message.await_args.args[1]
    assert admin_text.startswith("📩 Новое сообщение от пользователя: ")
    assert "Новый вопрос" not in admin_text


def test_explicit_truncation_retries_once_before_direct_send_and_history(pipeline, caplog):
    p = pipeline
    p.generated.side_effect = [ExplicitTruncationError(), "FINAL_ACCEPTED"]
    incoming = message()
    with caplog.at_level("INFO"):
        run(p.coach(incoming, p.state))
    assert p.generated.await_count == 2
    first, second = p.generated.await_args_list
    assert first.args == second.args and first.kwargs == second.kwargs
    p.bot.send_message.assert_awaited_once_with(41, "FINAL_ACCEPTED")
    cid = run(database.get_or_create_conversation_id(41))
    assert run(database.get_recent_history(41, cid)) == [
        {"role": "user", "content": "Вопрос."},
        {"role": "assistant", "content": "FINAL_ACCEPTED"},
    ]
    assert "retry attempt=2 reason=explicit_truncation" in caplog.text
    assert "FINAL_ACCEPTED" not in caplog.text


@pytest.mark.parametrize("second", [
    ExplicitTruncationError(),
    RuntimeError("PRIVATE_PROVIDER_ERROR"),
])
def test_retry_failure_uses_existing_generic_path_without_direct_output(pipeline, second, caplog):
    p = pipeline
    p.generated.side_effect = [ExplicitTruncationError(), second]
    incoming = message()
    with caplog.at_level("INFO"):
        run(p.coach(incoming, p.state))
    assert p.generated.await_count == 2
    assert p.generated.await_args_list[0].args == p.generated.await_args_list[1].args
    p.bot.send_message.assert_not_awaited()
    cid = run(database.get_or_create_conversation_id(41))
    assert run(database.get_recent_history(41, cid)) == [{"role": "user", "content": "Вопрос."}]
    assert incoming.answer.await_count == 2  # Existing acknowledgement, then generic failure.
    assert "Произошла ошибка связи." in incoming.answer.await_args.args[0]
    assert "PRIVATE_PROVIDER_ERROR" not in caplog.text


def test_non_truncation_provider_exception_is_not_retried(pipeline):
    p = pipeline
    p.generated.side_effect = RuntimeError("PRIVATE_PROVIDER_ERROR")
    incoming = message()
    run(p.coach(incoming, p.state))
    assert p.generated.await_count == 1
    p.bot.send_message.assert_not_awaited()
    assert "Произошла ошибка связи." in incoming.answer.await_args.args[0]


def test_normal_direct_response_makes_one_call_and_one_history_entry(pipeline):
    p = pipeline
    run(p.coach(message(), p.state))
    assert p.generated.await_count == 1
    p.bot.send_message.assert_awaited_once_with(41, "Ответ.")
    cid = run(database.get_or_create_conversation_id(41))
    assert run(database.get_recent_history(41, cid)) == [
        {"role": "user", "content": "Вопрос."},
        {"role": "assistant", "content": "Ответ."},
    ]


def test_moderated_retry_stores_only_final_draft(pipeline):
    p = pipeline
    p.generated.side_effect = [ExplicitTruncationError(), "FINAL_DRAFT"]
    drafts = AsyncMock(wraps=database.create_pending_draft)
    coach = p.modules["chat"].register_chat(
        p.dp, p.bot, object(), "offline", [99],
        types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")),
        lambda user: "Тест", lambda user: "Тест",
        database.add_chat_message, database.get_recent_history, drafts,
        database.rotate_conversation, database.get_or_create_conversation_id,
        database.is_active_conversation, direct_chat=False,
        get_conversation_history_with_ids=database.get_conversation_history_with_ids,
        admit_user_message=database.admit_user_message,
    )
    run(coach(message(), p.state))
    assert p.generated.await_count == 2
    assert p.generated.await_args_list[0].args == p.generated.await_args_list[1].args
    drafts.assert_awaited_once()
    assert drafts.await_args.args[3] == "FINAL_DRAFT"
    with sqlite3.connect(p.db) as conn:
        rows = conn.execute("SELECT ai_draft FROM pending_drafts").fetchall()
    assert rows == [("FINAL_DRAFT",)]
    assert p.bot.send_message.await_count == 1  # Admin draft only; no user delivery.
    assert p.bot.send_message.await_args.args[0] == 99
    assert "FINAL_DRAFT" in p.bot.send_message.await_args.args[1]


def test_moderated_double_truncation_creates_no_draft(pipeline):
    p = pipeline
    p.generated.side_effect = [ExplicitTruncationError(), ExplicitTruncationError()]
    drafts = AsyncMock(wraps=database.create_pending_draft)
    coach = p.modules["chat"].register_chat(
        p.dp, p.bot, object(), "offline", [99],
        types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")),
        lambda user: "Тест", lambda user: "Тест",
        database.add_chat_message, database.get_recent_history, drafts,
        database.rotate_conversation, database.get_or_create_conversation_id,
        database.is_active_conversation, direct_chat=False,
        get_conversation_history_with_ids=database.get_conversation_history_with_ids,
        admit_user_message=database.admit_user_message,
    )
    incoming = message()
    run(coach(incoming, p.state))
    assert p.generated.await_count == 2
    drafts.assert_not_awaited()
    p.bot.send_message.assert_not_awaited()
    assert "Произошла ошибка связи." in incoming.answer.await_args.args[0]



def test_provider_length_metadata_retries_identical_request_before_direct_delivery(pipeline, monkeypatch, caplog):
    p = pipeline

    class FakeClient:
        def __init__(self):
            self.calls = []
            self.outputs = iter([
                types.SimpleNamespace(choices=[types.SimpleNamespace(
                    finish_reason="length",
                    message=types.SimpleNamespace(content="PRIVATE_PARTIAL"),
                )]),
                types.SimpleNamespace(choices=[types.SimpleNamespace(
                    finish_reason="stop",
                    message=types.SimpleNamespace(content="FINAL_ONLY"),
                )]),
            ])
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return next(self.outputs)

    client = FakeClient()
    monkeypatch.setattr(p.modules["chat"], "generate_candidate", real_generate_candidate)
    coach = p.modules["chat"].register_chat(
        p.dp, p.bot, client, "fake-model", [],
        types.SimpleNamespace(AI_CHAT=types.SimpleNamespace(state="chat")),
        lambda user: "Тест", lambda user: "Тест",
        database.add_chat_message, database.get_recent_history, database.create_pending_draft,
        database.rotate_conversation, database.get_or_create_conversation_id,
        database.is_active_conversation, direct_chat=True,
        get_conversation_history_with_ids=database.get_conversation_history_with_ids,
        admit_user_message=database.admit_user_message,
    )
    with caplog.at_level("INFO"):
        run(coach(message(), p.state))
    assert len(client.calls) == 2
    assert client.calls[0] == client.calls[1]
    assert client.calls[0]["max_tokens"] == 350
    p.bot.send_message.assert_awaited_once_with(41, "FINAL_ONLY")
    cid = run(database.get_or_create_conversation_id(41))
    assert run(database.get_recent_history(41, cid)) == [
        {"role": "user", "content": "Вопрос."},
        {"role": "assistant", "content": "FINAL_ONLY"},
    ]
    assert "PRIVATE_PARTIAL" not in caplog.text
