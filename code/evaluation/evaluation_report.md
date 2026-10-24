# Evaluation report

## Measured public sample results

Requests: 32. These are public sample measurements, not hidden 518-case accuracy.

| Metric | Result |
| --- | ---: |
| status accuracy | 87.50% |
| exact row accuracy | 12.50% |
| step precision | 92.62% |
| step recall | 71.50% |
| step f1 | 80.70% |
| field accuracy | 52.21% |
| sequence accuracy | 12.50% |

Exact step matches: 138 / 149 predicted and 193 expected.
Aligned field matches: 720 / 1379.

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
| best-evidence | 87.50% | 12.50% | 12.50% |
| incomplete | 68.75% | 12.50% | 12.50% |

The configured default remains best-evidence. This comparison does not automatically select per-case answers or change policy. Review false COMPLETE cases before applying a general conservative rule; parser/identity/policy errors must be fixed at their source.

## Failures found and improvements made

Implementation separates primary and replica scopes, checks capture and observation cutoffs, distinguishes operation claims from direct reads, uses scoped multilingual negation before deletion stems, preserves tombstone references, and applies canonical operation ordering. These mechanisms are covered by independent tests rather than hardcoded sample labels.

The implementation review found six defects, reproduced with fictional regression cases and fixed: shared-phone attribution, structured/reverse resource links, partial payloads or treatment labels accepted as compliance proof, invalid intent responses cached before validation, unread PDF pages cached as successful extraction, and retained-only/unknown-payload flows treated as prohibited copies. Integration regression checks also enforce the required archive-root report paths and prevent system names in activity prose from becoming cross-subject resource links. Provider regression checks cover exponential backoff/jitter, permanent-error handling, retry-budget ownership, and server-directed cooldowns. The suite now includes 37 tests; live-provider quality and sample-specific accuracy tuning remain deferred until API configuration.

Remaining measured failures:

| Case | Expected status | Actual status | Sequence correct | Expected/actual steps |
| --- | --- | --- | --- | --- |
| case_01 | COMPLETE | INCOMPLETE | False | 1/0 |
| case_02 | COMPLETE | INCOMPLETE | False | 1/0 |
| case_03 | COMPLETE | COMPLETE | False | 3/2 |
| case_04 | COMPLETE | INCOMPLETE | False | 2/0 |
| case_05 | INCOMPLETE | INCOMPLETE | False | 3/4 |
| case_07 | INCOMPLETE | INCOMPLETE | False | 4/3 |
| case_08 | INCOMPLETE | INCOMPLETE | False | 4/3 |
| case_09 | INCOMPLETE | INCOMPLETE | False | 5/3 |
| case_10 | INCOMPLETE | INCOMPLETE | False | 4/1 |
| case_11 | INCOMPLETE | INCOMPLETE | False | 14/12 |
| case_12 | INCOMPLETE | INCOMPLETE | False | 5/5 |
| case_15 | INCOMPLETE | COMPLETE | False | 5/2 |
| case_16 | INCOMPLETE | INCOMPLETE | False | 7/8 |
| case_17 | INCOMPLETE | INCOMPLETE | False | 5/7 |
| case_18 | INCOMPLETE | INCOMPLETE | False | 14/10 |
| case_20 | INCOMPLETE | INCOMPLETE | False | 8/4 |
| case_21 | COMPLETE | COMPLETE | False | 3/1 |
| case_22 | INCOMPLETE | INCOMPLETE | False | 8/7 |
| case_23 | INCOMPLETE | INCOMPLETE | False | 8/6 |
| case_24 | INCOMPLETE | INCOMPLETE | False | 7/7 |
| case_25 | COMPLETE | COMPLETE | False | 3/1 |
| case_26 | COMPLETE | COMPLETE | False | 6/4 |
| case_27 | COMPLETE | COMPLETE | False | 6/4 |
| case_28 | COMPLETE | COMPLETE | False | 6/4 |
| case_29 | INCOMPLETE | INCOMPLETE | False | 14/10 |
| case_30 | INCOMPLETE | INCOMPLETE | False | 14/10 |
| case_31 | COMPLETE | COMPLETE | False | 3/2 |
| case_32 | INCOMPLETE | INCOMPLETE | False | 5/4 |

No live-provider/vision quality is claimed by an offline run. API credentials, configured model IDs, unread media, attribution gaps, and equivalent-proof citation choices can affect these results. See run diagnostics for estimated/fallback cases. Hidden evaluation answers were not accessed. Status agreement alone is not complete plan correctness.

## Live API attempt after configuration

A configured Gemini run processed all 32 public samples in 42.5 seconds. Both text and vision selected `gemini-3.1-pro-preview`. All 26 actual model calls (4 intent, 22 media, including bounded retries) were rejected with HTTP 429 RESOURCE_EXHAUSTED; no model response succeeded. The provider identified free-tier request/token quotas per minute and per day. A separate minimal diagnostic request reproduced the rejection; its suggested retry delay was 46,764 seconds. That diagnostic is outside the sample pipeline usage totals.

The application completed with deterministic intent fallback and local evidence, preserved all 32 rows, and recorded 12 estimated/fallback results. Predictions are byte-identical to the prior offline baseline: status accuracy 87.50%, step F1 80.70%, field accuracy 52.21%, and exact sequence/row accuracy 12.50%. These are fallback measurements, not live Gemini quality. No accepted provider token usage was supplied; failed-call usage/cost is unknown, not measured zero.

The full 518-case live run was not launched after the quota failure was confirmed. Root output.csv and its final-full-run usage report remain from the prior verified offline run. Check the active project/model quotas in AI Studio before another live run. No credentials, model settings, billing, or prediction rules were changed.

## Live retry after model change

Text and vision both selected `gemini-3.8-flash`. The 32-sample run completed in 724.8 seconds (12.08 minutes), preserving all output rows. Actual pipeline calls: 26; accepted successful calls: 0; task breakdown: {"intent": 4, "media": 22}. Failure types: {"HTTPError": 11, "TimeoutError": 15}; HTTP status counts: {"503": 5, "429": 6}. The command exited successfully through the agreed recoverable-failure paths; that does not establish provider success.

A separate minimal generation diagnostic timed out at 30 seconds. A read-only model-metadata diagnostic returned HTTP 200 and advertised generateContent support. Metadata success confirms the model name is recognized, not that generation is available for the project. These diagnostics are separate from the 26 pipeline calls. The service-status page did not expose readable incident details, so no wider outage is asserted.

Predictions are identical to the offline baseline: True. Status accuracy 87.50%, step F1 80.70%, aligned field accuracy 52.21%, and exact sequence accuracy 12.50%. These remain fallback results, not measurements of live Gemini quality. Usage was not supplied for failed calls; their token use/cost is unknown. No full 518-case live run was launched after repeated 503 errors/timeouts. The prior offline output and full-run usage report are preserved.

## Exponential backoff implementation and live verification

Added up to four transient transport retries after the initial call, using exponential waits of 1, 2, 4, 8 seconds plus jitter, capped at 60 seconds. Only HTTP 408/429/5xx, timeout and connection failures qualify. Permanent client errors are not retried, and transport exhaustion is not multiplied by the interpretation-repair loop. Every physical attempt remains in usage accounting. Retry-After/Google RetryInfo timing is honored, including deferring further calls to the same model when the requested wait exceeds 60 seconds.

All 37 tests pass. Seven new tests verify transient recovery and exact attempt accounting, delay growth/jitter/cap, permanent errors, no nested retry multiplication, separate invalid-content repair, short server delay, and long provider cooldown. The new behavior was reproduced as failing tests before implementation.

The live smoke check selected `gemini-3.8-flash` and received HTTP 429 with an explicit 45158-second provider wait (approximately 12.5 hours). It made one physical call; no short-delay retry was sent against that server instruction. This verifies the live cooldown path; exponential short-delay recovery is verified with deterministic mocked failures, not a successful live model response.

The updated sample CLI initially encountered a checkpoint PermissionError after saving 14 cases. A compatible --samples --resume run completed all 32 cases successfully; the combined logical sample run recorded 2 physical calls, both HTTP 429, and no accepted model responses. Each process honored the indicated long cooldown for its remaining model requests. The cause of the temporary file-write failure was not established; recovery used the existing checkpoint mechanism.

All sample rows passed coverage, sorting, schema, operation/state, citation and cutoff checks. Predictions remain byte-identical to the offline baseline: 87.50% status accuracy, 80.70% step F1, 52.21% field accuracy, 12.50% exact sequence accuracy; five custom cases pass. No live model accuracy improvement is established. Failed-call token/cost usage remains unknown. The prior 518-row offline output and final-full-run usage report remain unchanged.
