# Public-sample policy calibration — 25 October 2026

Acceptance gate requested by the user: **deletion-status accuracy greater than 90%**. Final result: **29/32 =90.625%**, in both live routing and deterministic hosted-API-offline fallback. This is calibration on the32 public examples, not an independent held-out estimate or a claim about hidden518-case accuracy.

## Measured comparison

| Metric | Saved baseline | Final live | Final local fallback |
| --- | ---: | ---: | ---: |
| Deletion-status accuracy | 68.750% | 90.625% | 90.625% |
| Exact full row | 12.500% | 28.125% | 28.125% |
| Exact step sequence | 12.500% | 28.125% | 28.125% |
| Step precision | 82.000% | 94.872% | 94.872% |
| Step recall | 63.731% | 76.684% | 76.684% |
| Step F1 | 71.720% | 84.814% | 84.814% |
| Aligned field accuracy | 51.124% | 60.334% | 60.334% |

Final live run: **67.2 seconds**,32 rows,7 COMPLETE /25 INCOMPLETE,17 case warnings (baseline363),3 estimated cases,0 processing errors. Final local fallback replay: **0.8 seconds with warm OCR cache**, identical prediction rows and zero hosted calls. A prior uncached local-OCR sample pass took36.9 seconds; the0.8-second replay must not be represented as cold-start runtime.

## General corrections

- Normalize replica/cluster infrastructure names to their owning business service while preserving replica scope. This removes phantom extra resources without hiding a replica that still contains data.
- Infer marketing purpose from explicit contact opt-in lookup fields instead of assuming an analytics-looking resource ID always means an analytics profile.
- Retain the latest conclusive record read when a later marker/metadata check supplies no state. A later idempotent deletion claim does not undo an observed absence; a recreation claim can still introduce uncertainty.
- Recognize an active subject-selected connector as a recreation risk. Explicit retained-only scope stays permitted; a bare enabled flag with no subject/payload scope stays unknown.
- Treat visible redaction placeholders as removed values and preserve required tombstone references.
- Route readable screens through local OCR and bounded20B text observation. Grounding failures stay UNKNOWN for relevant subjects; reliable unrelated scope does not blanket-block every request.
- Keep unsupported subject-linked screens unresolved even when they contain no recognizable resource ID. Low-confidence/malformed neighboring identities prevent confident scope exclusion.
- Read ordinary object-storage tables deterministically, retaining every visible filename. Do not assume ownership from filename repetition. Exact eligible catalog links can bind observed objects to stable IDs; conflicting owner/system bindings never establish a deletable attachment. Visible owners that cannot be safely attached per row retain scoped uncertainty.
- Any known material resource with UNKNOWN state, or a relevant failed observer, prevents COMPLETE. Required phase/operation/system/resource ordering is preserved.

Public sample answers are read only by the evaluator. Prediction stages do not load them, map case numbers to resources, or use organizer/generator files. No participant dataset was edited.

## Routing and model usage

| Work | Route |
| --- | --- |
| SQL / JSON / logs / structured text | Local deterministic parsers |
| Readable screenshots | Local RapidOCR -> bounded20B text observer |
| Readable object-storage listing | Local filename observations + exact eligible catalog binding |
| Unsupported/unreadable OCR / image-only PDF | Configured Qwen observer |
| Intent |20B,120B only for semantic review; deterministic multilingual fallback |
| Final state and remediation | Deterministic policies |

Final live hosted usage:12 GPT-OSS20B physical calls,8397 input tokens and2366 output tokens (10763 total,768 cached input).2 replies accepted;10 rejected by literal grounding validation. There were0 truncations,0 HTTP failures,0 local quota skips and0 transport retries. Other accepted work came from11 response-cache hits. No120B or Qwen calls were required in this measured run. Rejected observations did not become positive facts; the local fallback produced identical public-sample predictions. Monetary cost is unavailable because verified price rates were not configured.

Local OCR accounting is separate:11 cached screen reads,0 new OCR inference calls in the final warm run. The pinned local model is rapidocr-onnxruntime/1.2.3. Local hardware cost is not estimated. Cache construction and earlier calibration runs are excluded from these final-run usage figures.

## Verification

-133 tests pass in both the working environment and a fresh Python3.13 environment installed solely from requirements.lock. Fresh-environment pip check and real OCR smoke test also pass.
-23 new fictional calibration regressions cover policy purpose, replica naming, partial reads, connector scope, malformed OCR neighbors, exact filename matching, preserving all visible rows, conflicting owner links, capture cutoffs, visible ownership, material UNKNOWN and order invariance.
- The evaluator passes5/5 additional fictional cases and reports all required status/step/field/sequence metrics.
- Independent review reproduced unsafe OCR exclusions, missing no-ID artifact uncertainty, missing lock dependencies and catalog binding ambiguity. Each confirmed finding was fixed with regression coverage and rechecked. No Important/Critical findings remain in the reviewed scope.
- A separate final-code full-dataset offline contract run produced518 unique sorted valid rows in6.9 seconds with no processing errors and no hosted calls. It wrote under ignored .runtime/full-calibration-validation/. Its hidden accuracy is unknown; it is not the canonical submitted output.
- Root output.csv and its existing full-run usage report were preserved byte-for-byte. Sample predictions and the sample evaluation report were refreshed.

## Remaining differences and limits

Status misses: case_01, case_02 and case_04. The public baseline expects COMPLETE and account absence checks, but the supplied cutoff-eligible snapshot has no grounded subject-to-account-ID bridge for these missing rows. Bare activity IDs do not identify the subject. The agent retains INCOMPLETE instead of deriving resource IDs from user/case numbering.

Other exact-row mismatches include anonymous records with erased ownership links, policy-supported historical findings omitted by the baseline, and missing ownership metadata that appears only in later captures. Later files are not used to retroactively change an audit. Consequently status agreement exceeds90%, while exact-row agreement is28.125%; these metrics must not be conflated.

OCR confidence is a coverage heuristic, not a proof that no text was missed. Required matching/unscoped failures remain conservative. Successfully read but unattributed global records are treated as unassigned global data, consistent with the dataset decoy model, not as proof of absence. Unsupported audio still requires a separate transcription extension.
