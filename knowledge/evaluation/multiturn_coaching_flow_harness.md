# Multi-turn coaching flow harness

## Scope and provenance

This diagnostic evaluates one frozen DEV conversation for each of six synthetic Russian user trajectories in `tests/fixtures/multiturn_coaching_flow_scenarios.json`. These are authored test dialogues, not real Olga transcripts. Assistant turns are generated live; the fixture contains no expected wording or single correct response. The user turns are fixed, so a later user turn may not directly answer the assistant's preceding question. Reviewers must distinguish that limitation from a bot continuity error.

`knowledge/method/источник_истины_метода_Ольги.md` supplies the source IDs. Its B layer records validated project method rules, while its C layer records derived operational rules; neither is a fresh primary interview. The nine-stage map and eight example dialogues are derived product material, not Olga's recorded process. The source-of-truth gap audit and the three prior single-turn analyses inform risk selection, not new method doctrine. Trajectory ratings, question utility, pacing, monotony, and an acceptable-turn threshold are **product-quality criteria**, not claims personally validated by Olga. No numeric score is computed.

The six trajectories cover relocation identity, repeated «я не знаю», rejected interpretation with later user-led reopening, rich reflection with one true ambiguity, answered-question correction, and partner/work/autonomy tradeoffs. Existing turn-selection, hypothesis-grounding, and referent-grounding fixtures supplied reusable boundary concepts; the new dialogue wording is synthetic and independently written. Each fixture includes a correction or refinement, a substantial user reflection, useful room for a question, and room for a complete no-question reply.

## Frozen run path

1. Confirm checkout branch `feature/method-core`, model `z-ai/glm-5.2`, `DEFAULT_MAX_TOKENS=350`, and zero tracked prompt/runtime changes. Work only in `/opt/olga-coaching-dev`; do not access PROD, Telegram handlers, or the running DEV database.
2. Build the current system instruction through `services.coaching_generator.build_system_instruction(first_name='Тест', archetype=None)`. This selects the existing prompt and method core with no candidate variant.
3. For each scenario independently, append its next user message to a local ordered list and assign synthetic ascending source IDs. Mirror the DB's latest-20 read with `rows[-20:]`, pass full local rows plus that raw window to `services.conversation_state.build_carry_forward`, render with `render_runtime_memory`, and call `build_messages` then `generate_candidate` with `max_tokens=350`. Append the actual assistant text to that same scenario's list before the next user turn. No evaluator runs during generation.
4. Retry only an exception, missing content, or blank output. Record every attempt, error kind, and retry. If the technical failure persists, retain an explicit incomplete turn and stop that scenario rather than fabricating assistant text.
5. Write a manifest, six transcripts, a manual review, and a report beneath `artifacts/evaluation/multiturn-coaching-flow/<run_id>/`. Keep this directory untracked and do not stage it.

`raw_history_size` is the number of messages **before** the generator request, before latest-20 truncation. At user turn 11 in an otherwise complete 11-turn scenario, it is 21 and the boundary begins. Record the event objects or their source IDs and types for every turn. A change around that point is descriptive evidence only; it cannot establish causation from one trajectory.

## Human review contract

Each assistant turn receives exactly one classification: `GOOD`, `MINOR_ISSUE`, `METHOD_VIOLATION`, or `QUALITY_FAILURE`. It may receive zero or more of: `USEFUL_QUESTION`, `OPTIONAL_QUESTION`, `LOW_VALUE_QUESTION`, `GOOD_NO_QUESTION`, `UNSUPPORTED_INTERPRETATION`, `UNSUPPORTED_CAUSAL_CLAIM`, `CANDIDATE_AFTER_UNKNOWN`, `REJECTED_IDEA_REOPENED`, `PARTNER_BLAME`, `WORK_AS_SOLUTION`, `CLIENT_AUTHORSHIP_PRESSURE`, `REPETITION`, `IGNORED_USER_CORRECTION`, `LOST_CONTEXT`, `OTHER`. A question tag describes the question actually asked; no-question turns can receive `GOOD_NO_QUESTION`. `REJECTED_IDEA_REOPENED` flags bot-led reopening before user initiative, not the legitimate later return initiated by the user. Record brief quoted evidence and refer to prior turn numbers where the issue is longitudinal.

For each complete scenario, rate `CLIENT_AUTHORSHIP`, `GROUNDING`, `CONTINUITY`, `PROGRESSION`, `QUESTION_DISCIPLINE`, `INTERPRETATION_DISCIPLINE`, `PACING`, and `OVERALL_COHERENCE` as `GOOD`, `MIXED`, or `POOR`, with a reason. Explicitly answer: **If I removed the locally plausible wording and looked only at the trajectory, did the conversation actually become more useful and more owned by the user?** A fixed user script can supply progression independently; credit the bot only for how it handles that progression.

Count all ending-in-question turns and no-question turns, question utility tags, method violations, specific guardrail tags, repetition, context loss, and incomplete/error outputs, both per scenario and in aggregate. An assistant turn ending in a question is a text-ending property; a question embedded earlier in the same reply should still receive a utility tag. Tag each substantive question once. Track repeated patterns A–J from the task brief across scenarios, including reflect→question loop, depth pressure, global loop, context drift, authorship erosion, false resolution, monotony, premature action, partner/work default, and overloaded turn. Do not mistake one local issue for a systematic pattern.

## Offline evaluator audit and decision

Inspect `knowledge/evaluation/метод_Ольги_оценка.md` and `knowledge/evaluation/качество_ответов_оценка.md` against observed failures. They permit good no-question responses and specify local grounding/quality checks, but the review must test whether their current inputs and dimensions would expose long-range loops, semantic repetition, authorship erosion, and false progression. Do not call either evaluator or change its scoring in this run.

Choose exactly one verdict: `CURRENT MULTI-TURN BEHAVIOR ACCEPTABLE`, `ONE DOMINANT TRAJECTORY DEFECT IDENTIFIED`, `MULTIPLE SYSTEMATIC TRAJECTORY DEFECTS IDENTIFIED`, `SINGLE-TURN QUALITY IS GOOD BUT MULTI-TURN COHERENCE IS WEAK`, or `HARNESS NEEDS REVISION`. Name at most two defects for future work. This diagnostic does not authorize a prompt or runtime change.
