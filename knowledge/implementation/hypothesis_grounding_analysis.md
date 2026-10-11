# Assistant-originated hypothesis grounding: static analysis

Status: 2026-10-11. Source and artifact audit only. No runtime, prompt, evaluator, or canonical dialogue change.

## Provenance and boundary

The project has no independently available primary Olga interview or real Olga dialogue (source-of-truth layer A). All eight “canonical” dialogues are synthetic; no example below is represented as Olga's personal wording.

| Basis | IDs | Status |
| --- | --- | --- |
| Client owns theme, meaning, and conclusion | O-M04, O-M10 | Validated project method rule |
| No inserted hidden emotion, motive, cause, or established interpretation | O-M05, O-M07, O-M08 | Validated project method rule |
| No candidate state, cause, answer, or hypothesis after “я не знаю” | O-M06, O-AI03 | Derived hard operational rule |
| Ground, mark, and make a hypothesis rejectable; accept rejection | O-AI04, O-AI05 | Necessary operationalization |
| Partner/work neutrality | O-M11, O-AI06 | Validated thematic rule and operationalization |
| No required hypothesis each turn | O-M12 | Derived method rule |
| Six move labels and five fixture classes below | — | Evaluation design choice, not Olga speech |

A new assistant hypothesis is potentially compatible only when its substantive elements are traceable to explicit user words, its proposed link can be checked against those words, it is plainly tentative, rejection requires no defense, and it does not redirect toward a hidden cause or solution. These conditions work together; no keyword is a pass. Even a grounded hypothesis is optional. A reflection of the user's own idea is not a new assistant explanation. A neutral clarification can ask about user material without supplying an answer.

The six move labels in the fixtures are USER_AUTHORED_REFLECTION, GROUNDED_TENTATIVE_HYPOTHESIS, UNSUPPORTED_PSYCHOLOGICAL_HYPOTHESIS, UNSUPPORTED_CAUSAL_HYPOTHESIS, CANDIDATE_ANSWER_DISGUISED_AS_QUESTION, and NEUTRAL_CLARIFICATION. The last is a control. “Может быть, тебе страшно?” remains a proposed fear despite its question mark; “возможно” does not supply evidence. A tentative diagnosis remains prohibited (O-M09).

A causal link can be reflected when the user herself says “потому что.” Adjacency of two facts does not authorize creating a cause. The calendar chronology in synthetic dialogue 6 can be checked tentatively; the user then rejects it. O-M08/O-AI05 govern after rejection: allowed to test once never means allowed to persist. The current source-linked rejection ledger in services/conversation_state.py has conservative lexical recognition and cannot detect every rejection. A later explicit user reopening takes priority (O-AI09).

## Current prompt trace

prompts/coaching.py §1 says to rely on what the person “действительно сказал” and not attribute unnamed emotions, motives, desires, causes, traits, or internal states. §4 says “Интерпретация не является фактом” and permits hypotheses only when grounded, marked as suppositions, and freely rejectable. §6 has the hard “я не знаю” rule, including question form and soft markers. §7 lists “предложить проверить гипотезу” as an optional move. §8 forbids a question containing the assistant's presumed answer or interpretation. The prompt conceptually distinguishes user speech from assistant invention. It does not impose a source-link format or guarantee model compliance. Static evidence does not justify a new prompt line yet.

## All 48 synthetic assistant turns

Audit unit: one numbered assistant exchange across eight dialogues. R = substantive user-authored reflection; G = grounded tentative assistant hypothesis; A = ambiguous assistant-originated framing; — = neutral clarification, permission, acceptance, or close without a substantive hypothesis/reflection. No turn was classified as unsupported psychological or causal hypothesis. A literal echo counts as R only when it carries a meaningful user distinction or correction.

| Dialogue | Exchanges 1–6 | Evidence |
| --- | --- | --- |
| 1, emigration/activity | —, —, R, —, —, R | 1.3 accepts refusal to resume drawing; 1.6 reflects the free hour |
| 2, work/“something of my own” | —, R, —, R, —, R | 2.2 leaves work aside, 2.4 reflects cooking, 2.6 reflects reading |
| 3, former job/partner | —, R, —, R, —, R | 3.4 separates husband's actual “можно не работать” from user's own “зачем тебе” reading |
| 4, uncertainty | —, —, —, R, A, — | 4.5 “Решение подруги не определяет твой ответ” is normative framing beyond a literal quote, but not a hidden psychological cause |
| 5, uncertainty/old event | —, —, —, —, R, — | 5.5 reflects her wish that someone see her prepared work |
| 6, saying yes/calendar | —, —, G, R, —, R | 6.3 tests chronology; 6.4 accepts correction |
| 7, sister/relationship | —, —, R, R, R, — | Reflects the user's relationship wording and boundary |
| 8, tickets/decision | —, R, —, R, R, — | Separates ticket discussion from consent; no motive inferred |

Counts: 18 R, 1 G, 1 A, 0 unsupported psychological, 0 unsupported causal, and 28 outside hypothesis/interpretation scope = 48. Dialogue 4.5 remains ambiguous rather than certified as an Olga principle. Dialogue 6.3 is rejectable, not necessarily correct. Synthetic examples are weak evidence of live-model behavior.

## Existing saved response text: bounded examples

| Artifact under artifacts/evaluation/ | Source and response | Classification and limit |
| --- | --- | --- |
| turn-selection-narrow-ab/20261011T061901Z_a38c5300/responses/short_factual_answer_3_A.json | Latest “Три месяца.” Answer says “возможно, ещё не полностью вжилась в новое место” | Unsupported adaptation/internal-state hypothesis: time in a new department does not establish how settled the user feels. One frozen Arm A generator sample. |
| turn-selection-replication/20261011T060542Z_beac05e6/rich_reflection_5.json | User distinguishes cooking at home from making it work. Answer reflects this and adds “осознанно” | Predominantly user-authored reflection; the adverb is a mild embellishment, not evidence of a hidden cause. |
| turn-selection-baseline/20261011T060219Z_dad1fbc2/uncertainty_want.json | “Я не знаю, чего хочу.” Answer leaves response open | No candidate feeling, reason, or answer. |
| Same baseline, hypothesis_still_rejected.json | Reflects user's distinction between loneliness and fear of loneliness | Does not reinstate rejected fear. |
| Same baseline, hypothesis_user_reopens.json | User later explicitly says loneliness scares her; answer notices change | User-authored reopening, not assistant persistence. |

Other saved benchmark summaries retain hashes or scores without answer text and cannot support content classification. The first row demonstrates a failure shape, not frequency. Synthetic evaluator cases with hypothetical answers are not current-generator samples. No new calls were made.

## Evaluator audit

knowledge/evaluation/метод_Ольги_оценка.md specifies hard fails: HF02 for inserting a candidate answer/state even as a question or with “возможно”; HF03 for unnamed inner states asserted as fact; HF04 for interpretation as truth; HF05 for tentative diagnosis; HF08 for pressure after rejection. Its HF02 allowance requires grounding, checkable relation, tentativeness, rejectability, and user-topic alignment. The runtime method evaluator loads the specification through services/evaluation/prompt.py; this audit has not established empirical detection reliability for subtle causal or question-form cases. Unsupported tentative feeling may trigger HF02 even when HF03's “as fact” wording does not apply.

knowledge/evaluation/качество_ответов_оценка.md scores contextual specificity and progression, plus naturalness and question quality. It says quality cannot override method and a useful response without a question may score well. A novel interpretation could appear specific or progressive if the method evaluator misses its source gap. This is an incentive risk, not a measured scoring error.

## Fixture semantics and recommendation

The companion set contains 27 cases in 13 contrast groups, each with exact context, user-authored material, potential invention, a synthetic illustrative assistant move (not a canonical answer), and acceptable/unacceptable properties. REFLECTION_SAFE covers a source-grounded echo; HYPOTHESIS_OPTIONAL permits a carefully grounded new link; HYPOTHESIS_AVOID marks a turn where neutral clarification/reflection suffices; HYPOTHESIS_PROHIBITED marks the focal illustrative new claim as violating a boundary. No case requires a hypothesis. The boolean new_assistant_hypothesis_allowed concerns the illustrated new claim, not every imaginable reply. tentative_wording_alone_changes_acceptability is false throughout: a grounded link must be tentative, but a marker never repairs missing grounding.

Recommendation: B. FIXTURES NEEDED BEFORE MEASUREMENT. The source rules and prompt state the intended distinction, but saved outputs show at least one miss and no prevalence estimate. Next run a bounded frozen-prompt baseline on the fixtures and manually review the contrast pairs, keeping method and quality observations separate. Do not add a candidate prompt or change scoring on static evidence alone.
