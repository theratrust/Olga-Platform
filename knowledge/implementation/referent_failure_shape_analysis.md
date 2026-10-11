# Referent failure shape: original versus temporary fixtures

Static analysis, 11 October 2026. No new generator or evaluator calls. Sources: `ambiguous_referent_analysis.md`, the four saved evaluation runs listed below, `tests/fixtures/turn_selection_cases.json`, `artifacts/evaluation/referent-narrow-ab/temporary_cases.json`, and the method truth set. All examples are synthetic. The earlier response labels are observations under a deliberately strict referent standard, **not** proof of a user-facing method violation.

## Finding in brief

The candidate's apparent improvement is largely a **fixture-shape effect**. The three temporary targets pose visibly unresolved reference choices: a singular “тот разговор” after two parallel talks, “она” after two women, and “этому” after two distinct topics. The two originals allow ordinary discourse readings that the strict labels treat as errors: “а потом ... Это было по-другому” readily invites comparison with the later talk, and “два разговора ... После этого” can refer to the combined sequence. The model often commits to those readings and asks what changed, rather than asking which event is meant. That can be overconfident in some contexts, but the originals do not establish that clarification is always required. No previous assistant message primes any of the five contexts.

## Fixture structure

All five target contexts contain **one prior user message followed by one latest user message**, with no assistant turn, no missing history, and no ledger event. The possible referents are therefore equally close in message distance; their **order, syntax, and lexical salience** differ.

| Fixture | Prior candidates and distance | Latest form | Lexical/discourse cue | Plausible ambiguity | Assistant anchor? |
|---|---|---|---|---|---|
| `referent_ambiguous` (original) | Sister listening without advice; **then** talk with manager. Both in immediately preceding user sentence. | «Это было по-другому.» | «а потом» orders events; «по-другому» calls for a comparison; sister event has more detail, manager event is most recent. | Second talk versus first talk versus comparison of the two. The contrast makes the second talk a **reasonable, though not certain**, reading. | No. |
| `unresolved_referent` (original) | “Two conversations” with sister and manager in one immediately preceding user sentence. | «После этого стало иначе.» | «После этого» may point to the described sequence; no named property changed. | After one talk, after both, or after that day/sequence. Aggregate reading is ordinary Russian anaphora. | No. |
| `two_recent_conversations` (temporary) | Separate talk with sister and manager, parallel mention in preceding user sentence. | «Тот разговор оказался важным.» | Singular noun phrase repeats shared category «разговор»; no temporal contrast or unique descriptor. | Which of two talks? Stronger balanced choice. | No. |
| `ambiguous_person` (temporary) | Sister and friend, both feminine, in preceding user sentence. | «Она сказала, что не хочет продолжать разговор.» | Pronoun agrees with both; no intervening event or distinctive property. | Which woman spoke? Direct identity question is salient. | No. |
| `topic_switch_eto` (temporary) | Work with sister; trip with friend, in preceding user sentence. | «Теперь хочу вернуться к этому.» | Work/trip are lexically distinct topics; «вернуться» names no topic. | Which topic (or both)? A topic choice rather than an event comparison. | No. |

The candidate wording itself enumerates “людям, событиям или разговорам”. That mirrors the temporary **person** and **conversation** contrasts particularly closely. The original “после этого” instead invites a **whole-sequence** reading; the original “по-другому” invites contrast completion. Neither is a simple equal-salience two-option choice. This is a plausible mechanism for the candidate's different apparent performance, not causal proof from a small stochastic sample.

## Response inventory and mechanism coding

The baseline supplies one response to each original, the replication five to `referent_ambiguous`, the earlier turn-selection A/B supplies three per original per arm, and the referent A/B supplies three per original per arm. Thus there are **31 saved original-target responses**: 18 for `referent_ambiguous`, 13 for `unresolved_referent`. Under the prior strict manual labels, **26/31** were unsupported assumptions (15/18 and 11/13 respectively), 5/31 safe neutral, and 0/31 targeted “which referent?” clarifications. The narrow referent A/B itself was 5/6 unsupported for these two fixtures in **both** arms. Across the 31 responses, 24 contain a question mark, but none explicitly asks which conversation or which preceding event “это/после этого” denotes. Those counts include experimental arms and are **not** a frozen-prompt failure rate.

Mechanism tags below apply only to those **26 previously labeled unsupported** responses. They can overlap. `OPTION_SELECTION` means the model itself selected one already mentioned referent; it is separate from a clarification question that names options.

| Mechanism | Count | Evidence / limit |
|---|---:|---|
| `RECENCY_ANCHOR` | 7 | Explicitly selects the second/manager conversation in `referent_ambiguous`: replication `_1`–`_3`; previous A/B `_2_A`, `_1_B`; referent A/B `_3_A`, `_1_B`. This is **user-sentence** recency, not assistant priming. |
| `ASSISTANT_WORDING_ANCHOR` | 0 | The contexts have no preceding assistant message. The assistant's *own* response can compound its first assumption, but cannot be the input anchor here. |
| `CONTRAST_COMPLETION` | 15 | Every strictly labeled `referent_ambiguous` failure turns «по-другому» into an unconfirmed comparison, sometimes assigning it to the second talk. |
| `WORLD_KNOWLEDGE_FILL` | 0 | No failure depends on external knowledge about a sister, manager, or their likely behavior. |
| `OPTION_SELECTION` | 7 | The same seven second/manager selections counted under recency; no response selected the sister as the sole referent. |
| `OTHER` | 11 | Every strictly labeled `unresolved_referent` failure changes singular/whole-sequence «после этого» into «после них/этих двух разговоров». This **aggregate or pluralizing resolution** is the distinct recurring shape. |

The other five original-target responses preserve the uncertain link. The two mechanism families are visible in the text: the original baseline `referent_ambiguous` says the talks “были по-разному”; its replication `_2` says the manager talk was different; the original baseline `unresolved_referent` says “после них”. In the new A/B, `referent_ambiguous_1_B` again selects the manager, while all three `unresolved_referent` B responses refer to both talks. This is **not** an assistant-wording effect, because all fixture histories contain only user turns.

### Question form: “which?” versus “what else?”

The model commonly treats clarification as requesting more detail **after** a referent has been assumed. “Что именно было по-другому?” asks about the nature of a difference. It does not decide whether the user meant the manager talk, sister talk, or their comparison. “Что именно стало иначе?” similarly leaves the temporal referent untouched, sometimes following “после них”. An interrogative sentence therefore does not repair an unsupported factual preamble. The current runtime prompt offers both «уточнить смысл» and «углубить тему, которую обозначил сам человек» (`prompts/coaching.py` §7), and says a question should explore the user's own topic (§8). It does **not** require question frequency or explicitly distinguish “which referent?” from “what aspect?”. This could permit the observed detail-seeking pattern; the artifacts cannot prove the prompt wording caused it.

## Are the fixtures diagnosing the same error?

The three temporary targets are cleaner **referent identity tests**, although their almost schematic wording makes the ambiguity more conspicuous. `two_recent_conversations` uses a singular noun after two parallel instances; `ambiguous_person` uses a shared-gender pronoun; `topic_switch_eto` has two named topics and no “after/otherwise” bridge. Under the referent A/B, candidate B produced targeted clarifications in 9/9 temporary target responses, compared with A's 3/9 targeted clarifications and 2/9 strict assumptions. Their ease makes B's aggregate improvement look stronger than its result on natural discourse-level ambiguity. They remain valid contrastive cases; they are not a representative estimate of real chat frequency.

The originals are plausible user language but **too strict as binary CLARIFY_REQUIRED fixtures**. For `referent_ambiguous`, “а потом” plus “по-другому” makes a manager-versus-sister contrast a natural inference. A human could reasonably read it that way, while still being able to ask which experience the user meant. For `unresolved_referent`, the immediately preceding sentence packages the two talks as one episode; “после этого” can naturally mean after that episode. “После них” need not assert that **both caused** the change; it can merely locate it after both. A response that builds unsupported psychological meaning on that reading would be a separate failure, but the saved responses mostly restate the temporal/contrast relation. The prior strict U labels should therefore be interpreted as **referent-precision flags**, not unequivocal method hard failures. Both originals need a clearer expected-response boundary before being used as decisive prompt-selection targets.

### Minimal textual contrasts to examine later (not fixture edits)

| Original | A. Clearly resolved | B. Clearly ambiguous | C. Neutral response needs no resolution |
|---|---|---|---|
| `referent_ambiguous` | Replace latest with «Разговор с начальником был по-другому.» | Replace latest with «В одном из этих разговоров всё было по-другому.» | Append «Пока не хочу уточнять, о каком разговоре.» Acknowledge only the stated difference. |
| `unresolved_referent` | Replace latest with «После разговора с начальником стало иначе.» | Replace latest with «После одного из этих разговоров стало иначе.» | Append «Пока не хочу уточнять, после какого именно.» Acknowledge change without an event assignment. |

These are proposed analytic contrasts, not canonical answers or permanent fixtures. Variant B removes the natural aggregate/contrast shortcut and makes the identity uncertainty explicit; variant C tests whether the model can leave it open without pressuring the user.

## Named referents in clarification questions

“Ты про сестру или подругу?” in the temporary `ambiguous_person` B responses names **two people the user already introduced**. Likewise “к работе или поездке?” refers to explicit prior topics. This is different from offering candidate feelings, motives, reasons, or answers that the user never supplied. The method truth set's O-M02 concerns ready-made **solutions**; O-M05–06 and O-AI03 forbid filling «я не знаю» with candidate psychological states or choices. Neither source imposes a universal **open-question-only** rule for identifying already mentioned entities. Such a named-referent question can be compatible with client authorship if it remains a genuine question and leaves room for “neither/both/something else”. An open “Кого ты имеешь в виду?” is less constraining stylistically, but is a design preference, **not** a proven Olga requirement. The earlier A/B report's option concern should not be counted as a hard violation. If the user had said «я не знаю», the hard uncertainty rule would still bar supplying candidate states/reasons/options to fill that uncertainty; referent clarification must not be used as a workaround.

## Source-of-truth boundary

O-M04 (client authorship), O-M10 (follow the user's words), and O-AI04 (grounded reflection) support caution when a referent is **materially unresolved**. O-M07 forbids unsupported interpretation as established psychological truth, but a plausible event link is not automatically a hidden-state attribution. O-M12 and O-AI08 permit a neutral or no-question answer. O-AI09 gives current user words priority over derived memory; no memory is involved in these two-message contexts. The specific threshold “multiple plausible referents materially change the answer, therefore clarify” remains an **operational design choice**. None of these IDs demands clarification of every pronoun or forbids reasonable conversational inference.

## Recommendation

**ORIGINAL FIXTURES TOO STRICT / NEED REVISION.** Their discourse cues make the model's predominant readings plausible enough that the existing binary unsupported-assumption labels overstate method failure. The temporary fixtures are easier but valid tests of more explicit ambiguity; they do not demonstrate that the candidate solves the original shape. Do **not** make another prompt experiment yet. First, in a separate fixture-review task, establish adjudicated expectations for the two originals (acceptable natural inference, safe neutral, and actual unsupported commitment), then test the minimal A/B/C textual contrasts above. Only if a revised, genuinely balanced original-like case repeatedly produces an unsupported *material* commitment despite full context would a new narrow prompt experiment be justified. No runtime-context change is indicated by these two-message fixtures.
EOF'