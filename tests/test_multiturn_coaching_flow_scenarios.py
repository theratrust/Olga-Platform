"""Integrity checks for synthetic, fixed user trajectories; no model calls."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'tests/fixtures/multiturn_coaching_flow_scenarios.json').read_text(encoding='utf-8'))
SOURCE = (ROOT / 'knowledge/method/источник_истины_метода_Ольги.md').read_text(encoding='utf-8')
SCENARIOS = DATA['scenarios']


def test_exact_scenario_contract():
    assert DATA['schema_version'] == '1.0'
    assert DATA['language'] == 'ru' and DATA['synthetic'] is True
    assert DATA['provenance'] == 'derived_multiturn_coaching_flow_fixture'
    assert len(SCENARIOS) == len({s['id'] for s in SCENARIOS}) == 6
    assert [s['id'] for s in SCENARIOS] == [
        'identity_after_relocation', 'uncertainty_unknown',
        'rejected_hypothesis_reopening', 'rich_reflection_question_discipline',
        'answered_question_continuity', 'partner_work_autonomy',
    ]
    fields = {'id', 'title', 'purpose', 'source_ids', 'user_turns',
              'evaluation_focus', 'expected_guardrails', 'known_traps', 'notes'}
    for s in SCENARIOS:
        assert set(s) == fields
        assert re.fullmatch(r'[a-z][a-z0-9_]+', s['id'])
        assert s['title'] and s['purpose'] and s['notes']
        assert 8 <= len(s['user_turns']) <= 12
        assert all(isinstance(t, str) and t.strip() and re.search('[А-Яа-яЁё]', t)
                   for t in s['user_turns'])
        for key in ('source_ids', 'evaluation_focus', 'expected_guardrails', 'known_traps'):
            assert isinstance(s[key], list) and s[key]
        assert len(s['source_ids']) == len(set(s['source_ids']))
        assert all(f'| {sid} |' in SOURCE for sid in s['source_ids'])
        assert 'assistant' not in s and 'expected_response' not in s


def test_required_trajectory_coverage():
    turns = {s['id']: ' '.join(s['user_turns']).lower() for s in SCENARIOS}
    assert sum('я не знаю' in t for t in SCENARIOS[1]['user_turns']) >= 2
    assert 'не страшно' in turns['rejected_hypothesis_reopening']
    assert 'сейчас вспомнила' in turns['rejected_hypothesis_reopening']
    assert 'я уже отвечала' in turns['answered_question_continuity']
    assert 'муж' in turns['identity_after_relocation']
    assert 'работ' in turns['identity_after_relocation']
    assert 'муж' in turns['partner_work_autonomy']
    assert 'работ' in turns['partner_work_autonomy']
    assert all(any(mark in text for mark in ('неточно', 'уточн', 'не говорю', 'не хочу', 'не обязательно'))
               for text in turns.values())
    assert all(any(len(t) >= 110 for t in s['user_turns']) for s in SCENARIOS)
