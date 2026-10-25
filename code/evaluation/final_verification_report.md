# Final verification — 25 October 2026

## Scope

The existing four stages, CLI flags, provider routing, async quota queues and cache/checkpoint layout are preserved. The six-step user workflow is the verification checklist. No dataset, organizer truth, golden-label lookup, case-number mapping or resource-number inference is used by prediction code.

## Verified corrections

- Scoped negation and marketing-only removal precede affirmative multilingual deletion stems. Nominal negation and correction without removal are recognized. Separate invoice/billing restrictions do not suppress affirmative account deletion. The final default is NON_DELETION with a warning.
- Both model intent routes share the six-language instructions and grounded phrase/ID requirements. A twenty-case regression covers duplicate, missing and invented-phrase responses. Independent review does not receive the primary answer.
- Trace joins preserve owner_key and reset at read/resource/service boundaries. Regional, read, failover and reporting replica scopes remain distinct.
- JSON observations retain null versus missing, record event times and every containing timestamp. A child or precedence-selected timestamp cannot admit a future/invalid containing source.
- An explicit unblocked archive is a restore risk; explicit denial/block/restore flags and conflicting eligibility are resolved before asserting risk.
- The effective Groq native vision prompt requests all table rows and the right selected-record inspector, without attaching panel fields to neighboring rows or making policy verdicts.
- The usage writer reports per-model attempts, accepted/truncated/failed calls, local quota skips, retries, known token totals and per-request averages. Unknown costs/usage remain disclosed.

## Public samples

| Metric | Result |
| --- | ---: |
| status_accuracy | 90.625% |
| exact_row_accuracy | 28.125% |
| step_precision | 97.546% |
| step_recall | 82.383% |
| step_f1 | 89.326% |
| field_accuracy | 69.752% |
| sequence_accuracy | 28.125% |

All 32 arrays were compared field by field. There are zero ordering-only mismatches. Three statuses remain different: case_01, case_02 and case_04. Their authorization is DELETION and their identities resolve, but cutoff-eligible subject-linked state evidence is absent. No positive absence or ownership was invented.

The 23 differing arrays consist of 22 cases with reference resources outside the explicitly grounded ownership graph and one case with an independently supported extra historical-resource verification. case_07 also retains an independently supported storage object, rather than merging different filenames. See exact_step_report.md and three_case_rootcause.md. This is an explicit-link audit, not proof that every possible semantic interpretation is impossible.

The >80% full ordered-array gate remains unmet (9/32; at least 26/32 required). Individual-step F1 is not substituted for that gate. Sample calibration metrics do not estimate hidden-set accuracy.

Live sample run: 226.1 seconds, 32 rows, zero processing errors, 20 hosted calls, 18,977 known tokens. A fresh deterministic offline replay of the latest code produces the same sample metrics and no hosted calls.

## Tests and extraction audit

161 regression tests pass in both the working environment and the environment installed from requirements.lock. pip check reports no broken requirements. All five independent custom fixtures pass.

The manifest contains 94 evidence files: 24 SQL, 28 JSON, 26 logs, 11 PNGs, four PDFs and one TXT. Direct deterministic parsing audited 891 SQL observations, 890 JSON observations and 1,072 log observations. SQL uses isolated in-memory databases and preserves replica scopes. Media success remains contingent on grounded observation validation.

An isolated latest-code offline full contract run wrote 518 rows: 376 INCOMPLETE, 132 COMPLETE, 10 NOT_APPLICABLE, 30 estimated, zero processing errors. All ten specified non-deletion requests have empty step arrays. This is coverage/schema validation, not hidden accuracy.

## Rulings and limits

1. Twenty-case batches are tested and used via a process-local override for the requested live verification runs. The environment-configurable default of four and the saved .env are preserved. Cost: 20-case calls can hit the fixed 512-token cap and incur bounded split recovery and quota waits.
2. Missing SQL rows prove absence only under a grounded exhaustive population/table contract and a known resource binding. The supplied snapshot_scope declares system/time, not exhaustive subject coverage. Cost: some reference absence checks remain unknown rather than guessing a batch membership.
3. Keep the later approved conservative material-UNKNOWN/observer-failure gate over the original best-evidence draft. Cost: a case cannot become COMPLETE merely from partial compliant evidence.

Deferred minor: the existing cross-scope equivalent-evidence tie chooses descending evidence IDs while same-scope ties use ascending IDs. The result is deterministic and citations remain valid; this pass does not change that prior behavior.

## Final live full run

Stopped before output generation for the subsequent user-requested temporal-linkage investigation. Prior root output is preserved; no final live full-run success is claimed yet.
