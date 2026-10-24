# Ghost Data Still Exists — deletion-audit CLI

A hackathon implementation of the locked four-stage pipeline: authorization and guarded identity resolution; evidence observations; deterministic state/policy analysis; deterministic decisions and canonical remediation steps. The runner adds progress, checkpoints, evaluation, usage reporting, and packaging.

## Setup

Use Python 3.10 or newer from the repository root:

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

On macOS/Linux use `.venv/bin/python` instead. Activate the environment or substitute its Python path in the commands below. PyMuPDF is the only third-party dependency; CSV, SQLite, HTTP requests, CLI progress, tests, and packaging use the standard library.

## Configure Gemini

Copy `.env.example` to an uncommitted `.env`, then set `GEMINI_API_KEY`, `GEMINI_TEXT_MODEL`, and optionally `GEMINI_VISION_MODEL` to model IDs actually available in your Google AI Studio project. Alternatively set these as environment variables. An AI Pro subscription does not establish direct API entitlement; API keys, model access, billing, and quotas are separate account facts. The program does not enable billing.

No model ID or paid rate is guessed. Without a key and text model, the application runs its deterministic fallbacks and clearly warns that vision extraction is unavailable. You can force this with `--offline`. This makes the CLI runnable before API setup; it does not prove live multimodal accuracy. Groq/local backends are later alternatives if needed, rather than mandatory dependencies.

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

- Intent interpretation uses batches of 20, one retry for affected cases, then explicit non-deletion/negation, multilingual deletion stems, and finally NON_DELETION with warning.
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

Challenge: https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists
