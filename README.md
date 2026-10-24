# Ghost Data Still Exists — deletion-audit CLI

A hackathon implementation of the locked four-stage pipeline: authorization and guarded identity resolution; evidence observations; deterministic state/policy analysis; deterministic decisions and canonical remediation steps. The runner adds progress, checkpoints, evaluation, usage reporting, and packaging.

## Setup

Use Python 3.10 or newer from the repository root:

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

On macOS/Linux use `.venv/bin/python` instead. Activate the environment or substitute its Python path in the commands below. PyMuPDF extracts PDFs; Google's `google-genai` SDK handles Gemini calls. CSV, SQLite, quota scheduling, CLI progress, tests, and packaging use the standard library.

## Configure Gemini

Copy `.env.example` to an uncommitted `.env`, then set `GEMINI_API_KEY`. The user-selected defaults are:

```text
GEMINI_MODEL=gemini-3.6-flash
GEMINI_RPM=5
GEMINI_TPM=250000
GEMINI_MAX_CONCURRENCY=2
```

Both text and vision use `GEMINI_MODEL`. Optional `GEMINI_TEXT_MODEL` and `GEMINI_VISION_MODEL` override them individually. All settings can instead come from environment variables, which take precedence over `.env`. API access, billing, and granted quotas remain facts of the Google project; configuring a local limit does not grant quota. The program does not enable billing.

Without a key, the application runs its deterministic fallbacks and clearly warns that vision extraction is unavailable. You can force this with `--offline`. This makes the CLI runnable before API setup; it does not prove live multimodal accuracy. Groq/local backends remain alternatives if scheduled Gemini access is unsuitable.

Every Gemini SDK operation goes through a shared async queue in `code/quota.py`; audit stages never call the SDK directly. The scheduler enforces rolling 60-second RPM/input-TPM limits and at most two active operations. It counts images/text with the provider before generation, caches those counts, reserves schema/config overhead, and retains conservative reservations for failed attempts. Token-count calls also consume local RPM and concurrency; generation attempts consume input TPM. Accepted response-cache hits consume no API quota. SDK automatic retries and function calling are disabled; custom retries must rejoin the queue. This is one quota pool for one CLI process; other programs using the project can still consume its Google quota.

The synchronous CLI uses the same queue through `ModelClient.request_json`; concurrent integrations can await `request_json_async` and finish with `aclose`. An explicit httpx transport with zero reconnect retries prevents the SDK's aiohttp reconnect path from bypassing the queue. Shutdown cancels and gathers pending requests, including backoff waits, before closing the worker loop. Existing audit decisions and output ordering remain deterministic.

Optional `AUDIT_INPUT_USD_PER_MILLION`, `AUDIT_OUTPUT_USD_PER_MILLION`, and `AUDIT_CACHED_USD_PER_MILLION` must contain verified rates for the configured model. Leave them unset when unknown; reports distinguish unavailable cost from zero. Configure separate-model pricing in code before using differently priced text/vision models; one set of rates is otherwise applied to all models and is only an estimate.

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

- Intent interpretation uses batches of 20, one repair for affected invalid/missing interpretations, then explicit non-deletion/negation, multilingual deletion stems, and finally NON_DELETION with warning.
- SDK transport failures use up to four retries after the initial request: exponential delays of 1, 2, 4, and 8 seconds plus up to 25% jitter, capped at 60 seconds. Each attempt must reacquire shared quota. Retry only HTTP 408/429/5xx, timeouts, and connection/network failures. Permanent HTTP client errors are not retried. Exhausting transport retries does not trigger another interpretation retry.
- Respect `Retry-After` and Google's `RetryInfo` delay. A provider-requested wait longer than 60 seconds defers further calls to that model for the indicated window while cases continue through fallbacks. Every physical attempt is counted separately; failures with missing token usage remain unknown.
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
