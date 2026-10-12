"""Current-behavior characterization for restart recovery; no network or model calls."""
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


def incoming(message_id, text=None, *, user_id=41, voice=False, chat_type="private"):
    user = types.SimpleNamespace(id=user_id, first_name="Тест", last_name=None, username=None)
    chat = types.SimpleNamespace(id=user_id if chat_type == "private" else 900,
                                 type=chat_type)
    return types.SimpleNamespace(
        from_user=user, chat=chat, message_id=message_id, text=text,
        voice=types.SimpleNamespace(file_id="offline") if voice else None,
        audio=None, answer=AsyncMock(), answer_photo=AsyncMock(),
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
        return types.SimpleNamespace(message_id=500 + len(sent))
    async def send_photo(*args, **kwargs):
        sent.append(("photo", args, kwargs))
        return types.SimpleNamespace(message_id=500 + len(sent))
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
    )
    questions = json.loads(
        (ROOT / "knowledge/method/shadow_light/v1.1/questions.json").read_text()
    )
    loaded["start"].register_start(dp, lambda user: user.first_name, lambda _: object())
    loaded["quiz"].register_quiz(
        dp, bot, states, questions, lambda user: user.first_name, lambda _: object()
    )
    loaded["callbacks"].register_callbacks(dp, bot, states)
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
    )
    transcribe = AsyncMock(return_value="Распознанный текст.")
    loaded["voice"].register_voice(dp, bot, object(), "offline", [], transcribe, coach)
    return types.SimpleNamespace(
        db_path=db_path, functions=functions, bot=bot, states=states,
        generated=generated, transcribe=transcribe, sent=sent,
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
    await f["enter_chat"](callback(105, "open_ai_chat"), state)
    assert await state.get_state() == app.states.AI_CHAT.state
    await f["coaching"](incoming(106, "Первый разговор."), state)
    cid = await database.get_or_create_conversation_id(41)
    assert await database.get_recent_history(41, cid) == [
        {"role": "user", "content": "Первый разговор."},
        {"role": "assistant", "content": "Ответ."},
    ]
    return cid


def test_case_a_and_e_normal_quiz_coaching_then_fresh_memory_drops_first_returning_text(app):
    async def scenario():
        before = MemoryStorageDouble().context()
        cid = await complete_normal_path(app, before)
        assert (await before.get_data())["archetype"] == "Тень"
        with sqlite3.connect(app.db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert await database.get_user_profile(41) is None

        restarted = MemoryStorageDouble().context()
        assert await restarted.get_state() is None
        assert await restarted.get_data() == {}
        calls = app.generated.await_count
        returning = incoming(107, "Продолжаю после перезапуска.")
        await app.functions["coaching"](returning, restarted)
        assert app.generated.await_count == calls
        assert returning.answer.await_count == 0
        assert await database.get_or_create_conversation_id(41) == cid
        assert len(await database.get_recent_history(41, cid)) == 2
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
            assert "coaching_eligible" not in columns
            assert "onboarding_complete" not in columns
    run(scenario())


def test_case_d_after_new_active_id_and_cutoff_survive_but_fsm_does_not(app):
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
        assert await database.get_recent_history(41, new_id) == []
        assert await database.get_conversation_history_with_ids(41, old_id) == []
        assert app.generated.await_count == 1
    run(scenario())


def test_case_f_voice_after_fresh_memory_downloads_and_transcribes_before_state_gate(app):
    async def scenario():
        state = MemoryStorageDouble().context()
        cid = await complete_normal_path(app, state)
        restarted = MemoryStorageDouble().context()
        before = app.generated.await_count
        voice = incoming(107, voice=True)
        await app.functions["handle_voice_note"](voice, restarted)
        app.bot.get_file.assert_awaited_once()
        app.bot.download_file.assert_awaited_once()
        app.transcribe.assert_awaited_once_with(b"offline-audio")
        assert voice.text == "Распознанный текст."
        assert app.generated.await_count == before
        assert voice.answer.await_count == 0
        assert await database.get_or_create_conversation_id(41) == cid
        assert len(await database.get_recent_history(41, cid)) == 2
    run(scenario())
