"""Offline durable text-resume integration tests; no network or model calls."""
import asyncio
import importlib.util
import io
import json
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


def run(coro):
    return asyncio.run(coro)


class MemoryStorageDouble:
    """Fresh instance has no states/data, matching bot.py's process-local MemoryStorage boundary."""

    def __init__(self):
        self.contexts = {}

    def context(self, user_id=41):
        return self.contexts.setdefault(user_id, FSMContextDouble())


class FSMContextDouble:
    def __init__(self):
        self.state = None
        self.data = {}

    async def get_state(self):
        return self.state

    async def set_state(self, value):
        self.state = value.state if hasattr(value, "state") else value

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **values):
        self.data.update(values)

    async def clear(self):
        self.state = None
        self.data = {}


class Expression:
    def __getattr__(self, _name):
        return self

    def startswith(self, *_args):
        return self

    def __invert__(self):
        return self

    def __and__(self, _other):
        return self

    def __or__(self, _other):
        return self


class Registrar:
    def __init__(self, functions):
        self.functions = functions

    def __call__(self, *_args):
        def capture(fn):
            self.functions[fn.__name__] = fn
            return fn
        return capture

    def register(self, fn, *_args):
        self.functions["coaching"] = fn


def load_handlers(monkeypatch):
    # Host test environment intentionally has no aiogram dependency. Only decorator/types
    # are doubled; the real handler functions and database code execute below.
    modules = {
        "aiogram": {"Bot": object, "Dispatcher": object, "F": Expression(),
                    "types": types.SimpleNamespace(Message=object, CallbackQuery=object)},
        "aiogram.filters": {"Command": lambda *_args: object()},
        "aiogram.fsm.context": {"FSMContext": object},
        "aiogram.types": {"InlineKeyboardButton": lambda **kw: kw,
                          "InlineKeyboardMarkup": lambda **kw: kw,
                          "FSInputFile": lambda *_args: object()},
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    loaded = {}
    for name in ("start", "quiz", "callbacks", "chat", "voice"):
        spec = importlib.util.spec_from_file_location(
            "resume_test_" + name, ROOT / "handlers" / (name + ".py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    loaded["quiz"].asyncio = types.SimpleNamespace(sleep=AsyncMock())
    return loaded


def incoming(message_id, text=None, *, user_id=41, voice=False, audio=False, chat_type="private"):
    user = types.SimpleNamespace(id=user_id, first_name="Тест", last_name=None, username=None)
    chat = types.SimpleNamespace(id=user_id if chat_type == "private" else 900,
                                 type=chat_type)
    return types.SimpleNamespace(
        from_user=user, chat=chat, message_id=message_id, text=text,
        voice=types.SimpleNamespace(file_id="offline") if voice else None,
        audio=types.SimpleNamespace(file_id="offline-audio") if audio else None,
        answer=AsyncMock(return_value=types.SimpleNamespace(message_id=message_id + 1)),
        answer_photo=AsyncMock(return_value=types.SimpleNamespace(message_id=message_id)),
        delete=AsyncMock(),
    )


def callback(message_id, data, *, user_id=41):
    msg = incoming(message_id, user_id=user_id)
    return types.SimpleNamespace(
        from_user=msg.from_user, message=msg, data=data, answer=AsyncMock()
    )


@pytest.fixture
def app(monkeypatch, tmp_path):
    db_path = tmp_path / "resume_only.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    run(database.init_db())
    loaded = load_handlers(monkeypatch)
    functions = {}
    dp = types.SimpleNamespace(message=Registrar(functions),
                               callback_query=Registrar(functions))
    sent = []
    async def send_message(*args, **kwargs):
        sent.append(("message", args, kwargs))
        return types.SimpleNamespace(message_id=100 + len(sent))
    async def send_photo(*args, **kwargs):
        sent.append(("photo", args, kwargs))
        return types.SimpleNamespace(message_id=100 + len(sent))
    bot = types.SimpleNamespace(
        send_message=AsyncMock(side_effect=send_message),
        send_photo=AsyncMock(side_effect=send_photo),
        send_chat_action=AsyncMock(),
        get_file=AsyncMock(return_value=types.SimpleNamespace(file_path="offline")),
        download_file=AsyncMock(return_value=io.BytesIO(b"offline-audio")),
    )
    states = types.SimpleNamespace(
        QUESTION_STEP=types.SimpleNamespace(state="question"),
        CALC=types.SimpleNamespace(state="calc"),
        AI_CHAT=types.SimpleNamespace(state="chat"),
        HOME=types.SimpleNamespace(state="home"),
    )
    questions = json.loads(
        (ROOT / "knowledge/method/shadow_light/v1.1/questions.json").read_text()
    )
    loaded["start"].register_start(
        dp, lambda user: user.first_name, lambda _: object(),
        state_cls=states, is_coaching_eligible=database.is_coaching_eligible,
    )
    loaded["quiz"].register_quiz(
        dp, bot, states, questions, lambda user: user.first_name, lambda _: object(),
        persist_completed_quiz_result=database.persist_completed_quiz_result,
    )
    loaded["callbacks"].register_callbacks(
        dp, bot, states, mark_coaching_eligible=database.mark_coaching_eligible,
        get_coaching_resume_conversation_id=database.get_coaching_resume_conversation_id,
    )
    generated = AsyncMock(return_value="Ответ.")
    monkeypatch.setattr(loaded["chat"], "generate_candidate", generated)
    coach = loaded["chat"].register_chat(
        dp, bot, object(), "offline", [], states,
        lambda user: user.first_name, lambda user: user.first_name,
        database.add_chat_message, database.get_recent_history,
        database.create_pending_draft, database.rotate_conversation,
        database.get_or_create_conversation_id, database.is_active_conversation,
        direct_chat=True,
        get_conversation_history_with_ids=database.get_conversation_history_with_ids,
        admit_user_message=database.admit_user_message,
        get_coaching_resume_conversation_id=database.get_coaching_resume_conversation_id,
        get_coaching_quiz_result=database.get_coaching_quiz_result,
    )
    transcribe = AsyncMock(return_value="Распознанный текст.")
    loaded["voice"].register_voice(
        dp, bot, object(), "offline", [], transcribe, coach,
        states, database.get_coaching_resume_conversation_id,
    )
    return types.SimpleNamespace(
        db_path=db_path, functions=functions, bot=bot, states=states,
        generated=generated, transcribe=transcribe, sent=sent,
        chat_module=loaded["chat"], quiz_module=loaded["quiz"],
        voice_module=loaded["voice"],
    )


async def complete_normal_path(app, state):
    f = app.functions
    await f["cmd_start"](incoming(100, "/start"), state)
    await f["start_quiz"](callback(100, "start_quiz"), state)
    for index in range(3):
        await f["process_answer"](callback(101 + index, "q_ans_0"), state)
    assert await state.get_state() == app.states.CALC.state
    await f["show_result"](callback(104, "show_result"), state)
    assert (await state.get_data())["archetype"] == "Тень"
    await f["enter_chat"](callback(106, "open_ai_chat"), state)
    assert await state.get_state() == app.states.AI_CHAT.state
    await f["coaching"](incoming(106, "Первый разговор."), state)
    cid = await database.get_or_create_conversation_id(41)
    assert await database.get_recent_history(41, cid) == [
        {"role": "user", "content": "Первый разговор."},
        {"role": "assistant", "content": "Ответ."},
    ]
    return cid


def test_legitimate_entry_and_first_returning_text_processed_once(app, monkeypatch):
    async def scenario():
        before = MemoryStorageDouble().context()
        cid = await complete_normal_path(app, before)
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT coaching_eligible, test_result FROM users WHERE user_id=41"
            ).fetchone() == (1, "Тень")
            assert conn.execute(
                "SELECT COUNT(*) FROM active_chat_sessions WHERE user_id=41"
            ).fetchone()[0] == 1

        observed_archetypes = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (observed_archetypes.append(kw["archetype"]), original(**kw))[1],
        )
        restarted = MemoryStorageDouble().context()
        returning = incoming(107, "Продолжаю после перезапуска.")
        before_calls = app.generated.await_count
        await app.functions["coaching"](returning, restarted)
        assert await restarted.get_state() == app.states.AI_CHAT.state
        assert app.generated.await_count == before_calls + 1
        assert returning.answer.await_count == 1
        assert observed_archetypes == ["Тень"]
        assert await database.get_coaching_resume_conversation_id(41) == cid
        assert await database.get_recent_history(41, cid) == [
            {"role": "user", "content": "Первый разговор."},
            {"role": "assistant", "content": "Ответ."},
            {"role": "user", "content": "Продолжаю после перезапуска."},
            {"role": "assistant", "content": "Ответ."},
        ]
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM active_chat_sessions WHERE user_id=41"
            ).fetchone()[0] == 1
    run(scenario())

def test_case_b_new_user_with_fresh_memory_does_not_enter_coaching(app):
    async def scenario():
        state = MemoryStorageDouble().context(user_id=42)
        await app.functions["coaching"](
            incoming(101, "Первое сообщение.", user_id=42), state
        )
        assert app.generated.await_count == 0
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM active_chat_sessions WHERE user_id=42"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE user_id=42"
            ).fetchone()[0] == 0
    run(scenario())


def test_case_c_history_and_user_row_do_not_prove_completed_onboarding(app):
    async def scenario():
        await database.register_user(42, "Legacy", "")
        cid, reason = await database.admit_user_message(
            42, "Legacy", "", "Legacy user turn", 42, 101
        )
        assert cid and reason is None
        assert await database.add_chat_message(
            42, "Legacy", "", "assistant", "Legacy reply", cid
        )
        assert await database.get_user_profile(42) is not None
        assert await database.get_recent_history(42, cid)
        state = MemoryStorageDouble().context(user_id=42)
        await app.functions["coaching"](incoming(102, "Old row is not proof.", user_id=42), state)
        assert app.generated.await_count == 0
        assert len(await database.get_recent_history(42, cid)) == 2
        with sqlite3.connect(app.db_path) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            assert "coaching_eligible" in columns
            assert "quiz_result_verified" in columns
            assert conn.execute(
                "SELECT coaching_eligible FROM users WHERE user_id=42"
            ).fetchone()[0] == 0
    run(scenario())


def test_after_new_current_id_cutoff_and_eligibility_survive_fresh_memory(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        old_id = await complete_normal_path(app, state)
        await app.functions["cmd_new"](incoming(107, "/new"), state)
        new_id = await database.get_or_create_conversation_id(41)
        assert new_id != old_id
        assert await state.get_state() == app.states.AI_CHAT.state
        assert (await state.get_data())["archetype"] == "Тень"
        assert await database.get_recent_history(41, new_id) == []
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT cutoff_chat_id, cutoff_message_id FROM active_chat_sessions WHERE user_id=41"
            ).fetchone() == (41, 107)
        restarted = MemoryStorageDouble().context()
        await app.functions["coaching"](incoming(108, "После /new и перезапуска."), restarted)
        assert await database.get_or_create_conversation_id(41) == new_id
        assert await database.get_recent_history(41, new_id) == [
            {"role": "user", "content": "После /new и перезапуска."},
            {"role": "assistant", "content": "Ответ."},
        ]
        assert await database.get_conversation_history_with_ids(41, old_id) == []
        assert app.generated.await_count == 2
        assert await database.get_coaching_resume_conversation_id(41) == new_id
        assert await database.get_coaching_quiz_result(41) == "Тень"
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT coaching_eligible FROM users WHERE user_id=41"
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT cutoff_chat_id, cutoff_message_id FROM active_chat_sessions WHERE user_id=41"
            ).fetchone() == (41, 107)
    run(scenario())


def test_returning_voice_recovers_before_download_and_processes_same_message(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        cid = await complete_normal_path(app, state)
        restarted = MemoryStorageDouble().context()
        order = []
        async def get_file(*args, **kwargs):
            assert await restarted.get_state() == app.states.AI_CHAT.state
            order.append("get_file")
            return types.SimpleNamespace(file_path="offline")

        async def download(*args, **kwargs):
            order.append("download")
            return io.BytesIO(b"offline-audio")

        async def transcribe(*args, **kwargs):
            order.append("transcribe")
            return "Распознанный текст."

        # The fixture registered the real DB lookup. The state assertion at
        # get_file proves restoration preceded any expensive file work.
        app.bot.get_file.side_effect = get_file
        app.bot.download_file.side_effect = download
        app.transcribe.side_effect = transcribe
        before = app.generated.await_count
        voice = incoming(107, voice=True)
        await app.functions["handle_voice_note"](voice, restarted)
        assert order == ["get_file", "download", "transcribe"]
        app.bot.get_file.assert_awaited_once()
        app.bot.download_file.assert_awaited_once()
        app.transcribe.assert_awaited_once_with(b"offline-audio")
        assert voice.text == "Распознанный текст."
        assert app.generated.await_count == before + 1
        assert voice.answer.await_count == 1
        assert await database.get_coaching_resume_conversation_id(41) == cid
        assert await database.get_recent_history(41, cid) == [
            {"role": "user", "content": "Первый разговор."},
            {"role": "assistant", "content": "Ответ."},
            {"role": "user", "content": "Распознанный текст."},
            {"role": "assistant", "content": "Ответ."},
        ]
    run(scenario())


@pytest.mark.parametrize("evidence", ["user", "session", "history"])
def test_unmarked_legacy_evidence_never_recovers(app, evidence):
    async def scenario():
        user_id = 48
        if evidence in {"user", "history"}:
            await database.register_user(user_id, "Legacy", "")
        if evidence in {"session", "history"}:
            cid, reason = await database.admit_user_message(
                user_id, "Legacy", "", "old", user_id, 100
            )
            assert cid and reason is None
            if evidence == "history":
                await database.add_chat_message(
                    user_id, "Legacy", "", "assistant", "old answer", cid
                )
        state = MemoryStorageDouble().context(user_id)
        incoming_text = incoming(101, "New text.", user_id=user_id)
        await app.functions["coaching"](incoming_text, state)
        assert await state.get_state() is None
        assert app.generated.await_count == 0
        assert incoming_text.answer.await_count == 0
        assert await database.get_coaching_resume_conversation_id(user_id) is None
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE user_id=? AND content='New text.'",
                (user_id,),
            ).fetchone()[0] == 0
    run(scenario())


def test_stale_callback_and_unfinished_quiz_do_not_write_proof(app):
    async def scenario():
        for user_id in (47, 48):
            state = MemoryStorageDouble().context(user_id)
            if user_id == 48:
                await app.functions["cmd_start"](incoming(10, "/start", user_id=user_id), state)
                await app.functions["start_quiz"](callback(10, "start_quiz", user_id=user_id), state)
                assert await state.get_state() == app.states.QUESTION_STEP.state
            await app.functions["enter_chat"](
                callback(12, "open_ai_chat", user_id=user_id), state
            )
            # Preserve the pre-existing volatile callback behavior, but it is
            # not evidence for future restart recovery.
            assert await state.get_state() != app.states.AI_CHAT.state
            assert await database.get_coaching_resume_conversation_id(user_id) is None
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM users WHERE user_id IN (47,48)"
            ).fetchone()[0] == 0
    run(scenario())


def test_existing_ai_chat_path_does_not_need_recovery_lookup(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await complete_normal_path(app, state)
        app.generated.reset_mock()
        original = app.functions["coaching"]
        # Existing state routes directly through normal admission.
        await original(incoming(107, "Обычный следующий ход."), state)
        assert app.generated.await_count == 1
        cid = await database.get_coaching_resume_conversation_id(41)
        assert len(await database.get_recent_history(41, cid)) == 4
    run(scenario())


def test_group_message_cannot_restore_eligible_user(app):
    async def scenario():
        await complete_normal_path(app, MemoryStorageDouble().context())
        state = MemoryStorageDouble().context()
        before = app.generated.await_count
        group = incoming(107, "Групповой текст.", chat_type="group")
        await app.functions["coaching"](group, state)
        assert await state.get_state() is None
        assert app.generated.await_count == before
        assert group.answer.await_count == 0
    run(scenario())


def test_empty_legacy_quiz_field_is_not_restored_as_archetype(app, monkeypatch):
    async def scenario():
        await complete_normal_path(app, MemoryStorageDouble().context())
        with sqlite3.connect(app.db_path) as conn:
            conn.execute("UPDATE users SET test_result='' WHERE user_id=41")
        archetypes = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (archetypes.append(kw["archetype"]), original(**kw))[1],
        )
        await app.functions["coaching"](
            incoming(107, "Продолжение."), MemoryStorageDouble().context()
        )
        assert archetypes == [None]
        assert "Полутень" not in str(archetypes)
    run(scenario())


def test_moderated_resume_uses_existing_pending_draft_path(app):
    async def scenario():
        await complete_normal_path(app, MemoryStorageDouble().context())
        funcs = {}
        dp = types.SimpleNamespace(message=Registrar(funcs))
        # Same real handler module with moderation enabled; all ports stay offline.
        app.chat_module.register_chat(
            dp, app.bot, object(), "offline", [99], app.states,
            lambda user: user.first_name, lambda user: user.first_name,
            database.add_chat_message, database.get_recent_history,
            database.create_pending_draft, database.rotate_conversation,
            database.get_or_create_conversation_id, database.is_active_conversation,
            direct_chat=False,
            get_conversation_history_with_ids=database.get_conversation_history_with_ids,
            admit_user_message=database.admit_user_message,
            get_coaching_resume_conversation_id=database.get_coaching_resume_conversation_id,
            get_coaching_quiz_result=database.get_coaching_quiz_result,
        )
        app.generated.reset_mock()
        current = await database.get_coaching_resume_conversation_id(41)
        text = incoming(107, "Модерируемое продолжение.")
        await funcs["coaching"](text, MemoryStorageDouble().context())
        assert app.generated.await_count == 1
        with sqlite3.connect(app.db_path) as conn:
            rows = conn.execute(
                "SELECT conversation_id, status FROM pending_drafts WHERE user_id=41"
            ).fetchall()
            assert rows == [(current, "PENDING")]
            assert conn.execute(
                "SELECT role, content FROM chat_messages WHERE user_id=41 AND conversation_id=? "
                "ORDER BY id DESC LIMIT 1", (current,)
            ).fetchone() == ("user", "Модерируемое продолжение.")
        assert app.bot.send_message.await_args_list[-1].args[0] == 99
        assert "(Тень)" in app.bot.send_message.await_args_list[-1].args[1]
    run(scenario())


def test_schema_upgrade_keeps_legacy_users_ineligible(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE users (user_id INTEGER PRIMARY KEY, full_name TEXT, "
            "username TEXT, subscription_status TEXT, test_result TEXT, "
            "answers TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute("INSERT INTO users (user_id, test_result) VALUES (7, 'Свет')")
    monkeypatch.setattr(database, "DB_PATH", str(path))
    run(database.init_db())
    run(database.init_db())
    with sqlite3.connect(path) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(users)")}
        assert "coaching_eligible" in columns
        assert columns["coaching_eligible"][4] == "0"
        assert columns["quiz_result_verified"][4] == "0"
        assert conn.execute(
            "SELECT coaching_eligible FROM users WHERE user_id=7"
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT test_result, quiz_result_verified FROM users WHERE user_id=7"
        ).fetchone() == ("Свет", 0)
        conn.execute("INSERT INTO users (user_id) VALUES (8)")
        assert conn.execute(
            "SELECT coaching_eligible, quiz_result_verified FROM users WHERE user_id=8"
        ).fetchone() == (0, 0)
    assert run(database.get_coaching_quiz_result(7)) is None


def test_new_does_not_grant_unmarked_user_resume(app):
    async def scenario():
        state = MemoryStorageDouble().context(user_id=49)
        await app.functions["cmd_new"](incoming(101, "/new", user_id=49), state)
        assert await state.get_state() == app.states.AI_CHAT.state
        assert await database.get_coaching_resume_conversation_id(49) is None
        restarted = MemoryStorageDouble().context(user_id=49)
        await app.functions["coaching"](incoming(102, "После /new.", user_id=49), restarted)
        assert app.generated.await_count == 0
        assert await restarted.get_state() is None
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE user_id=49"
            ).fetchone()[0] == 0
    run(scenario())


def test_start_home_allows_existing_recovery_without_button(app):
    async def scenario():
        cid = await complete_normal_path(app, MemoryStorageDouble().context())
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(107, "/start"), state)
        assert await state.get_state() == app.states.HOME.state
        assert (await state.get_data())["home_message_id"] == 108
        before = app.generated.await_count
        await app.functions["coaching"](incoming(109, "Продолжаю разговор."), state)
        assert app.generated.await_count == before + 1
        assert await state.get_state() == app.states.AI_CHAT.state
        assert await database.get_coaching_resume_conversation_id(41) == cid
    run(scenario())


@pytest.mark.parametrize(
    ("choices", "score", "result"),
    [
        ((2, 2, 0), 0, "Свет"),
        ((2, 2, 1), 1, "Полутень"),
        ((2, 2, 2), 2, "Полутень"),
        ((1, 1, 1), 3, "Полутень"),
        ((0, 0, 0), 4, "Тень"),
        ((0, 0, 1), 5, "Тень"),
        ((0, 0, 2), 6, "Тень"),
    ],
)
def test_completed_quiz_scores_persist_and_recover_context(
    app, monkeypatch, choices, score, result
):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        for index, choice in enumerate(choices, 101):
            await app.functions["process_answer"](
                callback(index, f"q_ans_{choice}"), state
            )
        assert await state.get_state() == app.states.CALC.state
        assert (await state.get_data())["total_score"] == score
        assert await database.get_coaching_quiz_result(41) is None
        await app.functions["show_result"](callback(104, "show_result"), state)
        assert (await state.get_data())["archetype"] == result
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone() == (result, 1, 0)
        await app.functions["enter_chat"](callback(106, "open_ai_chat"), state)
        cid = await database.get_coaching_resume_conversation_id(41)
        assert cid
        assert await database.get_coaching_quiz_result(41) == result
        contexts = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (contexts.append(kw["archetype"]), original(**kw))[1],
        )
        await app.functions["coaching"](incoming(106, "Первый ход."), state)
        assert contexts == [result]
        restarted = MemoryStorageDouble().context()
        await app.functions["coaching"](incoming(107, "После перезапуска."), restarted)
        assert contexts == [result, result]
        assert await database.get_coaching_resume_conversation_id(41) == cid
        assert len(await database.get_recent_history(41, cid)) == 4
    run(scenario())


def test_incomplete_invalid_callback_and_malformed_score_persist_nothing(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        await app.functions["process_answer"](callback(101, "q_ans_99"), state)
        await app.functions["show_result"](callback(102, "show_result"), state)
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM users WHERE user_id=41"
            ).fetchone()[0] == 0
        for index in range(3):
            await app.functions["process_answer"](
                callback(101 + index, "q_ans_0"), state
            )
        assert await state.get_state() == app.states.CALC.state
        await state.update_data(total_score="4")
        await app.functions["show_result"](callback(106, "show_result"), state)
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM users WHERE user_id=41"
            ).fetchone()[0] == 0
        assert (await state.get_data()).get("archetype") is None
        for malformed in ("unknown", "", " ", ["Свет"]):
            with pytest.raises(ValueError):
                await database.persist_completed_quiz_result(41, malformed)
    run(scenario())


@pytest.mark.parametrize("stored", [None, "", "  ", "unknown", "Старый"])
def test_invalid_persisted_result_is_no_context_but_eligibility_survives(
    app, monkeypatch, stored
):
    async def scenario():
        await complete_normal_path(app, MemoryStorageDouble().context())
        cid = await database.get_coaching_resume_conversation_id(41)
        with sqlite3.connect(app.db_path) as conn:
            conn.execute(
                "UPDATE users SET test_result=?, quiz_result_verified=1 WHERE user_id=41",
                (stored,),
            )
        assert await database.get_coaching_quiz_result(41) is None
        contexts = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (contexts.append(kw["archetype"]), original(**kw))[1],
        )
        restarted = MemoryStorageDouble().context()
        await app.functions["coaching"](incoming(107, "Продолжение."), restarted)
        assert await restarted.get_state() == app.states.AI_CHAT.state
        assert contexts == [None]
        assert app.generated.await_count == 2
        assert await database.get_coaching_resume_conversation_id(41) == cid
        assert "Полутень" not in str(contexts)
    run(scenario())


def test_unverified_legacy_result_is_not_context_even_with_eligibility(
    app, monkeypatch
):
    async def scenario():
        await complete_normal_path(app, MemoryStorageDouble().context())
        with sqlite3.connect(app.db_path) as conn:
            conn.execute(
                "UPDATE users SET test_result='Свет', quiz_result_verified=0 WHERE user_id=41"
            )
        contexts = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (contexts.append(kw["archetype"]), original(**kw))[1],
        )
        await app.functions["coaching"](
            incoming(107, "Продолжение."), MemoryStorageDouble().context()
        )
        assert contexts == [None]
    run(scenario())


def test_result_without_eligibility_does_not_admit_returning_text(app):
    async def scenario():
        await database.persist_completed_quiz_result(42, "Свет")
        assert await database.get_coaching_quiz_result(42) is None
        state = MemoryStorageDouble().context(user_id=42)
        await app.functions["coaching"](
            incoming(101, "Не прошла вход.", user_id=42), state
        )
        assert await state.get_state() is None
        assert app.generated.await_count == 0
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT coaching_eligible, test_result, quiz_result_verified "
                "FROM users WHERE user_id=42"
            ).fetchone() == (0, "Свет", 1)
    run(scenario())


def test_db_result_wins_over_conflicting_fsm_result(app, monkeypatch):
    async def scenario():
        state = MemoryStorageDouble().context()
        await complete_normal_path(app, state)
        await state.update_data(archetype="Свет")
        contexts = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (contexts.append(kw["archetype"]), original(**kw))[1],
        )
        await app.functions["coaching"](incoming(107, "Следующий ход."), state)
        assert contexts == ["Тень"]
        assert await database.get_coaching_quiz_result(41) == "Тень"
    run(scenario())


def test_repeat_result_write_is_idempotent_and_does_not_grant_eligibility(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        for index in range(3):
            await app.functions["process_answer"](
                callback(101 + index, "q_ans_0"), state
            )
        with sqlite3.connect(app.db_path) as conn:
            conn.execute("CREATE TABLE result_write_count (n INTEGER)")
            conn.execute(
                "CREATE TRIGGER result_insert AFTER INSERT ON users "
                "BEGIN INSERT INTO result_write_count VALUES (1); END"
            )
            conn.execute(
                "CREATE TRIGGER result_update AFTER UPDATE OF test_result ON users "
                "BEGIN INSERT INTO result_write_count VALUES (1); END"
            )
        await app.functions["show_result"](callback(104, "show_result"), state)
        await app.functions["show_result"](callback(104, "show_result"), state)
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM result_write_count"
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone() == ("Тень", 1, 0)
    run(scenario())


def test_group_result_callback_cannot_persist_result(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        for index in range(3):
            await app.functions["process_answer"](
                callback(101 + index, "q_ans_0"), state
            )
        group = callback(104, "show_result")
        group.message.chat.type = "group"
        group.message.chat.id = 900
        await app.functions["show_result"](group, state)
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM users WHERE user_id=41"
            ).fetchone()[0] == 0
    run(scenario())


def test_generic_legacy_profile_update_clears_result_provenance(app):
    async def scenario():
        await complete_normal_path(app, MemoryStorageDouble().context())
        assert await database.get_coaching_quiz_result(41) == "Тень"
        await database.update_user_test_result(41, "legacy answers", "Свет")
        assert await database.get_coaching_quiz_result(41) is None
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone() == ("Свет", 0, 1)
    run(scenario())


def test_result_write_failure_prevents_new_result_ui_and_fsm_cache(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        for index in range(3):
            await app.functions["process_answer"](
                callback(101 + index, "q_ans_0"), state
            )
        functions = {}
        dp = types.SimpleNamespace(callback_query=Registrar(functions))
        questions = json.loads(
            (ROOT / "knowledge/method/shadow_light/v1.1/questions.json").read_text()
        )
        app.quiz_module.register_quiz(
            dp, app.bot, app.states, questions,
            lambda user: user.first_name, lambda _: object(),
            persist_completed_quiz_result=AsyncMock(side_effect=RuntimeError("offline DB failure")),
        )
        app.bot.send_photo.reset_mock()
        with pytest.raises(RuntimeError, match="offline DB failure"):
            await functions["show_result"](callback(104, "show_result"), state)
        assert (await state.get_data()).get("archetype") is None
        assert await state.get_state() == app.states.CALC.state
        app.bot.send_photo.assert_not_awaited()
        assert await database.get_coaching_quiz_result(41) is None
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM users WHERE user_id=41"
            ).fetchone()[0] == 0
    run(scenario())


def test_answer_buttons_are_bound_to_current_step_and_message(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        q1 = (await state.get_data())["last_question_message_id"]
        assert q1 == 101
        await app.functions["process_answer"](callback(q1, "q_ans_0"), state)
        after_q1 = await state.get_data()
        assert after_q1["current_q_idx"] == 1
        assert after_q1["total_score"] == 2
        assert len(after_q1["answers_list"]) == 1
        q2 = after_q1["last_question_message_id"]

        for payload in ("q_ans_0", "q_ans_2"):
            stale = callback(q1, payload)
            await app.functions["process_answer"](stale, state)
            stale.answer.assert_awaited_once()
            assert await state.get_data() == after_q1

        wrong_message = callback(q2 + 99, "q_ans_0")
        await app.functions["process_answer"](wrong_message, state)
        assert await state.get_data() == after_q1

        for payload in ("q_ans_99", "q_ans_bad", "q_ans_-1"):
            invalid = callback(q2, payload)
            await app.functions["process_answer"](invalid, state)
            assert await state.get_data() == after_q1

        await app.functions["process_answer"](callback(q2, "q_ans_1"), state)
        after_q2 = await state.get_data()
        assert after_q2["current_q_idx"] == 2
        assert after_q2["total_score"] == 3
        assert len(after_q2["answers_list"]) == 2
        q3 = after_q2["last_question_message_id"]
        await app.functions["process_answer"](callback(q2, "q_ans_0"), state)
        assert await state.get_data() == after_q2

        await app.functions["process_answer"](callback(q3, "q_ans_2"), state)
        final = await state.get_data()
        assert final["current_q_idx"] == 3
        assert final["total_score"] == 5
        assert len(final["answers_list"]) == 3
        assert await state.get_state() == app.states.CALC.state
        await app.functions["process_answer"](callback(q3, "q_ans_2"), state)
        assert await state.get_data() == final
        await app.functions["show_result"](
            callback(final["last_question_message_id"], "show_result"), state
        )
        assert await database.get_coaching_quiz_result(41) is None
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone() == ("Тень", 1, 0)
    run(scenario())


def test_old_welcome_button_cannot_restart_or_duplicate_quiz(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["cmd_start"](incoming(200, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        assert await state.get_state() is None
        assert (await state.get_data())["welcome_message_id"] == 200
        await app.functions["start_quiz"](callback(200, "start_quiz"), state)
        q1 = (await state.get_data())["last_question_message_id"]
        await app.functions["start_quiz"](callback(200, "start_quiz"), state)
        assert await state.get_state() == app.states.QUESTION_STEP.state
        assert (await state.get_data())["last_question_message_id"] == q1
        assert (await state.get_data())["current_q_idx"] == 0
    run(scenario())


def test_stale_result_button_in_new_completed_quiz_cannot_change_durable_fields(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        cid = await complete_normal_path(app, state)
        with sqlite3.connect(app.db_path) as conn:
            before = conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone()
        assert before == ("Тень", 1, 1)
        old_result_button = 104
        old_entry_button = 106

        # Exercise the callback guard against a second active quiz FSM directly.
        # /start no longer initiates a retake for an eligible user.
        await state.clear()
        await state.update_data(user_first_name="Тест", welcome_message_id=200)
        await app.functions["start_quiz"](callback(200, "start_quiz"), state)
        for choice in (2, 2, 0):
            mid = (await state.get_data())["last_question_message_id"]
            await app.functions["process_answer"](callback(mid, f"q_ans_{choice}"), state)
        new_result_button = (await state.get_data())["last_question_message_id"]
        assert new_result_button != old_result_button
        await app.functions["show_result"](
            callback(old_result_button, "show_result"), state
        )
        assert (await state.get_data())["last_question_message_id"] == new_result_button
        assert (await state.get_data())["archetype"] is None
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone() == before
        await app.functions["enter_chat"](
            callback(old_entry_button, "open_ai_chat"), state
        )
        assert await state.get_state() == app.states.CALC.state
        assert await database.get_coaching_resume_conversation_id(41) == cid
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone() == before

        await app.functions["show_result"](
            callback(new_result_button, "show_result"), state
        )
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone() == ("Свет", 1, 1)
        new_entry_button = (await state.get_data())["quiz_entry_message_id"]
        assert new_entry_button != old_entry_button
        await app.functions["enter_chat"](
            callback(old_entry_button, "open_ai_chat"), state
        )
        assert await state.get_state() == app.states.CALC.state
        await app.functions["enter_chat"](
            callback(new_entry_button, "open_ai_chat"), state
        )
        assert await state.get_state() == app.states.AI_CHAT.state
        assert await database.get_coaching_resume_conversation_id(41) == cid
    run(scenario())


def test_duplicate_result_and_entry_callbacks_have_no_second_effect(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        for index in range(3):
            await app.functions["process_answer"](
                callback(101 + index, "q_ans_0"), state
            )
        result_id = (await state.get_data())["last_question_message_id"]
        await app.functions["show_result"](callback(result_id, "show_result"), state)
        sent_after_result = len(app.sent)
        await app.functions["show_result"](callback(result_id, "show_result"), state)
        assert len(app.sent) == sent_after_result
        assert await state.get_state() == app.states.CALC.state
        entry_id = (await state.get_data())["quiz_entry_message_id"]
        await app.functions["enter_chat"](callback(entry_id, "open_ai_chat"), state)
        cid = await database.get_coaching_resume_conversation_id(41)
        repeated = callback(entry_id, "open_ai_chat")
        await app.functions["enter_chat"](repeated, state)
        assert repeated.message.answer.await_count == 0
        assert await state.get_state() == app.states.AI_CHAT.state
        assert await database.get_coaching_resume_conversation_id(41) == cid
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM active_chat_sessions WHERE user_id=41"
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT test_result, quiz_result_verified, coaching_eligible "
                "FROM users WHERE user_id=41"
            ).fetchone() == ("Тень", 1, 1)
    run(scenario())


def test_learn_more_replaces_entry_button_authority(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        for index in range(3):
            await app.functions["process_answer"](
                callback(101 + index, "q_ans_0"), state
            )
        await app.functions["show_result"](callback(104, "show_result"), state)
        old_entry_id = (await state.get_data())["quiz_entry_message_id"]
        await app.functions["menu_learn_more_handler"](
            callback(old_entry_id, "menu_learn_more"), state
        )
        new_entry_id = (await state.get_data())["quiz_entry_message_id"]
        assert new_entry_id != old_entry_id
        count = len(app.sent)
        await app.functions["menu_learn_more_handler"](
            callback(old_entry_id, "menu_learn_more"), state
        )
        assert len(app.sent) == count
        await app.functions["enter_chat"](
            callback(old_entry_id, "open_ai_chat"), state
        )
        assert await state.get_state() == app.states.CALC.state
        await app.functions["enter_chat"](
            callback(new_entry_id, "open_ai_chat"), state
        )
        assert await state.get_state() == app.states.AI_CHAT.state
        assert await database.get_coaching_resume_conversation_id(41)
    run(scenario())


def test_group_answer_button_cannot_mutate_quiz(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        before = await state.get_data()
        group = callback(before["last_question_message_id"], "q_ans_0")
        group.message.chat.type = "group"
        group.message.chat.id = 900
        await app.functions["process_answer"](group, state)
        assert await state.get_data() == before
        assert await state.get_state() == app.states.QUESTION_STEP.state
    run(scenario())


async def completed_quiz_without_text(app, state, choices=(0, 0, 0)):
    await app.functions["cmd_start"](incoming(100, "/start"), state)
    await app.functions["start_quiz"](callback(100, "start_quiz"), state)
    for choice in choices:
        mid = (await state.get_data())["last_question_message_id"]
        await app.functions["process_answer"](callback(mid, f"q_ans_{choice}"), state)
    result_mid = (await state.get_data())["last_question_message_id"]
    await app.functions["show_result"](callback(result_mid, "show_result"), state)
    entry_mid = (await state.get_data())["quiz_entry_message_id"]
    await app.functions["enter_chat"](callback(entry_mid, "open_ai_chat"), state)
    return await database.get_coaching_resume_conversation_id(41)


@pytest.mark.parametrize("media_type", ["voice", "audio"])
def test_fresh_memory_media_preflight_order_and_single_pipeline(app, media_type):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        state = MemoryStorageDouble().context()
        order = []
        original_lookup = database.get_coaching_resume_conversation_id

        async def lookup(user_id):
            order.append("eligibility")
            return await original_lookup(user_id)

        funcs = {}
        dp = types.SimpleNamespace(message=Registrar(funcs))
        app.voice_module.register_voice(
            dp, app.bot, object(), "offline", [], app.transcribe,
            app.functions["coaching"], app.states, lookup,
        )

        async def get_file(file_id):
            assert await state.get_state() == app.states.AI_CHAT.state
            order.append("get_file")
            return types.SimpleNamespace(file_path="offline")

        async def download(_path):
            order.append("download")
            return io.BytesIO(b"offline-audio")

        async def transcribe(_bytes):
            order.append("transcribe")
            return "Один голосовой ход."

        app.bot.get_file.side_effect = get_file
        app.bot.download_file.side_effect = download
        app.transcribe.side_effect = transcribe
        media = incoming(107, **{media_type: True})
        await funcs["handle_voice_note"](media, state)

        assert order == ["eligibility", "get_file", "download", "transcribe"]
        app.bot.get_file.assert_awaited_once()
        app.bot.download_file.assert_awaited_once()
        app.transcribe.assert_awaited_once_with(b"offline-audio")
        assert app.generated.await_count == 1
        assert media.answer.await_count == 1
        assert await database.get_coaching_resume_conversation_id(41) == cid
        assert await database.get_recent_history(41, cid) == [
            {"role": "user", "content": "Один голосовой ход."},
            {"role": "assistant", "content": "Ответ."},
        ]
    run(scenario())


def test_already_ai_chat_voice_uses_existing_path_without_recovery(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        cid = await completed_quiz_without_text(app, state)
        voice = incoming(107, voice=True)
        await app.functions["handle_voice_note"](voice, state)
        assert await state.get_state() == app.states.AI_CHAT.state
        assert app.bot.get_file.await_count == 1
        assert app.transcribe.await_count == 1
        assert app.generated.await_count == 1
        assert await database.get_recent_history(41, cid) == [
            {"role": "user", "content": "Распознанный текст."},
            {"role": "assistant", "content": "Ответ."},
        ]
    run(scenario())


@pytest.mark.parametrize("evidence", ["none", "user", "session", "history"])
def test_unmarked_fresh_voice_does_no_file_transcription_or_generation(app, evidence):
    async def scenario():
        user_id = 42
        if evidence in {"user", "history"}:
            await database.register_user(user_id, "Legacy", "")
        if evidence in {"session", "history"}:
            await database.admit_user_message(
                user_id, "Legacy", "", "old", user_id, 100
            )
        state = MemoryStorageDouble().context(user_id)
        voice = incoming(101, user_id=user_id, voice=True)
        await app.functions["handle_voice_note"](voice, state)
        assert await state.get_state() is None
        app.bot.get_file.assert_not_awaited()
        app.bot.download_file.assert_not_awaited()
        app.transcribe.assert_not_awaited()
        assert app.generated.await_count == 0
        assert voice.answer.await_count == 0
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE user_id=? AND content='Распознанный текст.'",
                (user_id,),
            ).fetchone()[0] == 0
    run(scenario())


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel", "private_mismatch"])
@pytest.mark.parametrize("media_type", ["voice", "audio"])
def test_nonprivate_media_rejected_before_preflight_or_download(
    app, chat_type, media_type
):
    async def scenario():
        await completed_quiz_without_text(app, MemoryStorageDouble().context())
        state = MemoryStorageDouble().context()
        kind = "private" if chat_type == "private_mismatch" else chat_type
        media = incoming(107, chat_type=kind, **{media_type: True})
        if chat_type == "private_mismatch":
            media.chat.id = 900
        await app.functions["handle_voice_note"](media, state)
        assert await state.get_state() is None
        app.bot.get_file.assert_not_awaited()
        app.bot.download_file.assert_not_awaited()
        app.transcribe.assert_not_awaited()
        assert app.generated.await_count == 0
    run(scenario())


@pytest.mark.parametrize(
    ("choices", "result"),
    [
        ((2, 2, 0), "Свет"),
        ((2, 2, 1), "Полутень"),
        ((0, 0, 0), "Тень"),
    ],
)
def test_fresh_voice_uses_verified_quiz_context(app, monkeypatch, choices, result):
    async def scenario():
        cid = await completed_quiz_without_text(
            app, MemoryStorageDouble().context(), choices
        )
        contexts = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (contexts.append(kw["archetype"]), original(**kw))[1],
        )
        await app.functions["handle_voice_note"](
            incoming(107, voice=True), MemoryStorageDouble().context()
        )
        assert contexts == [result]
        assert await database.get_coaching_resume_conversation_id(41) == cid
        assert app.generated.await_count == 1
    run(scenario())


@pytest.mark.parametrize(
    ("value", "verified"),
    [(None, 0), (None, 1), ("", 1), ("invalid", 1), ("Полутень", 0)],
)
def test_fresh_voice_missing_or_unverified_result_has_no_context(
    app, monkeypatch, value, verified
):
    async def scenario():
        await completed_quiz_without_text(app, MemoryStorageDouble().context())
        with sqlite3.connect(app.db_path) as conn:
            conn.execute(
                "UPDATE users SET test_result=?, quiz_result_verified=? WHERE user_id=41",
                (value, verified),
            )
        contexts = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (contexts.append(kw["archetype"]), original(**kw))[1],
        )
        await app.functions["handle_voice_note"](
            incoming(107, voice=True), MemoryStorageDouble().context()
        )
        assert contexts == [None]
        assert app.generated.await_count == 1
        assert "Полутень" not in str(contexts)
    run(scenario())


def test_fresh_voice_after_new_uses_current_id_and_cutoff(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        old_id = await complete_normal_path(app, state)
        await app.functions["cmd_new"](incoming(107, "/new"), state)
        new_id = await database.get_coaching_resume_conversation_id(41)
        assert new_id != old_id
        await app.functions["handle_voice_note"](
            incoming(108, voice=True), MemoryStorageDouble().context()
        )
        assert await database.get_coaching_resume_conversation_id(41) == new_id
        assert await database.get_conversation_history_with_ids(41, old_id) == []
        assert await database.get_recent_history(41, new_id) == [
            {"role": "user", "content": "Распознанный текст."},
            {"role": "assistant", "content": "Ответ."},
        ]
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT cutoff_chat_id, cutoff_message_id FROM active_chat_sessions WHERE user_id=41"
            ).fetchone() == (41, 107)
    run(scenario())


def test_fresh_voice_moderated_path_creates_one_draft(app):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        functions = {}
        dp = types.SimpleNamespace(message=Registrar(functions))
        moderated = app.chat_module.register_chat(
            dp, app.bot, object(), "offline", [99], app.states,
            lambda user: user.first_name, lambda user: user.first_name,
            database.add_chat_message, database.get_recent_history,
            database.create_pending_draft, database.rotate_conversation,
            database.get_or_create_conversation_id, database.is_active_conversation,
            direct_chat=False,
            get_conversation_history_with_ids=database.get_conversation_history_with_ids,
            admit_user_message=database.admit_user_message,
            get_coaching_resume_conversation_id=database.get_coaching_resume_conversation_id,
            get_coaching_quiz_result=database.get_coaching_quiz_result,
        )
        app.voice_module.register_voice(
            dp, app.bot, object(), "offline", [], app.transcribe, moderated,
            app.states, database.get_coaching_resume_conversation_id,
        )
        await functions["handle_voice_note"](
            incoming(107, voice=True), MemoryStorageDouble().context()
        )
        assert app.bot.get_file.await_count == 1
        assert app.transcribe.await_count == 1
        assert app.generated.await_count == 1
        assert await database.get_recent_history(41, cid) == [
            {"role": "user", "content": "Распознанный текст."},
        ]
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT conversation_id, status FROM pending_drafts WHERE user_id=41"
            ).fetchall() == [(cid, "PENDING")]
        assert app.bot.send_message.await_args_list[-1].args[0] == 99
        assert "(Тень)" in app.bot.send_message.await_args_list[-1].args[1]
    run(scenario())


def test_fresh_voice_empty_transcript_keeps_current_error_and_no_coaching(app):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        app.transcribe.return_value = ""
        state = MemoryStorageDouble().context()
        voice = incoming(107, voice=True)
        await app.functions["handle_voice_note"](voice, state)
        assert await state.get_state() == app.states.AI_CHAT.state
        assert app.bot.get_file.await_count == 1
        assert app.transcribe.await_count == 1
        assert app.generated.await_count == 0
        assert voice.answer.await_count == 1
        assert await database.get_recent_history(41, cid) == []
    run(scenario())


def test_fresh_voice_download_error_keeps_existing_exception_boundary(app):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        app.bot.download_file.side_effect = RuntimeError("offline download error")
        state = MemoryStorageDouble().context()
        with pytest.raises(RuntimeError, match="offline download error"):
            await app.functions["handle_voice_note"](incoming(107, voice=True), state)
        assert await state.get_state() == app.states.AI_CHAT.state
        assert app.bot.get_file.await_count == 1
        assert app.bot.download_file.await_count == 1
        assert app.transcribe.await_count == 0
        assert app.generated.await_count == 0
        assert await database.get_recent_history(41, cid) == []
    run(scenario())


def test_eligible_user_mid_quiz_does_not_preflight_voice_into_coaching(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await complete_normal_path(app, state)
        await state.set_state(app.states.QUESTION_STEP)
        await state.update_data(current_q_idx=0, answers_list=[], total_score=0)
        assert await state.get_state() == app.states.QUESTION_STEP.state
        before = await state.get_data()
        await app.functions["handle_voice_note"](incoming(108, voice=True), state)
        assert await state.get_state() == app.states.QUESTION_STEP.state
        assert await state.get_data() == before
        app.bot.get_file.assert_not_awaited()
        app.bot.download_file.assert_not_awaited()
        app.transcribe.assert_not_awaited()
        assert app.generated.await_count == 1  # Only the earlier text exchange.
    run(scenario())


def test_fresh_voice_transcription_exception_keeps_existing_boundary(app):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        app.transcribe.side_effect = RuntimeError("offline transcription error")
        state = MemoryStorageDouble().context()
        with pytest.raises(RuntimeError, match="offline transcription error"):
            await app.functions["handle_voice_note"](incoming(107, voice=True), state)
        assert await state.get_state() == app.states.AI_CHAT.state
        assert app.bot.get_file.await_count == 1
        assert app.bot.download_file.await_count == 1
        assert app.transcribe.await_count == 1
        assert app.generated.await_count == 0
        assert await database.get_recent_history(41, cid) == []
    run(scenario())

# Contextual /start: durable state is unchanged by opening home or continuing.
def durable_start_snapshot(db_path, user_id=41):
    with sqlite3.connect(db_path) as conn:
        return {
            "user": conn.execute(
                "SELECT coaching_eligible, test_result, quiz_result_verified "
                "FROM users WHERE user_id = ?", (user_id,),
            ).fetchone(),
            "session": conn.execute(
                "SELECT conversation_id, cutoff_chat_id, cutoff_message_id "
                "FROM active_chat_sessions WHERE user_id = ?", (user_id,),
            ).fetchone(),
            "history": conn.execute(
                "SELECT role, content, conversation_id FROM chat_messages "
                "WHERE user_id = ? ORDER BY id", (user_id,),
            ).fetchall(),
            "drafts": conn.execute(
                "SELECT status, conversation_id FROM pending_drafts "
                "WHERE user_id = ? ORDER BY id", (user_id,),
            ).fetchall(),
        }


@pytest.mark.parametrize("row_kind", ["new", "user", "history", "session", "legacy"])
def test_start_ineligible_evidence_never_selects_home(app, row_kind):
    async def scenario():
        if row_kind != "new":
            with sqlite3.connect(app.db_path) as conn:
                conn.execute("INSERT INTO users (user_id) VALUES (41)")
                if row_kind in {"history", "legacy"}:
                    conn.execute(
                        "INSERT INTO chat_messages (user_id, role, content) "
                        "VALUES (41, 'user', 'legacy')"
                    )
                if row_kind in {"session", "legacy"}:
                    conn.execute(
                        "INSERT INTO active_chat_sessions (user_id, conversation_id) "
                        "VALUES (41, 'legacy-id')"
                    )
                if row_kind == "legacy":
                    conn.execute(
                        "UPDATE users SET test_result='Полутень', "
                        "quiz_result_verified=0 WHERE user_id=41"
                    )
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        assert await state.get_state() is None
        assert (await state.get_data())["welcome_message_id"] == 100
        assert await database.is_coaching_eligible(41) is False
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        assert await state.get_state() == app.states.QUESTION_STEP.state
        assert (await state.get_data())["current_q_idx"] == 0
        app.generated.assert_not_awaited()
    run(scenario())


def test_start_interrupts_noneligible_quiz_and_restarts_at_first_question(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(100, "/start"), state)
        await app.functions["start_quiz"](callback(100, "start_quiz"), state)
        await app.functions["process_answer"](callback(101, "q_ans_0"), state)
        assert (await state.get_data())["current_q_idx"] == 1
        await app.functions["cmd_start"](incoming(200, "/start"), state)
        assert await state.get_state() is None
        assert "answers_list" not in await state.get_data()
        old_button = callback(102, "q_ans_0")
        await app.functions["process_answer"](old_button, state)
        assert old_button.answer.await_count == 1
        await app.functions["start_quiz"](callback(200, "start_quiz"), state)
        assert await state.get_state() == app.states.QUESTION_STEP.state
        assert (await state.get_data())["current_q_idx"] == 0
        assert (await state.get_data())["answers_list"] == []
        assert await database.is_coaching_eligible(41) is False
    run(scenario())


@pytest.mark.parametrize("fresh_fsm", [False, True])
def test_eligible_start_and_continue_are_durably_nondestructive(app, fresh_fsm):
    async def scenario():
        existing_state = MemoryStorageDouble().context()
        cid = await complete_normal_path(app, existing_state)
        with sqlite3.connect(app.db_path) as conn:
            conn.execute(
                "INSERT INTO pending_drafts (user_id, status, conversation_id) "
                "VALUES (41, 'PENDING', ?)", (cid,)
            )
        before = durable_start_snapshot(app.db_path)
        state = MemoryStorageDouble().context() if fresh_fsm else existing_state
        model_calls = app.generated.await_count
        start = incoming(200, "/start")
        await app.functions["cmd_start"](start, state)
        assert await state.get_state() == app.states.HOME.state
        assert start.answer.await_count == 1
        start.answer_photo.assert_not_awaited()
        assert start.answer.await_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "continue_coaching"
        assert durable_start_snapshot(app.db_path) == before
        assert app.generated.await_count == model_calls
        assert (await state.get_data())["home_message_id"] == 201
        continue_button = callback(201, "continue_coaching")
        await app.functions["continue_coaching"](continue_button, state)
        assert await state.get_state() == app.states.AI_CHAT.state
        assert (await state.get_data())["shadow_conversation_id"] == cid
        assert continue_button.message.answer.await_count == 1
        assert durable_start_snapshot(app.db_path) == before
        assert app.generated.await_count == model_calls
        assert await database.get_coaching_quiz_result(41) == "Тень"
    run(scenario())


def test_start_home_continue_then_text_uses_existing_pipeline_once(app):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(200, "/start"), state)
        await app.functions["continue_coaching"](callback(201, "continue_coaching"), state)
        await app.functions["coaching"](incoming(202, "Продолжаю."), state)
        assert app.generated.await_count == 1
        assert await database.get_recent_history(41, cid) == [
            {"role": "user", "content": "Продолжаю."},
            {"role": "assistant", "content": "Ответ."},
        ]
        assert await database.get_coaching_resume_conversation_id(41) == cid
    run(scenario())


def test_start_home_continue_then_voice_uses_existing_pipeline_once(app):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(200, "/start"), state)
        await app.functions["continue_coaching"](callback(201, "continue_coaching"), state)
        await app.functions["handle_voice_note"](incoming(202, voice=True), state)
        assert app.bot.get_file.await_count == 1
        assert app.bot.download_file.await_count == 1
        assert app.transcribe.await_count == 1
        assert app.generated.await_count == 1
        assert await database.get_recent_history(41, cid) == [
            {"role": "user", "content": "Распознанный текст."},
            {"role": "assistant", "content": "Ответ."},
        ]
    run(scenario())


def test_home_buttons_reject_old_wrong_and_duplicate_messages(app):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(200, "/start"), state)
        await app.functions["cmd_start"](incoming(300, "/start"), state)
        for message_id in (201, 399):
            bad = callback(message_id, "continue_coaching")
            await app.functions["continue_coaching"](bad, state)
            assert bad.answer.await_args.kwargs["show_alert"] is True
            assert await state.get_state() == app.states.HOME.state
        good = callback(301, "continue_coaching")
        await app.functions["continue_coaching"](good, state)
        assert await state.get_state() == app.states.AI_CHAT.state
        again = callback(301, "continue_coaching")
        await app.functions["continue_coaching"](again, state)
        assert again.answer.await_args.kwargs["show_alert"] is True
        assert await database.get_coaching_resume_conversation_id(41) == cid
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM active_chat_sessions WHERE user_id=41"
            ).fetchone()[0] == 1
        app.generated.assert_not_awaited()
    run(scenario())


def test_home_private_boundary_and_missing_session_fail_closed(app):
    async def scenario():
        await database.mark_coaching_eligible(41)
        state = MemoryStorageDouble().context()
        group = incoming(200, "/start", chat_type="group")
        await app.functions["cmd_start"](group, state)
        assert await state.get_state() is None
        group.answer.assert_not_awaited()
        await app.functions["cmd_start"](incoming(200, "/start"), state)
        assert await state.get_state() == app.states.HOME.state
        group_button = callback(201, "continue_coaching")
        group_button.message.chat.type = "group"
        group_button.message.chat.id = 900
        await app.functions["continue_coaching"](group_button, state)
        assert await state.get_state() == app.states.HOME.state
        with sqlite3.connect(app.db_path) as conn:
            conn.execute("DELETE FROM active_chat_sessions WHERE user_id=41")
        missing = callback(201, "continue_coaching")
        await app.functions["continue_coaching"](missing, state)
        assert missing.answer.await_args.kwargs["show_alert"] is True
        assert await state.get_state() == app.states.HOME.state
        assert await database.is_coaching_eligible(41) is True
        assert await database.get_coaching_resume_conversation_id(41) is None
        app.generated.assert_not_awaited()
    run(scenario())


def test_start_after_new_keeps_new_id_cutoff_and_no_old_history(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        old_cid = await complete_normal_path(app, state)
        await app.functions["cmd_new"](incoming(200, "/new"), state)
        before = durable_start_snapshot(app.db_path)
        assert before["session"][0] != old_cid
        assert before["history"] == []
        await app.functions["cmd_start"](incoming(201, "/start"), state)
        assert await state.get_state() == app.states.HOME.state
        assert durable_start_snapshot(app.db_path) == before
        await app.functions["continue_coaching"](callback(202, "continue_coaching"), state)
        assert (await state.get_data())["shadow_conversation_id"] == before["session"][0]
        assert durable_start_snapshot(app.db_path) == before
    run(scenario())


@pytest.mark.parametrize("result,verified", [(None, 0), ("Полутень", 0), ("", 1)])
def test_start_continue_never_invents_quiz_context(app, monkeypatch, result, verified):
    async def scenario():
        cid = await database.mark_coaching_eligible(41)
        with sqlite3.connect(app.db_path) as conn:
            conn.execute(
                "UPDATE users SET test_result=?, quiz_result_verified=? WHERE user_id=41",
                (result, verified),
            )
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(200, "/start"), state)
        await app.functions["continue_coaching"](callback(201, "continue_coaching"), state)
        assert await database.get_coaching_quiz_result(41) is None
        observed = []
        original = app.chat_module.build_system_instruction
        monkeypatch.setattr(
            app.chat_module, "build_system_instruction",
            lambda **kw: (observed.append(kw["archetype"]), original(**kw))[1],
        )
        await app.functions["coaching"](incoming(202, "Без тестового контекста."), state)
        assert observed == [None]
        assert await database.get_coaching_resume_conversation_id(41) == cid
        assert app.generated.await_count == 1
    run(scenario())


def test_start_home_voice_message_recovers_without_button(app):
    async def scenario():
        cid = await completed_quiz_without_text(app, MemoryStorageDouble().context())
        state = MemoryStorageDouble().context()
        await app.functions["cmd_start"](incoming(200, "/start"), state)
        assert await state.get_state() == app.states.HOME.state
        await app.functions["handle_voice_note"](incoming(202, voice=True), state)
        assert await state.get_state() == app.states.AI_CHAT.state
        assert app.bot.get_file.await_count == 1
        assert app.transcribe.await_count == 1
        assert app.generated.await_count == 1
        assert await database.get_recent_history(41, cid) == [
            {"role": "user", "content": "Распознанный текст."},
            {"role": "assistant", "content": "Ответ."},
        ]
        stale = callback(201, "continue_coaching")
        await app.functions["continue_coaching"](stale, state)
        assert stale.answer.await_args.kwargs["show_alert"] is True
    run(scenario())
