# Root cause: the three unresolved public-sample cases

The errors are **case_01, case_02 and case_04**. All three authorize deletion. Both the saved live model result and the deterministic multilingual fallback say DELETION; this is not an intent-classification failure. Identity resolution finds the correct stable subject without ambiguity.

## Actual stage-by-stage trace

| Stage | case_01 | case_02 | case_04 |
| --- | --- | --- | --- |
| Request meaning | Close account and remove personal details | Spanish request to check a failed deletion and finish it | Delete account; anonymous statistics may remain |
| Stage 1: saved model intent | DELETION, accepted | DELETION, accepted | DELETION, accepted |
| Stage 1: fallback intent | DELETION | DELETION | DELETION |
| Resolved subject | user_01 | user_02 | user_04 |
| Identity warnings | None | None | None |
| Cutoff-eligible evidence files | 69 | 69 | 74 |
| Eligible files containing a bounded identifier or full-name match | 0 | 0 | 0 |
| Stage 2: retrieved observations | 0 | 0 | 0 |
| Relevant observer failures | 0 | 0 | 0 |
| SQL primary / replica matching rows | 0 / 0 | 0 / 0 | 0 / 0 |
| Stage 3: addressable resources to evaluate | 0 | 0 | 0 |
| Stage 4 result | INCOMPLETE, estimated, empty steps | INCOMPLETE, estimated, empty steps | INCOMPLETE, estimated, empty steps |
| Public reference | COMPLETE, account_001 absent | COMPLETE, account_002 absent | COMPLETE, account_004 absent and analytics_901 anonymized |

All evidence types were considered under each audit cutoff. The source scan used current/historical resolved identifiers and full names; images used locally cached OCR and PDFs used extracted text. No hosted API calls were needed. The report does not infer that every conceivable fuzzy match was exhausted; it confirms there is no supported identifier/ownership path in the current parser and no raw bounded identifier/full-name match in the eligible files.

## case_01

Request: “Hi, I haven’t used this account in years and would like it closed. Please remove the profile and the personal details attached to it.”

Audit cutoff:2026-09-03T11:30:00Z. Stable subject:user_01. The reference expects an absence check for account_001 citing evidence_54.

[evidence_54](../../dataset/evidence/databases/customer_accounts_failover_replica_20260902.sql) is a SQLite snapshot captured2026-09-02T23:00:00Z. It contains three primary rows and four replica rows. Neither table contains user_01 or this subject’s email. SQL contains neither account_001 nor a catalog mapping user_01 to account_001.

The relevant activity_3342 names account_001 and claims DELETE_RECORD SUCCESS. It supplies no subject identifier. The activity can identify an operation target, but it does not establish that this target belongs to this request, and its result does not prove deletion.

The current retrieval index is seeded by subject identifiers. No positive row or ownership link starts the resource-history traversal. Therefore no SQL-derived negative record observation enters Stage3. Stage4 has no evidence-backed verification step it can serialize for the canonical account ID.

## case_02

Request: “Intenté eliminar mi cuenta ayer, pero la página terminó mostrando un error. ¿Pueden comprobar si todavía queda algún dato y completar la eliminación si hace falta?”

Audit cutoff:2026-09-04T15:00:00Z. Stable subject:user_02. The request explicitly asks to complete deletion if needed. Its reported PARTIALLY_COMPLETE workflow status is correctly not used as the verdict.

The same evidence_54 snapshot contains no matching user_02/email row in either primary or replica. The reference expects account_002, but the snapshot has no subject-to-account_002 bridge. activity_3376 names account_002 and reports PARTIAL without naming the subject. This is the same broken traversal start as case_01, not a Spanish-language edge case.

## case_04

Request: “I’m deleting my account. You can keep anonymous statistics, but nothing in analytics should still point back to me.”

Audit cutoff:2026-09-07T10:20:00Z. Stable subject:user_04. The account absence check has the same missing mapping problem, now for account_004. No participant evidence or activity row names account_004 with this subject.

[evidence_56](../../dataset/evidence/records/customer_analytics_report_20260907.json), captured2026-09-07T09:45:00Z, additionally contains analytics_901. Its user_id, email, phone and email_hash are all null. The payload is readable, fully parsed and classified ANONYMIZED. However, its identifying edge has been erased. There is no earlier eligible owner binding linking user_04 to analytics_901. activity_3463 claims an anonymization of analytics_901, again without a subject identifier. A separate identifiable analytics_824 belongs to another subject and is correctly excluded.

The algorithm can evaluate analytics_901 as anonymous in isolation. It cannot assign that anonymous row to case_04 without a grounded historical resource link. A new fictional regression confirms the existing traversal succeeds when such an earlier binding actually exists and does not invent an assignment when it is removed.

## Shared pattern and defects found

1. **Negative-evidence discovery gap.** A complete SQL snapshot can return zero rows when queried by the known subject. The row-oriented parser emits observations for existing rows; it cannot seed a resource graph from an absent row. The canonical account record IDs are also not recoverable from the supplied eligible identity links. Negative query coverage and an addressable canonical record ID are separate needs.
2. **Erased ownership edge.** Proper anonymization removes the identifiers used to retrieve the record. Historical resource ownership must establish that link before treatment, or an independent eligible catalog must preserve it. Requiring the anonymized payload to keep personal identifiers would defeat the policy.
3. **Misleading uncertainty flag, fixed.** An empty resource list previously produced Stage3 uncertain=false even though coverage was unresolved. Authorized requests with no subject-linked resources now produce uncertain=true and an explicit coverage warning.
4. **Skipped bounded investigation, fixed.** The runner previously rechecked only lists containing an UNCERTAIN resource. An empty list never satisfied that condition. Empty authorized retrieval now receives one bounded recheck. Actual replay confirms all three use it and still yield zero linked resources.
5. **Opaque terminal fallback, fixed.** The diagnostic now includes NO_SUBJECT_LINKED_STATE_EVIDENCE. INCOMPLETE here means verification could not be established; no remaining-data finding was emitted.

## Why the three labels are not forcibly changed

Marking empty retrieval COMPLETE would equate “did not connect evidence” with “proved no relevant data exists.” That can hide retrieval/parser failures. Deriving account_001/account_002/account_004 from user/case numbering would be a forbidden shortcut. Assigning the first anonymous analytics row to case_04 would also be ungrounded.

A safe complete implementation can add parameterized negative lookups over explicitly complete, eligible snapshots **once the output resource locator is grounded**. These cases additionally need an eligible subject-to-account-ID mapping, and case_04 needs the pre-anonymization analytics resource link. This audit does not fabricate those inputs or alter participant data.

## Verification and artifacts

-137 tests pass, including four new fictional missing-evidence/history tests and the expanded runner regression.
- The32-case local fallback replay is unchanged:29/32 status accuracy,90.625%. The three remain unresolved; no accuracy improvement is claimed from diagnostic changes.
- Root output.csv, sample_predictions.csv and the existing full-run usage report remain unchanged.
- Extracted requests:.runtime/three-case-rootcause/requests.csv.
- Complete per-case identity, eligible-file scan, SQL query counts, activity claims, anonymous-row state, stage outputs and recheck results:.runtime/three-case-rootcause/stage-traces.json.
