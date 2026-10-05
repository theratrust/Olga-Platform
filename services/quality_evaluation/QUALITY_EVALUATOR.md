# Offline response quality evaluator foundation

The methodology evaluator checks method fidelity/safety using HF01–HF08. The
independent response quality evaluator checks derived product criteria: specificity,
progression, repetition, naturalness, question quality and proportionality.
A methodologically valid response can still have weak product quality. Quality
cannot certify safety, override method findings or execute routing.

All quality criteria and synthetic labels are derived_product_quality_criteria,
not direct Olga statements. The Russian rubric is knowledge/evaluation/качество_ответов_оценка.md.
No canonical method file, methodology gold expectation, coaching prompt or runtime
is imported or altered. No GLM output was used to generate labels.

The package has a strict deterministic contract and a standalone specification-loaded
Russian prompt. The 22 Russian synthetic cases include multi-turn structures,
appropriate one-off reflection, justified repetition, no-question responses and
material context gaps. Recent pattern hints are optional untrusted metadata, not
quote evidence. The contract proves shapes, anchoring and declared consistency;
it does not perform NLP, infer semantic scores or independently prove flag truth.

Run the corpus without a model:

```sh
python3 -B tests/run_response_quality_cases.py
```

The runner exits nonzero on invalid envelopes/results. Unit tests are in
tests/test_response_quality_evaluator.py. Only standard-library runtime dependencies
are used; no adapter, model runner, worker, API credentials or network path exists.
This is a qualification foundation, not model qualification evidence. Future model
qualification would require separate authorization and compare dimension/flag/context
labels independently; no runtime integration or methodology gold import is needed.
