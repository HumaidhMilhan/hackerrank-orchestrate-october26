# Groq routing implementation plan

Spec: [Groq routing](../specs/2026-10-25-groq-routing-design.md).

## Global constraints

- Preserve deterministic policy decisions, cutoff enforcement, row coverage and canonical ordering.
- No organizer-only inputs, credentials in logs/archives, or golden-label prediction shortcuts.
- Preserve the user's output.csv and full-run usage report; changes run on the existing implementation branch.
- Existing Gemini compatibility and its 50 tests must keep passing.

## Review focus

- A primary classifier can report high confidence while contradicting explicit negation: escalate disagreements.
- A secondary provider failure must not promote an uncertain primary interpretation: use the locked fallback.
- Shared model IDs and application restarts must not bypass quota: shared buckets and persistent reservations.
- Malformed/truncated/refused replies and display labels must not become authoritative facts: validate before cache/admission.
- Multiple models have different prices and usage semantics: per-model attribution without double-counted reasoning.

## Task 1: Scheduled Groq provider

Files: create `code/groq_client.py`, `code/tests/test_groq_provider.py`; modify `code/llm.py`, `code/quota.py`, requirements and env example.

Interface: `ModelClient(cache_dir, offline=False)` selects the configured backend. Groq implements the existing sync/async request_json facade plus configuration, calls/cache_hits and close/aclose. New `DailyQuotaError`; scheduler accepts optional daily limits/ledger; Gemini defaults are unaffected.

- [x] Write failing tests for provider selection, schema/image payloads, cache isolation, bounded retries, daily persistence, shared buckets and shutdown.
- [x] Run focused tests; confirm missing behavior failures.
- [x] Implement AsyncGroq routing, quota/usage accounting and local validation.
- [x] Run provider and existing tests; fix regressions.

## Task 2: Confidence-based intent review

Files: modify `code/stage1.py`; create `code/tests/test_intent_routing.py`.

Interface: `interpret_requests` retains existing result structure and adds confidence/review metadata for Groq. Client exposes intent_review_model, intent_confidence_threshold and intent_batch_size. The task `intent_review` routes to 120B. Secondary inputs contain request text only.

- [x] Write failing tests for high-confidence fast path, low/missing/invalid confidence, primary-rule conflict, independent review, partial results and secondary failure.
- [x] Verify RED, implement bounded review/fallback, verify GREEN.

## Task 3: CLI/docs/integration

Files: README, locked design addendum, runner usage accounting and tests.

- [x] Add tests for per-role rates and no reasoning double-counting; verify RED then implement.
- [x] Update env defaults/routes/quota documentation and program progress.
- [x] Run the full test suite and separate offline sample integration; preserve full-run artifacts.
- [x] If credentials exist, bounded live verification; otherwise document the missing live test.
- [x] One fresh-context whole-change review, one fix pass for important findings, final tests, package inspection and commit.

Verification completed: 76 tests pass; separate offline sample and extracted 25-file archive each produced32 rows. No Groq key was configured, so the conditional live check was documented as unavailable. User full-run output/usage remain unchanged. Independent review findings were fixed with failing-then-passing regression tests.
