# Groq model routing

User-requested extension of [the locked pipeline](2026-10-24-deletion-audit-system-design.md). The four audit stages, evidence cutoffs, deterministic verdicts, remediation ordering, mandatory row coverage and three-part intent fallback remain in force.

## Approach

Use Groq's async SDK with the existing scheduler rather than replacing the audit pipeline or introducing an agent framework. Retain Gemini as an explicitly selectable backend for comparison; never silently mix providers or reuse another provider's response cache. Work on the existing implementation branch and preserve the user's latest output and usage report.

Route initial intent interpretation to `openai/gpt-oss-20b`, independent review to `openai/gpt-oss-120b`, and existing multimodal evidence extraction/rechecks to `qwen/qwen3.8-27b`. Structured logs, JSON, SQL and text PDFs retain deterministic extraction. These choices implement the user's selected architecture, not a claim that the models are more accurate.

## Intent routing

Groq classifications add a finite numeric confidence in [0,1] to the existing grounded phrase and exact case ID. Default escalation threshold: 0.80, configurable. Review only cases with missing/invalid primary results, low confidence, or disagreement with the deterministic intent check. Secondary review is independent: it receives request text, not the primary verdict. It has the same grounding and confidence validation. Groq local ValueError/JSON/schema/grounding failures stop the current request without another stage or transport attempt. A valid partial intent result may request missing cases once; secondary review remains a distinct route. Unresolved/low-confidence secondary output uses the locked fallback and a warning. Self-reported confidence is an escalation heuristic, not calibrated probability. Gemini keeps its existing behavior.

## Quotas, responses and resilience

All physical Groq attempts pass through a per-model rolling scheduler and one provider concurrency semaphore. Initial defaults per model are 30 RPM, 8000 combined TPM, 1000 RPD and 200000 TPD, plus provider concurrency 2; all are env configurable. Published limits are organization-wide; other applications may consume them. Reserve conservative UTF-8 text/schema overhead, Qwen's documented 2048 image tokens, and maximum output tokens. Refuse oversized requests locally, preserve bounded fallback, retain failed reservations, and reconcile minute reservations upward using returned total usage. Successful daily reservations settle to actual total tokens; missing usage retains the estimate so the 518-case run does not prematurely exhaust a daily budget using successful overestimates. Daily guards use rolling 24-hour reservations without waiting a day. Token/request reservations persist in an ignored local quota ledger across restarts; account activity outside this checkout is handled by provider errors/cooldowns. Shared-model overrides share one quota bucket using the tightest configured role limit.

Use `AsyncGroq(max_retries=0)` and an explicit httpx transport with retries disabled. Retry only 408/409/429/5xx and transient network errors, at most four times with exponential jitter; honor Retry-After and reset timing, model-scoped cooldowns, and cancellation. Invalid/truncated/refused JSON is not cached. GPT OSS uses strict JSON Schema; Qwen also uses strict JSON Schema plus local semantic validation, reasoning_effort none and a hard512-token output cap. GPT OSS uses low reasoning, omits reasoning text and retains1024-token outputs. The media schema excludes empty/malformed resource IDs to prevent UI headings being returned as records. Wrap array responses as `{"items": [...]}` on the wire. Do not record raw prompts, images, API keys, provider error bodies or credential-bearing URLs in usage/logs.

## Configuration and reporting

`AUDIT_PROVIDER=groq`, `GROQ_API_KEY`, role-specific model/quota/output-token variables, confidence threshold, batch size (default 8), timeout and verified role-specific cost rates live in env configuration. Secrets remain uncommitted. CLI reports selected routes and quota waits. Usage keeps per-model calls/tokens and escalation calls; unknown token usage remains unknown. Output/usage from a previous full run must not be presented as a Groq run. No performance superiority or free-tier entitlement is claimed without measurement.

## Verification

Tests must exercise routing, grounded confidence escalation, malformed and partial batches, unavailable secondary service, strict/object JSON conversion, image request encoding, quota sharing/daily persistence, SDK retry ownership, 429 cooldowns, cancellation, per-model usage and provider-isolated caches. Preserve the current 518-case output and report; run tests and offline sample integration without spending quota. If a Groq credential is already configured, run a bounded live sample separately and report measured accuracy; otherwise state that live quality remains unverified.

Sources checked 2026-10-25: [models](https://console.groq.com/docs/models), [vision](https://console.groq.com/docs/vision), [structured outputs](https://console.groq.com/docs/structured-outputs), [rate limits](https://console.groq.com/docs/rate-limits), [SDK](https://github.com/groq/groq-python).

## API diagnosis and user-directed refinement

Controlled calls reproduced HTTP400 json_validate_failed for insufficient intent output, a Qwen HTTP200 length finish, and rejected empty-ID UI rows. The eight requested refinements set Qwen512/none/strict, intent batch8, threshold0.80, prohibit validation replay, retain deterministic non-image parsing and separate per-model budgets. The active intent output cap was256 and was restored to1024 so eight structured classifications fit. Live eight-case requests now pass both GPT OSS models. Qwen strict512/none subsequently returned HTTP200stop with four locally validated rows and463 output tokens, after one503overcapacity. Server capacity failures must not be mislabeled as token quota exhaustion. These changes repair API transport/format handling, not the audit policies or accuracy logic.
