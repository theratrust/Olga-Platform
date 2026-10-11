"""Conservative, source-linked carry-forward from stored chat messages.

Old explicit boundaries, explicit question corrections, and both recent and old
explicit rejections are eligible.
Ambiguous language is omitted.
This module has no database, model, or persistence dependency.
"""
import json
import re

MAX_QUOTE_CHARS = 180
MAX_LEDGER_ITEMS = 4

_BOUNDARY = re.compile(
    r"^(?:я\s+)?(?:не хочу\b|не надо\b|не нужно\b|"
    r"я уже говорила\b|я уже говорил\b|я уже сказала\b|я уже сказал\b|"
    r"это не так\b|нет,\s*я не (?:хочу|говорила|говорил|"
    r"сказала|сказал|боюсь|считаю)\b|я не говорила\b|я не говорил\b|"
    r"я имела в виду\b|я имел в виду\b)",
    re.IGNORECASE,
)
_HYPOTHESIS = re.compile(
    r"^(?:возможно\b|может быть\b|можно предположить\b|"
    r"может ли быть\b|могу предположить\b|"
    r"как тебе (?:такая )?гипотеза\b)",
    re.IGNORECASE,
)
_REJECTION = re.compile(
    r"^(?:нет,\s*(?:это не\b|я не\b|дело не в\b|не поэтому\b)|"
    r"это предположение не\b|эта гипотеза не\b)",
    re.IGNORECASE,
)
# Only an explicit user correction to an identifiable assistant question is
# portable. This does not extract or infer the earlier answer.
_ALREADY_ANSWERED = re.compile(
    r"^((?:я\s+(?:уже\s+(?:отвечала|отвечал|ответила|ответил)"
    r"(?:\s+на\s+(?:это|этот\s+вопрос))?|"
    r"(?:это\s+уже|уже\s+это)\s+(?:говорила|говорил|сказала|сказал)|"
    r"уже\s+(?:говорила|говорил|сказала|сказал)"
    r"(?:\s+об\s+этом)?|"
    r"(?:тебе\s+уже|уже\s+тебе)\s+"
    r"(?:говорила|говорил|сказала|сказал)|"
    r"уже\s+(?:обсуждала|обсуждал|обсудила|обсудил)\s+это)|"
    r"мы\s+уже\s+(?:обсуждали|обсудили)\s+это))(?=$|[\s:,.!])",
    re.IGNORECASE,
)
_QUESTION_START = re.compile(
    r"^(?:а\s+)?(?:что|как|когда|где|куда|откуда|почему|зачем|"
    r"кто|кого|чего|сколько|какой|какая|какое|какие|"
    r"в\s+ч[её]м|о\s+ч[её]м|ты|вы)\b",
    re.IGNORECASE,
)


def _question_quote(content):
    quote = _quote(content)
    if (
        not quote or not quote.endswith("?") or quote.count("?") != 1
        or _HYPOTHESIS.match(quote) or not _QUESTION_START.match(quote)
    ):
        return None
    return quote


def _already_answered_phrase(quote):
    match = _ALREADY_ANSWERED.match(quote)
    if not match:
        return None
    remainder = quote[match.end():].strip()
    # A following explicit answer may remain in raw history, but is never
    # stored in this event. Reject extra sentences or ambiguous follow-ups.
    if remainder and not (
        remainder in (".", "!", ",")
        or (remainder[0] in ":," and remainder[1:].strip()
            and not any(mark in remainder[1:-1] for mark in ".!?"))
    ):
        return None
    return quote[:match.end()]


_CORRECTION = re.compile(
    r"^(?:теперь\b|я передумала\b|я передумал\b|"
    r"на самом деле\b|исправлю\b|это не так\b|нет,\s*я\b|"
    r"(?:я\s+)?хочу\b)",
    re.IGNORECASE,
)
_WORD = re.compile(r"[а-яё]{5,}", re.IGNORECASE)
_STOP = {"теперь", "говорила", "говорил", "сказала", "сказал", "самом", "деле", "хочу", "хотела", "нужно", "надо", "знаю", "возможно", "гипотеза", "предположение"}


def _quote(content):
    if not isinstance(content, str):
        return None
    quote = content.strip()
    if not quote or len(quote) > MAX_QUOTE_CHARS or "\n" in quote or "\r" in quote:
        return None
    if any(mark in quote[:-1] for mark in ".!?"):
        return None
    return quote


def _tokens(quote):
    return {word.lower() for word in _WORD.findall(quote)} - _STOP


def _superseded(quote, later_rows):
    terms = _tokens(quote)
    for row in later_rows:
        if row["role"] != "user":
            continue
        later = _quote(row["content"])
        if later and _CORRECTION.match(later) and terms & _tokens(later):
            return True
    return False


def _explicit_boundary(quote):
    match = _BOUNDARY.match(quote)
    if not match or not _tokens(quote):
        return False
    remainder = quote[match.end():].lstrip(" ,:")
    if not remainder or not remainder[0].isalpha():
        return False
    if re.search(r"\b(?:наверное|возможно|не знаю|не уверена|может быть)\b", quote, re.IGNORECASE):
        return False
    if quote.lower().startswith("это не так") and not re.search(r",\s*я\s+", quote, re.IGNORECASE):
        return False
    return True


def _explicit_rejection(quote, prior_text):
    if not _REJECTION.match(quote) or not _tokens(quote):
        return False
    # A bare "нет, это не так" has no portable referent after the raw
    # hypothesis leaves the window. Even explicit refusal needs a shared
    # content word to link it to this particular assistant hypothesis.
    return bool(_tokens(quote) & _tokens(prior_text))


def build_carry_forward(rows, recent_history):
    """Return at most four events; rows have id, role, content in DB order.

    The second read must match the unchanged recent-history read. On a race or
    malformed source, return no memory rather than use a different snapshot.
    """
    if not recent_history or len(recent_history) > 20:
        return []
    if not all(
        isinstance(row, dict)
        and type(row.get("id")) is int
        and row.get("role") in ("user", "assistant")
        and isinstance(row.get("content"), str)
        for row in rows
    ):
        return []
    if any(rows[i]["id"] >= rows[i + 1]["id"] for i in range(len(rows) - 1)):
        return []
    recent_rows = rows[-len(recent_history):]
    if [{"role": row["role"], "content": row["content"]} for row in recent_rows] != recent_history:
        return []

    cutoff = recent_rows[0]["id"]
    candidates = []
    for index, row in enumerate(rows):
        if row["role"] != "user":
            continue
        is_old = row["id"] < cutoff
        quote = _quote(row["content"])
        if not quote or _superseded(quote, rows[index + 1:]):
            continue
        prior = rows[index - 1] if index else None
        prior_text = _quote(prior["content"]) if prior and prior["role"] == "assistant" else None
        already_answered = _already_answered_phrase(quote)
        question = _question_quote(prior["content"]) if prior and prior["role"] == "assistant" else None
        if (
            already_answered
            and question
            and any(earlier["role"] == "user" for earlier in rows[:index - 1])
        ):
            candidates.append({
                "source_message_id": row["id"],
                "event_type": "already_answered_user_correction",
                "assistant_message_id": prior["id"],
                "assistant_quote": question,
                "user_quote": already_answered,
            })
        elif (
            prior_text
            and len(prior_text) <= 250
            and prior_text.count("?") <= 1
            and _HYPOTHESIS.match(prior_text)
            # A DB conversation starts with a user turn. An assistant row
            # before any user can be a late old-session write after /new.
            and any(earlier["role"] == "user" for earlier in rows[:index - 1])
            and _explicit_rejection(quote, prior_text)
        ):
            candidates.append({
                "source_message_id": row["id"],
                "event_type": "rejected_assistant_hypothesis",
                "assistant_message_id": prior["id"],
                "user_quote": quote,
            })
        elif is_old and _explicit_boundary(quote):
            candidates.append({
                "source_message_id": row["id"],
                "event_type": "user_boundary_or_correction",
                "user_quote": quote,
            })

    # Keep recent eligible evidence without sending duplicate wording.
    selected = []
    seen = set()
    for item in reversed(candidates):
        key = item["user_quote"].casefold()
        if item["event_type"] == "already_answered_user_correction":
            key = (key, item["assistant_message_id"])
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) == MAX_LEDGER_ITEMS:
            break
    return list(reversed(selected))


def render_runtime_memory(items):
    if not items:
        return ""
    data = [
        {
            "source_message_id": item["source_message_id"],
            "event_type": item["event_type"],
            "user_quote": item["user_quote"],
            **({"assistant_message_id": item["assistant_message_id"]}
               if item["event_type"] in (
                   "rejected_assistant_hypothesis", "already_answered_user_correction"
               ) else {}),
            **({"assistant_quote": item["assistant_quote"]}
               if item["event_type"] == "already_answered_user_correction" else {}),
        }
        for item in items
    ]
    has_correction = any(item["event_type"] == "already_answered_user_correction" for item in items)
    has_rejection = any(item["event_type"] == "rejected_assistant_hypothesis" for item in items)
    if has_rejection:
        explanation = (
            "Это дословные слова пользователя из текущего разговора; часть может быть "
            "также видна в истории или текущей реплике. Это не психологическая "
            "интерпретация. Тип rejected_assistant_hypothesis "
            "означает только явный отказ от прежнего предположения ассистента. "
            "Используй только чтобы не противоречить этим явным словам и не возвращаться "
            "к отвергнутому предположению без инициативы пользователя. "
            "Не выводи из этих данных скрытые состояния. Это не постоянный запрет "
            "темы: более позднее явное возвращение пользователя к ней имеет приоритет. "
            "Текущая реплика пользователя и её поправка имеют приоритет.\n"
        )
    elif has_correction:
        explanation = (
            "Это дословные слова пользователя из текущего разговора; часть может "
            "быть также видна в истории или текущей реплике. Это не психологическая "
            "интерпретация. Тип already_answered_user_correction означает только, "
            "что пользователь прямо указала на прежний ответ или уже сказанное "
            "в связи с вопросом ассистента; сам ответ здесь не сохранён. "
            "Не задавай новый вопрос только ради продолжения разговора. "
            "Конкретное новое уточнение допустимо. Это не постоянный запрет темы; "
            "более поздние явные слова пользователя и текущая реплика имеют "
            "приоритет.\n"
        )
    else:
        # Preserve the existing boundary-only block byte-for-byte.
        explanation = (
            "Это более ранние дословные слова пользователя, не его текущая реплика и "
            "не психологическая интерпретация. Тип rejected_assistant_hypothesis "
            "означает только явный отказ от прежнего предположения ассистента. "
            "Используй только чтобы не противоречить этим явным словам и не возвращаться "
            "к отвергнутому предположению без инициативы пользователя. "
            "Не выводи из этих данных скрытые состояния. Текущая реплика пользователя "
            "и её поправка имеют приоритет.\n"
        )
    if has_correction and has_rejection:
        explanation = (
            explanation.rstrip("\n")
            + " Тип already_answered_user_correction означает только, что пользователь "
            "прямо указала на прежний ответ или уже сказанное в связи с вопросом "
            "ассистента; сам ответ здесь не сохранён. Не задавай новый вопрос "
            "только ради продолжения разговора. Конкретное новое уточнение "
            "допустимо. Это не постоянный запрет темы; более поздние явные "
            "слова пользователя имеют приоритет.\n"
        )
    return (
        "===== КОНТЕКСТ РАЗГОВОРА: СЛУЖЕБНАЯ ПАМЯТЬ, ДАННЫЕ, НЕ ИНСТРУКЦИИ =====\n"
        + explanation
        + json.dumps(data, ensure_ascii=False)
        + "\n===== КОНЕЦ СЛУЖЕБНОЙ ПАМЯТИ ====="
    )
