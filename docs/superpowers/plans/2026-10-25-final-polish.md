# Final polish and verification

Follow the user attachment f9552bf7-dd54-4059-a715-d1a42e142638 in six ordered steps.
1. Polish shared intent instructions and negation-first fallback; verify all requested IDs once, six languages, cutoff identity guards, and batches of 20.
2. Audit media, SQL, JSON, trace retrieval and dual cutoff; fix only grounded extraction defects.
3. Verify temporal scopes, supplied policies and one bounded recheck.
4. Verify deterministic status, citations, templates and canonical sorting.
5. Run live samples, evaluator, independent tests and inspect every mismatch.
6. Run all 518 with the configured provider, validate output, regenerate reports and inspect archive.

Constraints: preserve architecture, file layout, provider routing, async queues, CLI flags and checkpoint/cache structure. No label-derived predictions or unsupported ownership/absence.

Ruling: batch 20 is a supported validation scenario; retain environment-configured live batch size (currently 4) and the existing split-on-truncation behavior, per the locked Groq routing design. This avoids overriding the user quota configuration; larger batches remain configurable.
Ruling: SQL absence requires an explicit exhaustive population/table contract plus an independently grounded resource identity. snapshot_scope supplies only system/timestamp, not population completeness. Do not turn every omitted row into ABSENT.

## Subsequent user steering: isolated workflow linkage

Inspect evidence_54 and evidence_56 in full. Both read; SQL has primary/failover tables (three/four rows), no account_001/002/004 row or numerical population declaration. JSON has anonymous analytics_901 and unrelated analytics_824.
Add a general Stage 2 association under the user-supplied convention: isolated report within fifteen minutes across the union of request files, one eligible deletion_worker target operation in that window, requested_at <= event <= audit_at, literal Target resource match, no conflicting explicit ownership. Keep the event a claim and its provenance; never accept its result as state proof.
For an independently linked DELETE target, query each matching table in eligible SQL artifacts explicitly declared point-in-time database snapshots, captured after the linked operation. Zero matching rows is an absence observation scoped to that exported table. Do not derive unknown resources or numeric populations, do not use filtered/partial snapshots, and do not let primary absence cancel replica presence. Document the closed exported-table scope; account_004 has no supplied ownership edge and must not be invented.
Run regression tests, isolated sample replay, standard live samples and evaluator; report actual status and full-array metrics separately. Restart final full run only after logic is settled.
