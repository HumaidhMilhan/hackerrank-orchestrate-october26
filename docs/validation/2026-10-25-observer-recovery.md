# Observer recovery validation — 25 October 2026

The Stage 1/2 changes are implemented; the requested full live acceptance gate has **not passed**. Stage 3/4 remain unchanged. This report is separate from the existing competition evaluation and full-run usage reports, which were preserved byte-for-byte. Root `output.csv` was also preserved. Public sample predictions were regenerated as requested.

## Verification

- 110 automated tests pass in the clean Python 3.13 environment; `pip check` reports no dependency conflicts.
- New regressions cover temporary 5000-token reservation / 1300 actual settlement, separate model ledgers, UTC date rollover, local skips, unknown returned usage, legacy estimate migration, corrupt state, native observation adaptation, literal source-preserving repair, missing visual category normalization and actual/truncated call metrics.
- SDK transport fixtures cover image-free repair, one image dispatch, per-model actual usage, local daily skips without API attempts, and HTTP retry allowlisting. A fabricated observation introduced during repair is rejected.
- A forced mocked `finish_reason=length` batch splits on 20B without 120B escalation. A real forced cap of 64 (and 256) instead made Groq return HTTP400 `json_validate_failed`; it received no transport retry or semantic escalation and is labeled `primary_schema_failure`. The normal 512 cap remains unchanged.
- A real four-case normal intent probe returned four accepted interpretations, `finish=stop`, no review.
- A real image request reached Qwen and returned HTTP400 `json_validate_failed` with usable `failed_generation`. One text-only 20B repair returned four grounded rows. The image was not resent. A shorter key/value fact prompt was subsequently added and covered by unit tests; successful live validation of that revised prompt remains pending available Qwen quota.
- Independent review found missing policy categories when a screenshot did not print a canonical record type. Reusing the existing Stage 2 resource mapping fixed it; the reviewer verified the original reproduction now generates finding/remediation/verification. No outstanding Important/Critical review findings.

## Full public sample run

The standard `python code/main.py --samples` command produced all 32 rows with no processing errors. It used one response cache hit from the live probe, seven new 20B calls and one attempted Qwen call. It did not use 120B.

| Acceptance criterion | Observed |
| --- | --- |
| Normal intent truncations | 0 |
| Normal intent schema failures | 0 |
| Semantic review rate | 0/32 |
| Qwen API attempts | 1 |
| Qwen provider failure | 429, actual daily limit |
| Qwen local deferrals | 10, following the provider cooldown |
| Transport retries | 0 |
| Estimated cases | 12, previously 7 |
| Case warnings | 363, previously 281 |
| Runtime | 7.4 seconds; **not a successful vision performance result** |

Groq explicitly reported **tokens per day: Limit 200000, Used 198721, Requested 2498**, with Retry-After 527 seconds. This differs from the earlier stale local estimate block: this request left the process and Groq rejected it. The remaining images were deferred under that provider cooldown. Historical daily migration reconstructed only provable actual usage; it cannot reconstruct all usage from other clients or ambiguous old estimates. Provider quota diagnostics disclose the authoritative external bound.

## Sample agreement

The label-isolated evaluator was run after prediction, without feeding sample answers into prompts or prediction stages.

| Metric | Previous saved predictions | Current quota-blocked run |
| --- | ---: | ---: |
| Status accuracy | 68.75% | 68.75% |
| Exact rows / exact sequence | 12.50% | 12.50% |
| Step precision | 90.44% | 82.00% |
| Step recall | 63.73% | 63.73% |
| Step F1 | 74.77% | 71.72% |
| Aligned field accuracy | 49.09% | 51.12% |

These outcomes do not show an accuracy improvement. Missing visual observations still make the verdicts incomplete; deterministic policies were not weakened to hide that failure.

## Remaining live acceptance work

Rerun `python code/main.py --samples` once sufficient Qwen daily capacity is available. One image fitting after a short cooldown does not establish enough capacity for all eleven visual jobs. Confirm the revised Qwen JSON envelope succeeds, warnings/estimated cases decrease, all required observations are covered, and runtime stays below the preferred 300 seconds. Then evaluate the regenerated samples. If the provider continues rejecting valid JSON Object vision requests, this remains a provider/prompt reliability issue requiring another measured iteration, not an accuracy tuning justification.

Audio is not present in the participant dataset. Its recommended Whisper-to-text route is documented as a future extension; unsupported audio never goes to Qwen vision.


Final follow-up probe after the first cooldown still received provider429: Used197462/200000 and Requested2733. It performed exactly one transport retry, then honored the new 85-second provider cooldown. No image success or full-suite acceptance is claimed from that probe. The prior real text-only repair and mocked native-envelope tests remain the available positive checks.
