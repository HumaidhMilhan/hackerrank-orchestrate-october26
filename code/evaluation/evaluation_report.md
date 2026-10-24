# Evaluation report

## Measured public sample results

Requests: 32. These are public sample measurements, not hidden 518-case accuracy.

| Metric | Result |
| --- | ---: |
| status accuracy | 90.62% |
| exact row accuracy | 15.62% |
| step precision | 94.41% |
| step recall | 78.76% |
| step f1 | 85.88% |
| field accuracy | 66.50% |
| sequence accuracy | 15.62% |

Exact step matches: 152 / 161 predicted and 193 expected.
Aligned field matches: 917 / 1379.

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
| best-evidence | 90.62% | 15.62% | 15.62% |
| incomplete | 68.75% | 15.62% | 15.62% |

The configured default remains best-evidence. This comparison does not automatically select per-case answers or change policy. Review false COMPLETE cases before applying a general conservative rule; parser/identity/policy errors must be fixed at their source.

## Failures found and improvements made

Implementation separates primary and replica scopes, checks capture and observation cutoffs, distinguishes operation claims from direct reads, uses scoped multilingual negation before deletion stems, preserves tombstone references, and applies canonical operation ordering. These mechanisms are covered by independent tests rather than hardcoded sample labels.

Remaining measured failures:

| Case | Expected status | Actual status | Sequence correct | Expected/actual steps |
| --- | --- | --- | --- | --- |
| case_01 | COMPLETE | INCOMPLETE | False | 1/0 |
| case_02 | COMPLETE | INCOMPLETE | False | 1/0 |
| case_03 | COMPLETE | COMPLETE | False | 3/2 |
| case_04 | COMPLETE | INCOMPLETE | False | 2/0 |
| case_05 | INCOMPLETE | INCOMPLETE | False | 3/4 |
| case_06 | INCOMPLETE | INCOMPLETE | False | 4/3 |
| case_07 | INCOMPLETE | INCOMPLETE | False | 4/3 |
| case_08 | INCOMPLETE | INCOMPLETE | False | 4/3 |
| case_09 | INCOMPLETE | INCOMPLETE | False | 5/3 |
| case_10 | INCOMPLETE | INCOMPLETE | False | 4/1 |
| case_12 | INCOMPLETE | INCOMPLETE | False | 5/5 |
| case_16 | INCOMPLETE | INCOMPLETE | False | 7/8 |
| case_17 | INCOMPLETE | INCOMPLETE | False | 5/7 |
| case_18 | INCOMPLETE | INCOMPLETE | False | 14/12 |
| case_20 | INCOMPLETE | INCOMPLETE | False | 8/6 |
| case_21 | COMPLETE | COMPLETE | False | 3/1 |
| case_22 | INCOMPLETE | INCOMPLETE | False | 8/7 |
| case_23 | INCOMPLETE | INCOMPLETE | False | 8/6 |
| case_24 | INCOMPLETE | INCOMPLETE | False | 7/7 |
| case_25 | COMPLETE | COMPLETE | False | 3/1 |
| case_26 | COMPLETE | COMPLETE | False | 6/4 |
| case_27 | COMPLETE | COMPLETE | False | 6/4 |
| case_28 | COMPLETE | COMPLETE | False | 6/4 |
| case_29 | INCOMPLETE | INCOMPLETE | False | 14/12 |
| case_30 | INCOMPLETE | INCOMPLETE | False | 14/12 |
| case_31 | COMPLETE | COMPLETE | False | 3/2 |
| case_32 | INCOMPLETE | INCOMPLETE | False | 5/4 |

No live-provider/vision quality is claimed by an offline run. API credentials, configured model IDs, unread media, attribution gaps, and equivalent-proof citation choices can affect these results. See run diagnostics for estimated/fallback cases. Hidden evaluation answers were not accessed. Status agreement alone is not complete plan correctness.
