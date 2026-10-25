# Exact ordered-step calibration — 25 October 2026

## Acceptance result

**The requested greater-than-80% full ordered-array target was not reached.** That gate requires at least 26 of 32 complete arrays to match. The measured result remains **9/32 (28.125%)**. Deletion-status accuracy remains **29/32 (90.625%)**.

The changes improve exact individual-step matches from **148 to 159**. Individual-step F1 is **89.326%**, but that is a different metric and is not substituted for the requested whole-array gate.

| Metric | Before this change | After |
| --- | ---: | ---: |
| Full ordered arrays | 28.125% | 28.125% |
| Deletion status | 90.625% | 90.625% |
| Exact individual-step precision | 94.872% | 97.546% |
| Exact individual-step recall | 76.684% | 82.383% |
| Exact individual-step F1 | 84.814% | 89.326% |
| Aligned field accuracy | 60.334% | 69.752% |

Final standard live CLI run: 98.5 seconds, 32 rows, no processing errors. It made 10 hosted 20B calls; rejected observations stayed unknown. The deterministic offline replay gives the same measured step scores. Model observations do not define final verdicts or step ordering.

## Patterns that are supported by the evidence

- Canonical sorting is already correct: FINDING, REMEDIATION, VERIFICATION; each phase follows the required operation order, then system_id and resource_id. The baseline comparison found **zero ordering-only mismatches**.
- Active, subject-scoped identity bridges and customer-event connectors can recreate personal data. Their source records may identify the subject using customer_email instead of subject_selector. Those paths now produce the supported finding, DISABLE_DATA_FLOW, and verification. Explicit retained-only payload scope still wins; an unscoped enabled flag stays unknown.
- A legacy contact-index lookup is an identifier store, not a retained conversation. Query source/type metadata is preserved only within that read. It receives DELETE treatment under SECONDARY_IDENTIFIER; shared support conversations keep REDACT. Explicit record_type takes precedence over purpose heuristics.
- Query metadata is reset on a new read, resource or service boundary. A reused trace cannot make a later support conversation inherit SECONDARY_IDENTIFIER and be deleted.
- A catalog identity alias alone does not establish a record treatment plan. Its uncertainty remains in the verdict/diagnostics. Actual worker-operation targets still retain their future verification.
- Distinct resource IDs retain independent checks. A newer absence of a different account cannot replace an older account’s required verification, especially when an archive can recreate the older account. No unsupported historical deduplication remains.
- Remaining-data findings, remediation and verification stay generated from policy/state templates. No case IDs, sample answer lookup, row-position mapping or resource-number rules were introduced in prediction code.

## Why complete arrays still differ

The evaluation-only audit found **22 cases with reference resources unreachable through the supplied cutoff-eligible identifier/resource links**, even after traversing the explicit graph to closure. This is not merely an ordering issue. It is also not a proof that every imaginable semantic interpretation is impossible; the finding identifies the missing grounding that the current data/rules provide.

Examples:

| Case | Reference resource | Grounding gap |
| --- | --- | --- |
| case_01 / case_02 | account_001 / account_002 | SQL has zero subject matches; the operation targets have no subject identifier or eligible ownership binding. |
| case_03 | analytics_9406 | Eligible readback is anonymous; the anonymization activity names the resource without its former owner. |
| case_04 | account_004 / analytics_901 | No account binding; analytics identity fields are all null and no earlier ownership edge is supplied. |
| case_24 | audit_record_7095 | Ownership record found only in evidence_02, captured after audit_at. The reference step is future verification with an empty evidence_id, not an invalid citation to evidence_92. |
| case_25 | account_3136 / analytics_1895 | Eligible export contains the absence/anonymous rows with no subject identifiers. |
| case_26 | account_5684 / analytics_4566 | Current export rows have no owner; another snapshot containing ownership was captured after the cutoff. |
| case_31 | account_4857 | Eligible activity names an operation target but has no subject ownership link or confirming account observation. |

All missing array resources from the link audit:

| Case | Unlinked reference resources |
| --- | --- |
| case_01 | account_001 |
| case_02 | account_002 |
| case_03 | analytics_9406 |
| case_04 | account_004, analytics_901 |
| case_07 | account_007 |
| case_08 | account_008 |
| case_09 | account_3960, audit_record_4902 |
| case_10 | account_010 |
| case_18 | account_5521, audit_record_6645 |
| case_20 | account_5037, audit_record_5569 |
| case_21 | account_6440, analytics_5335 |
| case_22 | account_4990 |
| case_23 | account_410, audit_record_4128 |
| case_24 | audit_record_7095 |
| case_25 | account_3136, analytics_1895 |
| case_26 | account_5684, analytics_4566 |
| case_27 | account_3866, analytics_4574 |
| case_28 | account_5482, analytics_6077 |
| case_29 | account_7012, audit_record_3954 |
| case_30 | account_4163, audit_record_1707 |
| case_31 | account_4857 |
| case_32 | account_8858 |

The source-content citation check found no invalid nonempty evidence citations. An earlier commentary description of case_24 as a citation error was corrected: the problem is availability/ownership at the cutoff, not a nonempty incorrect citation.

The three unresolved statuses were replayed again. Their model and fallback intent is DELETION, identities resolve, and retrieval still returns zero subject-linked observations. No API error or language classifier caused these three outputs.

Some extra steps also have independent supporting evidence. For example, object_19 is a listed delivery_confirmation_19.pdf object with a catalog ownership link. support_001 is delivery_address_correction.pdf, with a different size and checksum prefix in the supplied PDF. They are not interchangeable copies without an explicit equivalence/deletion-scope proof. Dropping the object finding solely to fit the sample would hide supported data.

## Verification and limits

- 151 tests pass, including 11 new fictional exact-step/query-metadata/risk regressions and 3 atomic-write regressions.
- Independent review found stale trace-type inheritance and unsafe cross-resource absence deduplication; both reproductions were fixed and reverified.
- The isolated final-code 518-row offline contract run passed in 11.7 seconds with no logged errors and no hosted calls. This is a schema/coverage check, not a hidden-accuracy claim. Two earlier runs encountered temporary Windows checkpoint sharing denials; retrying the same replacements later succeeded. A bounded atomic-replacement retry now covers checkpoint JSON and final CSV writes. Persistent denials still raise an error and preserve the prior artifact.
- Public answers remain evaluator-only. Participant data, canonical full output.csv and its existing full-run usage report are preserved. sample_predictions.csv and the public evaluation report are refreshed.
- The input would need additional cutoff-eligible subject-to-resource bindings, including pre-anonymization ownership, to ground the missing exact checks. Inferring those IDs from case numbers, assigning anonymous rows by order, or using later captures is not implemented.
- Complete-array scores are measured on the same 32 examples used for calibration and are not a held-out result.

Artifacts: .runtime/step-optimization/diffs.json, grounding-audit.json, final-metrics.json, live.log and the fictional regression logs. The strict 80% gate is explicitly left unmet rather than reporting individual-step F1 as whole-array accuracy.
