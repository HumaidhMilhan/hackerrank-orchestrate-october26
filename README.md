# Ghost Data Still Exists — deletion-audit CLI

A hackathon implementation of the locked four-stage pipeline: authorization and guarded identity resolution; evidence observations; deterministic state/policy analysis; deterministic decisions and canonical remediation steps. The runner adds progress, checkpoints, evaluation, usage reporting, and packaging.

## Setup

Use Python 3.13 (the verified runtime) from the repository root:

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
.venv\Scripts\Activate.ps1
```

On macOS/Linux use `.venv/bin/python` and `source .venv/bin/activate` instead. Activate the environment or substitute its Python path in the commands below. PyMuPDF extracts PDFs; Groq's `groq` async SDK handles the default model routes. Google's `google-genai` SDK remains available for Gemini comparisons. CSV, SQLite, quota scheduling, CLI progress, tests, and packaging use the standard library.

## Configure Groq

Copy `.env.example` to an uncommitted `.env`, then set `GROQ_API_KEY`. Defaults:

```text
AUDIT_PROVIDER=groq
GROQ_API_KEY=your_private_key
GROQ_INTENT_MODEL=openai/gpt-oss-20b
GROQ_REVIEW_MODEL=openai/gpt-oss-120b
GROQ_EVIDENCE_MODEL=qwen/qwen3.8-27b
GROQ_INTENT_CONFIDENCE=0.80
GROQ_INTENT_BATCH_SIZE=4
GROQ_INTENT_MAX_OUTPUT_TOKENS=512
GROQ_REVIEW_MAX_OUTPUT_TOKENS=512
GROQ_EVIDENCE_MAX_OUTPUT_TOKENS=512
GROQ_EVIDENCE_FORMAT=json
GROQ_EVIDENCE_REASONING_EFFORT=none
GROQ_MAX_RETRIES=1
GROQ_TIMEOUT=30
GROQ_MAX_CONCURRENCY=2
GROQ_RPM=30
GROQ_TPM=8000
GROQ_RPD=1000
GROQ_TPD=200000
```

External environment variables take precedence over `.env`; the last definition of a repeated name inside the file wins. Startup logs show each effective role cap, format, effort and retry budget. Never commit the key. Without a configured key, the CLI uses the locked deterministic fallback and warns that model interpretation is unavailable. `--offline` explicitly disables network calls.

GPT OSS 20B handles intent in batches of four. Only genuinely low-confidence or rule-conflicting interpretations go to an independent GPT OSS 120B review. Missing results, API failures and schema failures use the deterministic fallback with an explicit resolution reason. Truncated primary batches split on the same 20B model; a truncated singleton gets one shorter retry at the configured cap. Recovery stays bounded (at most 11 primary calls for an always-truncated four-case batch) and never silently raises the token budget. The review receives request text without the first model's answer. Both models must return exact case IDs, a phrase copied from the request, and finite confidence in [0,1]. Unresolved or low-confidence review results use the existing three-step fallback. Confidence is a routing heuristic, not a calibrated probability or proof of correctness.

Qwen processes screenshots, image-only PDF pages and bounded visual rechecks. SQL, JSON, logs and text PDF extraction stay deterministic. Model output remains observations; final status, policy application and remediation order remain deterministic. Changing the model does not automatically solve evidence attribution or state-reconstruction defects.

Groq's published free-plan limits for these models were checked on 25 October 2026: 30 RPM, 8000 combined TPM, 1000 RPD, 200000 TPD per model. Actual account limits can differ. See [models](https://console.groq.com/docs/models), [vision](https://console.groq.com/docs/vision), [structured outputs](https://console.groq.com/docs/structured-outputs), and [rate limits](https://console.groq.com/docs/rate-limits). Free access is quota-limited; better accuracy requires measurement.

Every physical request/retry uses a separate per-model async queue and provider-wide concurrency limit. Queues reserve conservative UTF-8 text/schema tokens, 2048 image tokens, and the configured output allowance. Minute reservations settle to returned actual usage excluding cached input; unknown usage keeps a temporary minute estimate. Provider token-headroom/reset headers add bounds after accounting for concurrent calls. Request-limit headers represent daily counts and never overwrite RPM. Models sharing an ID use the tightest configured role limits.

Confirmed daily responses and actual tokens persist separately in `.runtime/model_cache/groq_daily_usage.json`, using UTC calendar dates and distinct model counters. Temporary reservations stay in memory and are released on all exit paths. Local quota skips never increase provider usage. Truncated and invalid responses still count their returned actual usage. Unknown usage is disclosed separately and never replaced by a persisted estimate. The old rolling ledgers are archived under `groq_quota_archive`; only provably settled actual entries migrate. This migration can undercount historical usage because old estimates cannot establish actual consumption. Provider limits remain authoritative. Use one CLI process per checkout; the ledger is not a cross-process lock.

GPT OSS intent/review use strict JSON Schema with `additionalProperties=false` and all fields required. Both use low reasoning with reasoning text omitted. Qwen vision always uses JSON Object mode and local Pydantic validation of `observations` (fact, source_reference, confidence), `ambiguities`, and `missing_information`. Facts use compact `resource_id=...;field=value` rows; a deterministic adapter restores internal record fields. Original JSON record strings are also accepted. Missing categories use the existing resource mapping. No model decides policy or deletion status.

Malformed vision output with usable text gets one separate 20B text-only formatting repair, including `failed_generation` returned by Groq with HTTP400. The image is never resent for formatting. Repair facts/quotes must occur in the source response. Dropped or uninterpretable observations preserve uncertainty. Accepted responses alone enter model caches. Observer failure is logged as `UNKNOWN observation fallback`, without claiming another provider was used.

SQL, JSON and logs keep local structured extraction. TXT uses local extraction first, with a grounded 20B text observer when needed; CSV uses structured rows. JPG, JPEG, PNG and WEBP use Qwen. PDFs extract text with `pymupdf` before rendering unreadable pages. Audio is outside the supplied dataset and remains unsupported; it is never sent to vision. A future audio extension should use Whisper transcription followed by the text observer.

The output caps default to 512/512/512 and remain configurable; `GROQ_TIMEOUT=30` controls Groq timeouts independently of Gemini. One transport retry maximum (`GROQ_MAX_RETRIES=0` or `1`) covers only 429, 500, 502, 503, 504 and transient connection/timeout failures. SDK and HTTP transport retries are disabled. JSON/schema failures and length stops use explicit recovery, never transport retries. Retries reacquire quota; shutdown cancels queued/backoff work. Startup prints effective caps, formats, reasoning effort, UTC daily actuals and retry budget. CLI totals distinguish attempted, accepted, truncated, HTTP-failed, validation-failed, locally skipped and retried calls, plus actual tokens per model.

Individual call diagnostics in `.runtime/checkpoint-<mode>.json` include actual usage, finish reason, selected rate-limit headers, safe provider error codes, and validation phase/path/type. Set `AUDIT_LOG_RESPONSE_BODY=1` to include bounded response body shapes. Unknown keys, string values and numeric values are redacted, so this is not an unredacted artifact/PII log. Request prompts, credentials, authorization headers and images are never logged. Usage totals remain separate from these redacted body shapes.

The clean environment and `requirements.lock` avoid the global installation's requests/HTTP dependency mismatch. Run with the activated environment or `.venv\Scripts\python.exe`. Validate with `python -m pip check`.


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

- Groq intent uses configurable batches of four and independent secondary review for flagged cases; Gemini retains batches of 20. Groq local JSON/schema/grounding validation errors do not trigger another attempt; a valid partial intent batch may request missing cases once. Gemini retains its existing single interpretation repair. The final fallback checks explicit non-deletion/negation first, multilingual deletion stems second, and defaults to NON_DELETION with warning.
- Groq transport retries come from `GROQ_MAX_RETRIES` (default one); Gemini retains up to four retries. Both use exponential delays of 1, 2, 4, and 8 seconds plus up to 25% jitter, capped at 60 seconds. Each attempt must reacquire shared quota. Retry only HTTP 408/429/5xx (also Groq 409), timeouts, and connection/network failures. Permanent HTTP client errors are not retried. Exhausting transport retries does not trigger another interpretation retry.
- Respect `Retry-After`, Groq reset headers and Google's `RetryInfo` delay. A provider-requested wait longer than 60 seconds defers further calls to that model for the indicated window while cases continue through fallbacks. Every physical attempt is counted separately; failures with missing token usage remain unknown.
- Identity links follow explicit stable user ownership and eligible history, never names/phone coincidences or numeric suffixes.
- Evidence is parsed once, with primary/replica scopes and capture/observation times. Resource retrieval has at most two link-expansion passes.
- Stage 3 allows one targeted recheck. Operation reports do not prove resulting state. Retention, anonymization, redaction, tombstones, active flows, and restore access are evaluated from supplied rules.
- Stage 4 has no model calls and follows the mandated phase/operation/system/resource order. Findings and COMPLETE checks cite eligible evidence; future INCOMPLETE actions/checks have empty evidence IDs.
- Recoverable failures do not drop cases. An eligible initial extraction failure or targeted observer recheck failure always prevents COMPLETE, preserving prior facts without inventing findings. Best-evidence can still estimate COMPLETE for other uncertainty, while `--uncertainty incomplete` treats all uncertainty conservatively. With no usable state evidence, the last resort is INCOMPLETE with available steps, possibly an empty array. These guarantee row coverage, not semantic correctness; diagnostics disclose the estimates. `--uncertainty incomplete` uses the conservative comparison policy.

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
