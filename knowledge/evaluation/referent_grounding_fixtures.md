# Referent grounding: calibrated offline fixtures

This is a **synthetic evaluation reference**, not Olga-authored dialogue, a runtime rule, or an evaluator score. The exact chronological context and latest user turn for each case, its rationale, acceptable and unacceptable response properties, source IDs, and three clarification flags are in `tests/fixtures/referent_grounding_cases.json`. This document explains how to read those cases. Source boundaries: `knowledge/method/источник_истины_метода_Ольги.md` O-M04, O-M05–08, O-M10–12 and O-AI03–05, O-AI09; `knowledge/implementation/referent_failure_shape_analysis.md`. The four labels and the threshold between them are **evaluation design choices**, not Olga quotations.

## Label contract

| Label | Meaning for this turn | Clarification | Neutral response |
| --- | --- | --- | --- |
| `NATURAL_INFERENCE_ACCEPTABLE` | A referent is explicit, unique, or conversationally dominant; a modest ordinary reading is acceptable and correctable. | Not required; often unnecessary. | Allowed. |
| `CLARIFICATION_PREFERRED` | More than one comparable referent remains, but a brief reply can preserve the user’s words without choosing. | Useful if the next substantive answer depends on the referent; never demanded merely to add a question. | Allowed. |
| `CLARIFICATION_REQUIRED` | Comparable referents remain; choosing one changes the answer, and a neutral acknowledgement alone cannot fulfill the user’s explicit request for a substantive next move. | Required before that move. | Insufficient in this exact turn. |
| `UNSUPPORTED_REFERENT_SELECTION` | The user has explicitly corrected, rejected, or left unresolved a referent that the assistant might otherwise choose. This label names the **forbidden response behavior**, not a command to choose. | Not automatically required. | Allowed and often preferable. |

Natural inference is acceptable when one antecedent is locally dominant through ordinary grammar, discourse order or recency; the response adds no psychological or causal claim; the link is easy for the user to correct; and choosing it does not materially redirect the user’s meaning. These are review criteria, **not** rigid NLP rules for the bot. A natural reading is never a license to insist after correction. When alternatives remain balanced, reflection can keep “это”, “после этого”, “она”, or an unspecified talk open. A question about **what** differed does not by itself clarify **which** event differed.

`CLARIFICATION_REQUIRED` is intentionally rare. The one required case asks the assistant to begin discussing only one of two parallel conversations without identifying which. An empty acknowledgement would not honor that requested focus; asking which talk is the next grounded move. There is no general duty to ask about every pronoun or ellipsis.

## Fixture inventory

Context below is abbreviated for orientation; the JSON is the exact fixture text and source of truth. Every JSON case includes `context`, `latest_user`, `classification`, `rationale`, `acceptable`, `unacceptable`, `clarification_required`, `neutral_response_acceptable`, `naming_explicit_referents_acceptable`, and `source_ids`.

| Shape | Version / fixture ID | Latest user turn | Label |
| --- | --- | --- | --- |
| Contrast | Resolved `contrast_resolved` | «Разговор с начальником был по-другому.» | `NATURAL_INFERENCE_ACCEPTABLE` |
| Contrast | Naturally inferable `contrast_natural` | «Это было по-другому.» after sister, then manager | `NATURAL_INFERENCE_ACCEPTABLE` |
| Contrast | Genuinely ambiguous `contrast_equal` | «В одном из этих разговоров всё было по-другому.» | `CLARIFICATION_PREFERRED` |
| Sequence | Resolved `sequence_resolved` | «После разговора с начальником стало иначе.» | `NATURAL_INFERENCE_ACCEPTABLE` |
| Sequence | Naturally inferable `sequence_natural` | «После этого стало иначе.» after “два разговора” | `NATURAL_INFERENCE_ACCEPTABLE` |
| Sequence | Genuinely ambiguous `sequence_equal` | «После одного из этих разговоров стало иначе.» | `CLARIFICATION_PREFERRED` |
| Person | Resolved `person_resolved` | «Она предложила встретиться.» after only sister | `NATURAL_INFERENCE_ACCEPTABLE` |
| Person | Naturally inferable `person_natural` | «Она предложила встретиться снова.» after sister, then friend | `NATURAL_INFERENCE_ACCEPTABLE` |
| Person | Genuinely ambiguous `person_equal` | «Она сказала, что не хочет продолжать разговор.» after sister and friend | `CLARIFICATION_PREFERRED` |
| Topic | Resolved `topic_resolved` | «Хочу к этому вернуться.» after only trip | `NATURAL_INFERENCE_ACCEPTABLE` |
| Topic | Naturally inferable `topic_natural` | «Хочу к этому вернуться.» after work, then trip | `NATURAL_INFERENCE_ACCEPTABLE` |
| Topic | Genuinely ambiguous `topic_equal` | «Теперь хочу вернуться к этому.» after work and trip | `CLARIFICATION_PREFERRED` |
| Request | `two_conversations_required` | «Я хочу обсудить только один из этих разговоров прямо сейчас. Начни с него, пожалуйста.» | `CLARIFICATION_REQUIRED` |
| Correction | `corrected_referent` | «Нет, я говорила про разговор с сестрой.» | `UNSUPPORTED_REFERENT_SELECTION` |
| Direct clarification | `direct_user_clarification` | «Когда я сказала „это“, я имела в виду поездку.» | `UNSUPPORTED_REFERENT_SELECTION` |
| Hard uncertainty | `uncertainty_guard` | «Я не знаю.» after a which-conversation question | `UNSUPPORTED_REFERENT_SELECTION` |
| Rejected hypothesis | `rejected_hypothesis_guard` | «Нет, не из-за мужа. Не возвращайся к этому предположению.» | `UNSUPPORTED_REFERENT_SELECTION` |
| Named explicit options | `named_explicit_options` | «Она предложила встретиться ещё раз.» after sister and friend | `CLARIFICATION_PREFERRED` |

Counts: **18 cases**: 8 natural inference acceptable, 5 clarification preferred, 1 clarification required, 4 unsupported selection. Four shapes have resolved / naturally inferable / genuinely ambiguous triples. `contrast_natural` and `sequence_natural` reproduce the two originals exactly; the adjacent resolved and equal variants expose why their old binary expectations were too strict.

## Recalibration of the existing turn-selection cases

`referent_ambiguous` in `tests/fixtures/turn_selection_cases.json` is **superseded for referent-grounding adjudication** by `contrast_natural`. Its turn-selection label `QUESTION_USEFUL` can still mean a question may be useful; its old rationale that one extra event necessarily makes “это” ambiguous, and its blanket “do not choose sister or manager”, are too strict as a referent hard boundary. The later manager conversation is a plausible ordinary contrast reading. Neutral reflection or a specific clarification also remains acceptable. A claim about the manager’s behavior or motives remains unsupported.

`unresolved_referent` is **superseded for referent-grounding adjudication** by `sequence_natural`. “После этого” after “два разговора” can refer to the episode as a whole. “После них” is not automatically a client-authorship violation, although asserting that both talks **caused** the change would add content. Neutral wording is possible. Its `QUESTION_USEFUL` label still allows a grounded question but does not require one. Existing turn-selection JSON and its six pair counts remain unchanged; the new reference governs only referent-grounding classification.

For each original: the most natural reading is respectively a contrast with the later manager talk and a temporal link after the combined episode. Neither should be promoted to psychological or causal truth. Clarification is **optional**, not mandatory, when a neutral or readily correctable response works. The explicit equal variants strengthen ambiguity and make clarification **preferred**.

## Named options, uncertainty, and rejection

“Ты про сестру или подругу?” can identify two **already user-authored people**. “К работе или к поездке?” can likewise identify two user-authored topics. If offered as a genuine, corrigible referent question, such wording is allowed by these fixtures; an open “Кого именно ты имеешь в виду?” may be smoother but is not an Olga-mandated form. The options must not be presented as exhaustive if “both/neither/another event” remains possible. They do not license “Ты, наверное, боишься одиночества или перемен?”: that supplies candidate psychological content the user did not state. O-M02 concerns ready-made solutions, while O-M05–06 and O-AI03 prohibit supplying candidate states, reasons, answers or forced choices after «я не знаю».

`uncertainty_guard` therefore accepts a short no-question response and forbids choosing a conversation or supplying candidate internal states. `rejected_hypothesis_guard` accepts the user's boundary and forbids returning to the assistant-originated husband explanation. Neither guard is an invitation to demand a clarification. Current explicit correction in `corrected_referent` and `direct_user_clarification` has priority over an earlier assistant guess (O-M04, O-AI09).

## Later evaluator mapping (no scoring change here)

- **Contextual specificity:** credit an explicit or natural antecedent used without invented detail; do not require a referent question in `NATURAL_INFERENCE_ACCEPTABLE` cases.
- **Question quality:** credit a question that identifies the unresolved referent when needed; a “what else/how different?” question does not repair a prior ungrounded selection. `CLARIFICATION_PREFERRED` permits an equally grounded neutral response.
- **Client authorship:** penalize insisting on a referent after correction or making a balanced referent choice materially reshape the user’s account; do not penalize a modest natural inference solely because another logical reading exists.
- **Unsupported interpretation:** reserve hard concern for explicit contradiction, invented psychological/causal meaning, or an ungrounded selection that materially changes the answer. Ordinary temporal or contrast inference is not automatically a hidden-state claim.
- **Naturalness:** avoid routine “who/what do you mean?” interrogation of clear pronouns and ordinary ellipsis; allow concise clarification in the rare required case.

These are conceptual mappings for future evaluator work. No evaluator rubric, score, prompt, runtime path, or canonical dialogue changes accompany this fixture set.
EOF'