# Intent and observer recovery

Authority: user's532-line pasted request (attachment7adb62a8-eee8-4b03-9d14-83c58aec05f1). Preserve Stage3/4 deterministic verdict rules.

1. Raise intent cap512; honor all supplied config including GROQ_TIMEOUT30. Expose request outcomes and IntentResolutionReason. Truncated primary batches split once on the same20B route; unresolved protocol/API failures use deterministic fallback, never semantic120B review. Only genuine lowconfidence/ruleconflict goes to review.
2. Add UTC calendar daily ledger with per-model confirmed responses/actual tokens and in-memory-only reservations. Archive legacy estimate-ledgers and migrate only provably settled actual entries. Track unknown usage separately. Local skips never count as provider calls. Keep safe model-specific rollingminute/header/concurrency controls.
3. Add native fact/source/confidence vision envelope with Pydantic validation, deterministic structured-fact adaptation, and one source-grounded20B text-only repair for malformed vision JSON. Never resend image for format repair. Structured text keeps deterministic extraction first, unstructured text routes20B; images routeQwen; PDFs textfirst. Unsupported audio must not route to vision; add Whisper transcription support if needed by input fixtures.
4. Expand per-model metrics, contextual logs and honest UNKNOWN fallback labels. Switch fitz imports to pymupdf.
5. RED/GREEN tests for daily lifecycle/rollover/migration/local skips, truncation recovery/no review, image-free repair/no fabricated facts, metrics/modalityrouting. Clean-env94-test baseline plus new cases must pass.
6. Small live cases, forced-smallcap recovery, one image+repair checks, independent review and one fixpass, full --samples and acceptance/accuracyreport. Preserve full output and prior reports; root sample predictions may update as explicitly requested.

Rulings: UTC is the explicit local quota date; confirmed token totals include truncated responses. Legacy entries with distinct settled daily/minute charges prove known usage; unchanged estimates are archived/unconfirmed, not charged as actual. Existing internal structured record fields remain available through adapters so Stage3/4 need no changes.


Execution status: steps 1–5 implemented and verified (110 tests). Step 6 includes the normal four-intent probe, real malformed-image text-only repair, real small-cap schema rejection, the complete 32-sample command and label-isolated comparison. Independent review finding fixed and reverified. Full live acceptance remains blocked by confirmed provider Qwen TPD exhaustion (Used198721/200000, Requested2498); no accuracy improvement claimed. See docs/validation/2026-10-25-observer-recovery.md. Existing full output/reports preserved.
