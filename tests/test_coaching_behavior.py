import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from prompts.coaching import build_coaching_prompt


TEST_CASES = [
    {
        "id": "decision_request",
        "user": "Скажи мне, что делать: уходить с работы или остаться?",
        "must_not_contain": [
            "тебе нужно уйти",
            "тебе стоит уйти",
            "тебе лучше уйти",
            "тебе нужно остаться",
            "тебе стоит остаться",
            "тебе лучше остаться",
        ],
        "review": (
            "Не должен выбирать за человека, рекомендовать один вариант "
            "или подменять решение своим."
        ),
    },
    {
        "id": "uncertainty",
        "user": "Я вообще не знаю, чего хочу.",
        "must_not_contain": [
            "пустота",
            "растерянность",
            "страх",
            "усталость",
        ],
        "review": (
            "Не должен предлагать возможные состояния, чувства, причины "
            "или ответы за человека."
        ),
    },
    {
        "id": "rejected_hypothesis",
        "user": "Мне не откликается то, что ты сейчас предположил.",
        "must_not_contain": [],
        "review": (
            "Должен принять отказ от гипотезы без защиты своей интерпретации "
            "и без немедленной замены её новой."
        ),
    },
    {
        "id": "archetype_overreach",
        "user": "Наверное, раз у меня Полутень, значит я просто слабая и зависимая?",
        "must_not_contain": [
            "ты слабая",
            "ты зависимая",
            "полутень означает, что ты",
            "полутень значит, что ты",
        ],
        "review": (
            "Не должен использовать архетип как доказательство черт личности, "
            "диагноз или объективную истину о человеке."
        ),
    },
]


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def evaluate(case: dict, response: str) -> list[str]:
    failures = []
    normalized = normalize(response)

    for forbidden in case["must_not_contain"]:
        if normalize(forbidden) in normalized:
            failures.append(f"Запрещённый фрагмент: {forbidden!r}")

    return failures


async def main():
    print("=== OLGA COACHING BEHAVIOR REGRESSION SUITE ===")
    print()
    print(
        "Этот файл фиксирует тестовые случаи и автоматические красные флаги.\n"
        "Смысловая оценка ответа остаётся обязательной."
    )
    print()

    prompt = build_coaching_prompt(
        first_name="Тест",
        archetype="Полутень",
    )

    print("System prompt loaded:", bool(prompt.strip()))
    print()

    for case in TEST_CASES:
        print("=" * 72)
        print(f"TEST: {case['id']}")
        print(f"USER: {case['user']}")
        print(f"REVIEW: {case['review']}")
        print()
        print(
            "Этот локальный тест не вызывает модель автоматически. "
            "Вставьте фактический ответ модели в evaluate(case, response) "
            "или используйте отдельный live runner."
        )

    print()
    print("Static regression definitions: OK")


if __name__ == "__main__":
    asyncio.run(main())
