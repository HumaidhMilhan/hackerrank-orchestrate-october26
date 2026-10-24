# Ghost Data Still Exists — deletion-audit CLI

A hackathon implementation of the locked four-stage pipeline: authorization and guarded identity resolution; evidence observations; deterministic state/policy analysis; deterministic decisions and canonical remediation steps. The runner adds progress, checkpoints, evaluation, usage reporting, and packaging.

## Setup

Use Python 3.10 or newer from the repository root:

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

On macOS/Linux use `.venv/bin/python` instead. Activate the environment or substitute its Python path in the commands below. PyMuPDF extracts PDFs; Groq's `groq` async SDK handles the default model routes. Google's `google-genai` SDK remains available for Gemini comparisons. CSV, SQLite, quota scheduling, CLI progress, tests, and packaging use the standard library.

## Configure Groq

Copy `.env.example` to an uncommitted `.env`, then set `GROQ_API_KEY`. Defaults:

```text
AUDIT_PROVIDER=groq
GROQ_API_KEY=your_private_key
GROQ_INTENT_MODEL=openai/gpt-oss-20b
GROQ_REVIEW_MODEL=openai/gpt-oss-120b
GROQ_EVIDENCE_MODEL=qwen/qwen3.8-27b
GROQ_INTENT_CONFIDENCE=0.85
GROQ_INTENT_BATCH_SIZE=5
GROQ_MAX_CONCURRENCY=2
GROQ_RPM=30
GROQ_TPM=8000
GROQ_RPD=1000
GROQ_TPD=200000
```

Environment variables take precedence over `.env`. Never commit the key. Without a configured key, the CLI uses the locked deterministic fallback and warns that model interpretation is unavailable. `--offline` explicitly disables network calls.

GPT OSS 20B handles intent in batches of five. Only low-confidence, missing/invalid, or rule-conflicting interpretations go to an independent GPT OSS 120B review. The review receives request text without the first model's answer. Both models must return exact case IDs, a phrase copied from the request, and finite confidence in [0,1]. Unresolved or low-confidence review results use the existing three-step fallback. Confidence is a routing heuristic, not a calibrated probability or proof of correctness.

Qwen processes screenshots, image-only PDF pages and bounded visual rechecks. SQL, JSON, logs and text PDF extraction stay deterministic. Model output remains observations; final status, policy application and remediation order remain deterministic. Changing the model does not automatically solve evidence attribution or state-reconstruction defects.

Groq's published free-plan limits for these models were checked on 25 October 2026: 30 RPM, 8000 combined TPM, 1000 RPD, 200000 TPD per model. Actual account limits can differ. See [models](https://console.groq.com/docs/models), [vision](https://console.groq.com/docs/vision), [structured outputs](https://console.groq.com/docs/structured-outputs), and [rate limits](https://console.groq.com/docs/rate-limits). Free access is quota-limited; better accuracy requires measurement.

Every physical request/retry uses a per-model async queue and provider-wide concurrency limit. Queues reserve conservative UTF-8 text/schema tokens, Qwen's documented 2048 image tokens, and the entire configured output allowance. Minute reservations remain conservative and reconcile upward to actual total usage. Successful daily reservations settle to actual total usage; failures or missing usage retain their full estimates. This can deliberately underuse the available quota. Oversized jobs fall back without dispatch. Set `GROQ_{INTENT,REVIEW,EVIDENCE}_{RPM,TPM,RPD,TPD}` to override a role's limits; roles using the same model share the tightest bucket. `GROQ_{INTENT,REVIEW,EVIDENCE}_MAX_OUTPUT_TOKENS` controls output budgets (1024/1024/2048 by default). Larger budgets must fit the model's local TPM allowance.

Rolling 24-hour request/token reservations persist under ignored `.runtime/model_cache/groq_quotas/`, including recent minute reservations. Daily exhaustion does not make the CLI wait a day: affected calls fall back. An unreadable ledger also refuses untracked dispatch and warns. Use one CLI process per checkout; the ledger is not a cross-process or cross-machine lock. Other applications in the same organization can still consume quota. Provider 429/reset headers remain authoritative.

GPT OSS uses strict JSON Schema. Qwen uses JSON-object mode with recursive local validation. Both also pass stage-specific grounding checks. Truncated/refused/invalid responses are never cached. Automatic SDK/HTTP retries are disabled; bounded application retries reacquire quota. Shutdown cancels queued calls and backoff waits. Accepted response caches are provider/model/prompt/schema/config isolated and consume no API quota.

Cost rates are optional and never guessed. For each role, configure `GROQ_<ROLE>_INPUT_USD_PER_MILLION`, `GROQ_<ROLE>_OUTPUT_USD_PER_MILLION`, and optionally `GROQ_<ROLE>_CACHED_USD_PER_MILLION`. Reports preserve separate model totals. Groq reasoning is already included in completion tokens and is not counted twice. Missing or conflicting prices are reported as unavailable, not zero.

## Optional Gemini comparison

Set `AUDIT_PROVIDER=gemini` and configure `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_RPM`, `GEMINI_TPM` and `GEMINI_MAX_CONCURRENCY`. Defaults remain gemini-3.6-flash, 5 RPM, 250000 input TPM and concurrency 2. Optional `GEMINI_TEXT_MODEL`/`GEMINI_VISION_MODEL` override model routing. With no `AUDIT_PROVIDER`, existing installations retain Gemini for compatibility; `.env.example` explicitly selects Groq. There is no silent provider fallback.

Every Gemini operation, including token counting, uses its shared async quota queue. Count calls consume local RPM/concurrency; generation reserves input TPM. Explicit httpx transport and disabled SDK retries prevent hidden calls. `AUDIT_INPUT_USD_PER_MILLION`, `AUDIT_OUTPUT_USD_PER_MILLION` and `AUDIT_CACHED_USD_PER_MILLION` apply only to Gemini and assume a common verified price; use the same model or leave rates unset when comparing different Gemini prices.

Both providers expose the same `request_json` / `request_json_async` and `close` / `aclose` interfaces. The audit stages never call an SDK directly.

## Run

```text
python code/main.py --samples
python code/evaluation/main.py
python code/main.py
```

The sample run writes `sample_predictions.csv`; the full run writes root `output.csv` with exactly 518 sorted evaluation cases. The evaluator alone reads public sample labels. Prediction code never reads `sample_output.csv`, organizer files, hidden answers, or generator internals.

Useful options:

```text
python code/main.py --samples --offline
python code/main.py --resume
python code/main.py --quiet
python code/main.py --verbose
python code/main.py --uncertainty incomplete
python code/main.py --env-file path/to/private.env
python code/main.py --help
```

Progress, current phase/case, running status counts, retries/rechecks, warnings, and errors go to stderr. CSV is written to a file. `--quiet` retains warnings and the final summary; `--verbose` adds sanitized detail. Final output includes elapsed time, case/status counts, estimates, warning/error counts, model calls/tokens, and artifact locations.

The source resolves its normal dataset and output paths relative to the repository, so it can be launched from another working directory. `--dataset` and `--output` support independent fictional datasets/testing. Do not point `--output` at participant input files.

## Behavior and limitations

- Groq intent uses configurable batches of five and independent secondary review for flagged cases; Gemini retains batches of 20. Each model has at most one interpretation repair for invalid/missing results. The final fallback checks explicit non-deletion/negation first, multilingual deletion stems second, and defaults to NON_DELETION with warning.
- SDK transport failures use up to four retries after the initial request: exponential delays of 1, 2, 4, and 8 seconds plus up to 25% jitter, capped at 60 seconds. Each attempt must reacquire shared quota. Retry only HTTP 408/429/5xx (also Groq 409), timeouts, and connection/network failures. Permanent HTTP client errors are not retried. Exhausting transport retries does not trigger another interpretation retry.
- Respect `Retry-After`, Groq reset headers and Google's `RetryInfo` delay. A provider-requested wait longer than 60 seconds defers further calls to that model for the indicated window while cases continue through fallbacks. Every physical attempt is counted separately; failures with missing token usage remain unknown.
- Identity links follow explicit stable user ownership and eligible history, never names/phone coincidences or numeric suffixes.
- Evidence is parsed once, with primary/replica scopes and capture/observation times. Resource retrieval has at most two link-expansion passes.
- Stage 3 allows one targeted recheck. Operation reports do not prove resulting state. Retention, anonymization, redaction, tombstones, active flows, and restore access are evaluated from supplied rules.
- Stage 4 has no model calls and follows the mandated phase/operation/system/resource order. Findings and COMPLETE checks cite eligible evidence; future INCOMPLETE actions/checks have empty evidence IDs.
- Recoverable failures do not drop cases. The selected best-evidence fallback may estimate COMPLETE when known observations are compliant but coverage is uncertain. With no usable state evidence, the last resort is INCOMPLETE with available steps, possibly an empty array. These guarantee row coverage, not semantic correctness; diagnostics disclose the estimates. `--uncertainty incomplete` uses the conservative comparison policy.

Accepted extraction and compatible case checkpoints live under ignored `.runtime/`. `--resume` reuses only a compatible input/source/configuration signature. This directory also contains assessments, diagnostics, and per-run usage. Do not package it or share credential-bearing provider files.

## Tests and evaluation

```text
python -m unittest discover -s code/tests -v
python code/evaluation/main.py
```

The evaluator reports status accuracy, exact row accuracy, step precision/recall/F1, aligned field accuracy, and sequence accuracy on the 32 public samples. It also runs independent fictional cases for multilingual negation, replica drift, tombstones, audit cutoffs, and recreation risk. The same saved assessments compare the two uncertainty policies without additional model calls. Sample agreement does not establish hidden 518-case accuracy.

Required human-readable reports are generated at:

- `code/evaluation/evaluation_report.md`: measured sample metrics, custom cases, remaining failures, and implementation improvements.
- `code/evaluation/usage_report.md`: actual final full-run provider/model/call/token totals, averages, cost estimates, cache reuse, and limitations.

Model interpretation/extraction prompts are in Python source, so they remain visible to the code judge. The raw runtime cache is not part of the submitted solution.

## Package

After sample evaluation and a full run:

```text
python code/evaluation/main.py --package
```

Alternatively append `--package` to the full audit command once both reports exist. The inspected `code.zip` includes README, requirements, the safe environment example, Python source/prompts, tests, and Markdown reports. It excludes the dataset, caches, environments, credentials, and nested archives. Upload root `output.csv` separately and root `log.txt` as the development transcript. The application does not submit or publish anything automatically.

The archive also includes the required `evaluation/evaluation_report.md` and `evaluation/usage_report.md` paths at its root, copied from the generated reports under `code/evaluation/`.

Challenge: https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists
