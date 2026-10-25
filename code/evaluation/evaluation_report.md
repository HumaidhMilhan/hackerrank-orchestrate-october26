# Evaluation report

## Measured public sample results

Requests: 32. These are public sample measurements, not hidden 518-case accuracy.

| Metric | Result |
| --- | ---: |
| status accuracy | 90.625% |
| exact row accuracy | 28.125% |
| step precision | 94.872% |
| step recall | 76.684% |
| step f1 | 84.814% |
| field accuracy | 60.334% |
| sequence accuracy | 28.125% |

Exact step matches: 148 / 156 predicted and 193 expected.
Aligned field matches: 832 / 1379.

Step comparison excludes step_no but retains all other fields including evidence IDs. Field comparison uses aligned array positions; missing steps count as seven mismatches. Sequence comparison includes every field and array order. JSON key order and whitespace are ignored.

## Independent custom cases

### custom-negation: Multilingual explicit non-deletion

French negation must precede affirmative deletion stems.

Expected status: NOT_APPLICABLE; actual: NOT_APPLICABLE; passed: True.
Expected ordered operations: .
Actual ordered operations: .

### custom-replica: Primary absent, replica present

A primary absence cannot erase replica presence; cite replica-source.

Expected status: INCOMPLETE; actual: INCOMPLETE; passed: True.
Expected ordered operations: REPORT_REMAINING_RECORD, DELETE_RECORD, VERIFY_RECORD_ABSENT.
Actual ordered operations: REPORT_REMAINING_RECORD, DELETE_RECORD, VERIFY_RECORD_ABSENT.

### custom-tombstone: Tombstone exposes an email hash

Keep the stable subject reference; redact the exposed hash.

Expected status: INCOMPLETE; actual: INCOMPLETE; passed: True.
Expected ordered operations: REPORT_EXPOSED_PII, REDACT_RECORD, VERIFY_RECORD_REDACTED.
Actual ordered operations: REPORT_EXPOSED_PII, REDACT_RECORD, VERIFY_RECORD_REDACTED.

### custom-cutoff: Ignore an after-cutoff capture

A later capture is ineligible even when its embedded observation time is earlier.

Expected status: COMPLETE; actual: COMPLETE; passed: True.
Expected ordered operations: VERIFY_RECORD_ABSENT.
Actual ordered operations: VERIFY_RECORD_ABSENT.

### custom-recreation: Disable flows and block restores before cleanup

The canonical operation order stops flows/restores before record deletion.

Expected status: INCOMPLETE; actual: INCOMPLETE; passed: True.
Expected ordered operations: REPORT_REMAINING_RECORD, REPORT_ACTIVE_DATA_FLOW, REPORT_RESTORE_RISK, DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE_RECORD, VERIFY_RECORD_ABSENT, VERIFY_DATA_FLOW_DISABLED, VERIFY_RESTORE_BLOCKED.
Actual ordered operations: REPORT_REMAINING_RECORD, REPORT_ACTIVE_DATA_FLOW, REPORT_RESTORE_RISK, DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE_RECORD, VERIFY_RECORD_ABSENT, VERIFY_DATA_FLOW_DISABLED, VERIFY_RESTORE_BLOCKED.

## Uncertainty policy comparison

Both policies reuse saved assessments without new model calls.

| Policy | Status accuracy | Exact row | Sequence |
| --- | ---: | ---: | ---: |
| best-evidence | 90.625% | 28.125% | 28.125% |
| incomplete | 90.625% | 28.125% | 28.125% |

The configured default remains best-evidence. This comparison does not automatically select per-case answers or change policy. Review false COMPLETE cases before applying a general conservative rule; parser/identity/policy errors must be fixed at their source.

## Failures found and improvements made

Implementation separates primary and replica scopes, checks capture and observation cutoffs, distinguishes operation claims from direct reads, uses scoped multilingual negation before deletion stems, preserves tombstone references, and applies canonical operation ordering. These mechanisms are covered by independent tests rather than hardcoded sample labels.

The implementation review found six defects, reproduced with fictional regression cases and fixed: shared-phone attribution, structured/reverse resource links, partial payloads or treatment labels accepted as compliance proof, invalid intent responses cached before validation, unread PDF pages cached as successful extraction, and retained-only/unknown-payload flows treated as prohibited copies. Integration regression checks also enforce the required archive-root report paths and prevent system names in activity prose from becoming cross-subject resource links. Provider regression checks cover exponential backoff/jitter, permanent-error handling, retry-budget ownership, and server-directed cooldowns. Async scheduler tests cover rolling RPM/input TPM, shared concurrency, shutdown during backoff, all SDK operations, retry admission, real-SDK transport ownership and sanitized quota diagnostics. Groq tests additionally cover role routing, confidence-based independent review, persistent daily quotas, queued cooldowns, cancellation-owned physical permits, and per-model usage/costs. The suite now includes 94 tests; live interpretation remains source-grounded and rejected observations retain scoped uncertainty. See calibration_report.md for the current measured acceptance runs.

Remaining measured failures:

| Case | Expected status | Actual status | Sequence correct | Expected/actual steps |
| --- | --- | --- | --- | --- |
| case_01 | COMPLETE | INCOMPLETE | False | 1/0 |
| case_02 | COMPLETE | INCOMPLETE | False | 1/0 |
| case_03 | COMPLETE | COMPLETE | False | 3/2 |
| case_04 | COMPLETE | INCOMPLETE | False | 2/0 |
| case_07 | INCOMPLETE | INCOMPLETE | False | 4/6 |
| case_08 | INCOMPLETE | INCOMPLETE | False | 4/3 |
| case_09 | INCOMPLETE | INCOMPLETE | False | 5/3 |
| case_10 | INCOMPLETE | INCOMPLETE | False | 4/3 |
| case_17 | INCOMPLETE | INCOMPLETE | False | 5/7 |
| case_18 | INCOMPLETE | INCOMPLETE | False | 14/10 |
| case_20 | INCOMPLETE | INCOMPLETE | False | 8/4 |
| case_21 | COMPLETE | COMPLETE | False | 3/1 |
| case_22 | INCOMPLETE | INCOMPLETE | False | 8/7 |
| case_23 | INCOMPLETE | INCOMPLETE | False | 8/6 |
| case_24 | INCOMPLETE | INCOMPLETE | False | 7/6 |
| case_25 | COMPLETE | COMPLETE | False | 3/1 |
| case_26 | COMPLETE | COMPLETE | False | 6/4 |
| case_27 | COMPLETE | COMPLETE | False | 6/4 |
| case_28 | COMPLETE | COMPLETE | False | 6/4 |
| case_29 | INCOMPLETE | INCOMPLETE | False | 14/10 |
| case_30 | INCOMPLETE | INCOMPLETE | False | 14/10 |
| case_31 | COMPLETE | COMPLETE | False | 3/2 |
| case_32 | INCOMPLETE | INCOMPLETE | False | 5/4 |

No live-provider/vision quality is claimed by an offline run. API credentials, configured model IDs, unread media, attribution gaps, and equivalent-proof citation choices can affect these results. See run diagnostics for estimated/fallback cases. Hidden evaluation answers were not accessed. Status agreement alone is not complete plan correctness.
