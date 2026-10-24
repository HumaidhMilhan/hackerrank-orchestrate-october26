# Ghost Data Still Exists: locked hackathon implementation design

Date: 24 October 2026. Status: decisions locked by the user; CLI implementation complete, with offline verification. Live model/vision validation and accuracy refinement await API configuration.

This document replaces the earlier production-oriented design with the lean decisions finalized stage by stage in the conversation. The target is a viable solution for a 24-hour hackathon. There are four core audit stages and a fifth runner/evaluation layer. The application is a terminal CLI showing progress, current status, warnings, and errors.

## 1. Goal and implementation boundary

Build a runnable Python program that reads participant-facing inputs from `dataset/` and writes root-level `output.csv` with exactly 518 data rows, one per evaluation request, sorted by `case_id`. The exact columns are `case_id,deletion_status,steps_json`.

The program investigates the supplied artifacts and proposes remediation. It does not execute deletion, disable real services, or restore data. Use only participant-facing inputs. Public sample answers are evaluation labels, never prediction inputs, prompts, runtime lookup tables, or hardcoded case branches. Organizer files, generator internals, hidden answers, and case/resource number patterns are excluded.

Every evaluation case receives a row. Recoverable parser, provider, interpretation, and per-case processing errors use bounded retries and the agreed fallbacks rather than aborting the dataset run. Warnings and estimates are recorded outside the required CSV. Never invent resources, observations, findings, or evidence references to fill missing information.

## 2. Selected approach and tools

The user selected a four-stage deterministic pipeline with a bounded investigation loop. LLMs interpret request language, extract observations, and clarify evidence. Code applies authorization mapping, identity-link guards, temporal rules, deletion policy, final status selection, step generation, and serialization. Stage 5 runs and evaluates those stages; it introduces no additional adjudicator.

The alternatives discussed were a fixed pipeline with no follow-up, local OCR before vision, and conservative INCOMPLETE for all remaining uncertainty. The selected approach uses one targeted recheck, vision for screenshots, local PDF text extraction, and best-evidence estimation for remaining uncertainty. Conservative INCOMPLETE remains an evaluation comparison, not the current default.

Use Python, standard-library CSV/JSON/SQLite/argparse/logging tools, dictionaries and sets, local PDF text extraction, and a small model-provider helper. Use PyMuPDF for PDF text extraction, which is already available in the inspected environment. Shared SQL snapshots are separate in-memory SQLite databases. A small filesystem cache and case checkpoint are sufficient; no hosted database or general-purpose orchestration framework is required.

Gemini is the initial provider preference. Groq or a local model are alternatives if Gemini access, quota, or capability is unsuitable; implement an alternative only when needed, rather than building three full backends upfront. Exact text/vision model IDs are runtime configuration values and must reflect actual available models. Credentials come only from environment variables or an ignored local `.env`; no credentials enter source, logs, reports, or archives. A consumer subscription is not proof of API entitlement: confirm usable API access and quotas before relying on it. Do not enable billing automatically.

## 3. Stage 1: authorization and guarded identity resolution

### Authorization

Send request text in batches of **20** for LLM interpretation. Return `case_id`, `DELETION` or `NON_DELETION`, and a short supporting phrase copied from the original request. The model does not return a final deletion status.

Code validates the labels, supporting spans, and that every requested case appears exactly once. Retry failed, missing, or invalid interpretations once, only for affected cases. Then apply the fallback in this exact order:

User-requested transport update after live testing: the provider helper now owns up to four transient transport retries after the initial call, using exponential backoff (1, 2, 4, 8 seconds), up to 25% jitter, and a 60-second delay cap. Only HTTP 408/429/5xx, timeout, and connection/network errors qualify. Permanent client errors and exhausted transport requests go directly to fallback rather than consuming the separate interpretation-repair retry. Honor server retry timing; a requested wait above 60 seconds defers calls to that model for the indicated interval while still producing case rows. Count every physical attempt in usage. The single interpretation-repair limit applies to invalid/missing model content, not transport failures.

1. **Explicit non-deletion / negation check -> NON_DELETION.** Include multilingual negation and clear access/correction/export/marketing-only requests. Match intent and the scope of negation, not isolated keywords.
2. **Multilingual affirmative deletion stems -> DELETION.** Normalize case and Unicode and cover deletion expressions in the languages present in participant requests. Build general language patterns, not case-specific mappings.
3. **Final default -> NON_DELETION plus warning.** This is a best-effort fallback and may be less accurate than model interpretation.

For example, "export my data; do not delete my account" is NON_DELETION, while "export my data, then delete my account" and "do not send confirmation emails; delete my account" authorize deletion. Multilingual affirmative and negated forms require tests.

Code maps NON_DELETION to NOT_APPLICABLE with `steps_json=[]` and bypasses per-case deletion investigation. DELETION continues to Stage 2.

### Identity

Use two indexes: normalized email -> candidate user IDs, and user ID -> known identifiers with their source references. Match the supplied email against current and historical values. Collect emails, phones, hashes, and names connected by explicit ownership to the same stable `user_id`.

Use only information available at or before `audit_at`. Exclude later audit events; a current snapshot updated after the cutoff is not itself proof of the earlier identity. Eligible identity history can supply earlier values. Preserve raw identifiers as well as normalized search values; do not remove email dots/plus tags or invent phone country codes or hash algorithms.

Shared names or phone numbers do not merge subjects. Keep ambiguous candidates separate until evidence establishes ownership. If no identity matches, continue with the supplied request email as the search seed. Resource-history links are discovered in Stage 2, not in a separate graph-building subsystem.

Output: case ID and cutoff, authorization, candidate subject IDs, known identifiers and source references, and warnings.

## 4. Stage 2: evidence observations

### Shared extraction

Read the manifest and actual contents of the **94** artifacts once: **24 SQL, 28 JSON, 26 logs, 11 screenshots, 4 PDFs, and 1 text file**. Reuse parsed content across cases; cache accepted model-assisted extraction by source content and extractor/prompt/model configuration. A failed or partial extraction is recorded as such, not cached as a successful empty result.

| Format | Extraction |
| --- | --- |
| SQL | Load each snapshot separately into in-memory SQLite; inspect real schemas and retain primary/replica/table scope |
| JSON | Traverse records, service exports, and nested snapshots; preserve applicable parent and record timestamps |
| Logs | Extract observations and operation claims; join identifier and result lines using trace IDs and explicit context |
| Text | Read and parse records/prose with line references |
| PDF | Extract text from every page locally; use vision only where missing text or layout loses important associations |
| Screenshot | Use Gemini vision to extract identifiers, resource fields, timestamps, relevant rows, and selected-record details |

LLM extraction returns observed facts and their source locations, not policy decisions, verdicts, or remediation actions. Preserve null versus missing fields. A workflow badge or successful delete operation is a claim; an actual record read or completed lookup is a scoped observation. Do not interpret a cache miss or arbitrary missing row as deletion.

Repair invalid extracted model content once; transient transport failures follow the provider backoff policy above. Then continue with available content and a warning. Reuse cached media observations across cases rather than calling vision for each person. A text-only fallback model cannot silently replace image interpretation.

### Case retrieval and bounded expansion

1. Search Stage 1's accepted identifiers as complete values rather than substrings.
2. Collect explicitly connected resource IDs.
3. Search those resources in evidence and global activity.
4. Follow explicit links to additional resources for **at most two expansion passes** after the initial search.

Use resource history to find absent or anonymized resources whose current payload has no identifiers. Historical audit attribution alone does not make a correctly anonymized current payload noncompliant. Do not infer ownership from file names, manifest origin, similar identifiers, or numeric suffixes.

Filter evidence capture time and observation/event time against `audit_at` before using observations in a case or sending case context to a model. Later bundles remain ineligible even if they describe earlier events. Keep primary and replica observations separate, and keep ambiguous subjects separate until grounded links resolve them.

Output observations contain: participant evidence ID (`file_id`, `activity_id`, or `audit_id`), system/resource IDs when available, capture and observation times, scope, extracted facts, claim/observation kind, and a locator such as table/row, JSON path, PDF page, screenshot region, or log lines. Return extraction/retrieval warnings alongside them. The manifest is a locator, not proof of membership or state.

## 5. Stage 3: deterministic state, policy, and recreation-risk analysis

### Reconstruct state

Group observations by system, resource, and store/replica scope. Exclude later evidence and prefer the latest applicable direct state observation within the same scope. After checking eligible history, carry that observation forward to the cutoff unless later evidence challenges it. This is a supplied-corpus inference, not proof that unrecorded changes are impossible.

A later successful-operation claim does not establish the resulting state or override a direct read. A later possible mutation without a confirming read creates uncertainty. Primary absence does not cancel replica presence. Failed extraction, a cache miss, or an incomplete query cannot establish absence. A negative lookup proves only its defined scope; absence from a snapshot requires evidence that its relevant population was completely captured and checked.

If equally applicable observations conflict, retain the conflict for the targeted recheck and subsequent best-evidence handling rather than describing compliance as verified. Do not impose a universal file-format ranking or invent a snapshot-age threshold.

### Apply supplied policy

Load `deletion_rules.csv` and implement its conditions in ordinary code. Derive record category from actual metadata, table structure, and document role; an unclear category or condition can be sent back for interpretation. Code selects the applicable rule and treatment.

| Treatment | Required check |
| --- | --- |
| DELETE | Relevant copy is absent |
| REDACT | Prohibited identifiers are removed while permitted context remains |
| ANONYMIZE | Current record no longer exposes prohibited attribution through identifiers or links |
| RETAIN | Required record remains available under the supplied retention/hold condition |
| ACCOUNT_TOMBSTONE | Preserve permitted stable `user_id`; remove name, email, phone, email hash, and other prohibited direct identifiers |
| BACKUP_ARCHIVE | Preserve the affected archive and block restoration of prohibited subject data |

Inspect fields rather than trusting a "redacted" or "anonymized" label. A surviving hash or prohibited subject reference can still identify the person. A surviving account row qualifies as a tombstone only when its state and purpose establish that category. Do not invent extra deletion or redaction obligations for records that the supplied policy permits retaining.

### Sync and restore paths

Use an adjacency map of evidence-backed source/process/destination links. Follow paths with a visited set, including cycles, to identify active subject-related sync, import, replication, or restore processes capable of recreating prohibited data. Exclude unrelated processes and paths preserving only permitted data. An unknown path is not automatically safe.

Record required disabling or restore blocking. This graph identifies risks; it never topologically sorts the submitted remediation array.

### One targeted recheck

Allow **one targeted return to Stage 2 per case**, bundling relevant questions. Re-read existing rows, traces, pages, or images first; use model interpretation only if needed. Do not start an unbounded investigation loop or add another general adjudicator.

After rechecking, preserve supported observations and unresolved warnings and continue. Output each resource/process's state, applicable rule, required treatment, selected supporting evidence, and internal `COMPLIANT`, `VIOLATION`, or `UNCERTAIN` assessment. These are not new public statuses. Never create facts or citations to fill a gap.

## 6. Stage 4: deterministic decision and output

Stage 4 has no LLM calls. It selects status, generates steps from fixed templates, validates them, and produces one result per case.

### Status precedence

| Condition, evaluated in order | Output |
| --- | --- |
| Stage 1 NON_DELETION | NOT_APPLICABLE with `[]` |
| Any supported policy violation or prohibited recreation risk | INCOMPLETE |
| All required treatments supported as compliant, no unresolved issue | COMPLETE |
| Remaining uncertainty, at least one supported compliant direct-state assessment, and no established violation | Estimate COMPLETE; record the reason and uncertainty outside the CSV |
| No usable state evidence or no supported basis for a completion estimate | Last-resort INCOMPLETE with warning and available supported steps, possibly `[]` |

One violation outweighs any number of compliant records. Do not use majority voting, reported workflow status, or operation success as proof. Best-evidence estimation is the user-selected initial fallback; it is not the same as verified completion.

Estimated COMPLETE can fail the challenge requirement to prove every relevant treatment. Sparse INCOMPLETE fallbacks can lack a complete supported remediation plan. These are explicit scoring limitations of always producing a row under unresolved evidence; never conceal them by inventing steps. Record estimated case IDs, reasons, unresolved facts, and whether an exception fallback was used in diagnostics. Missing knowledge cannot be eliminated by deterministic rules alone.

### Step templates

| Established issue | Finding | Remediation | Verification |
| --- | --- | --- | --- |
| DELETE-required copy present | REPORT_REMAINING_RECORD / PRESENT | DELETE_RECORD / ABSENT | VERIFY_RECORD_ABSENT / ABSENT |
| REDACT-required identifiers exposed | REPORT_EXPOSED_PII / PRESENT | REDACT_RECORD / REDACTED | VERIFY_RECORD_REDACTED / REDACTED |
| ANONYMIZE-required attribution exposed | REPORT_EXPOSED_PII / PRESENT | ANONYMIZE_RECORD / ANONYMIZED | VERIFY_RECORD_ANONYMIZED / ANONYMIZED |
| Prohibited active copy flow | REPORT_ACTIVE_DATA_FLOW / ACTIVE | DISABLE_DATA_FLOW / DISABLED | VERIFY_DATA_FLOW_DISABLED / DISABLED |
| Unsafe restore path | REPORT_RESTORE_RISK / ACTIVE | BLOCK_RESTORE / BLOCKED | VERIFY_RESTORE_BLOCKED / BLOCKED |

Also generate required verification for already-compliant resources in the established case scope. Ordinary retained security/legal records use VERIFY_RECORD_PRESENT / PRESENT. Tombstones use VERIFY_RECORD_REDACTED; backup archives use VERIFY_RESTORE_BLOCKED. Preserve their required reference/archive as part of the specialized check without mechanically adding duplicate PRESENT checks.

- COMPLETE: verification only, each backed by eligible evidence. Even an estimated completion cannot invent checks for unread resources or use an empty array as proof.
- INCOMPLETE: supported findings, required remedies, and the available required future verification set. Findings cite proving evidence; all remediation and all future verification use `evidence_id=""`, including checks of already-compliant retained resources.
- NOT_APPLICABLE: `[]` only.

Select the latest applicable direct observation that proves the assertion in its scope; break equivalent-proof ties deterministically by evidence ID and locator. A replica-presence finding cites the replica evidence, not the primary-absence result. Preserve additional identity/derivation references internally when one public citation needs contextual linkage. If an issue cannot be represented with an allowed operation, record the limitation rather than invent an operation.

### Canonical ordering and validation

Sort by phase, then the operation sequence below, then `system_id`, then `resource_id`, using ascending literal strings. Deduplicate equivalent logical steps and assign consecutive numbers after sorting. Case IDs also sort as literal strings.

| Phase | Operation sequence |
| --- | --- |
| FINDING | REPORT_REMAINING_RECORD, REPORT_EXPOSED_PII, REPORT_ACTIVE_DATA_FLOW, REPORT_RESTORE_RISK |
| REMEDIATION | DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE_RECORD, REDACT_RECORD, ANONYMIZE_RECORD |
| VERIFICATION | VERIFY_RECORD_ABSENT, VERIFY_RECORD_PRESENT, VERIFY_RECORD_REDACTED, VERIFY_RECORD_ANONYMIZED, VERIFY_DATA_FLOW_DISABLED, VERIFY_RESTORE_BLOCKED |

Canonical order is authoritative. Do not add downstream-first tie breakers, topological sorting, or intermediate checks out of phase. Disabling and blocking precede record changes through the prescribed ranks. The program proposes actions and does not claim to execute a dependency-safe live workflow under conflicting constraints.

Every step has exactly: `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`. Validate field types, operation/state combinations, evidence eligibility, supported attribution, numbering, ordering, and JSON serialization. Repair malformed steps from templates, or exclude unsupported steps with a warning and reapply status rules. Never suppress the case row. Semantic uncertainty remains visible in diagnostics rather than being falsely reported as verified compliance.

## 7. Stage 5: CLI runner, evaluation, and deliverables

### Execution and console behavior

Use one CLI runner around the four stages. Resolve dataset/output paths from the repository root, not the shell's current directory. Use standard-library `argparse` and `logging`; the CLI does not require a dashboard or terminal UI framework.

The CLI must show:

- Run mode, request count, provider and model names when configured, and preparation status.
- Evidence extraction progress: completed/total files and cache hits.
- Case progress: completed/total, current case ID, current core stage, and running COMPLETE/INCOMPLETE/NOT_APPLICABLE counts.
- Current activity such as interpreting an intent batch, reading evidence, assessing policy, performing the one recheck, or writing output.
- Visible warnings/errors with case or evidence IDs, a short sanitized explanation, and the recovery action: retry, fallback, skipped unsupported observation, or resume.
- A final summary: elapsed time, rows written, status counts, estimated/fallback case counts, warnings/errors, model-call/token totals, and paths to output and reports.

Progress/status goes to stderr. CSV is written to a file, never mixed with terminal logs. Interactive terminals may refresh one progress line; redirected/non-interactive runs receive ordinary newline messages. `--quiet` hides routine progress, not warnings/errors or the final summary. `--verbose` adds diagnostic detail without leaking secrets or raw provider credentials. Print case IDs rather than personal identifiers in routine progress.

Proposed interface, now fixed as implementation defaults:

```text
python code/main.py                         # full run -> output.csv
python code/main.py --samples               # 32 samples -> sample_predictions.csv
python code/main.py --resume                # resume compatible full-run checkpoint
python code/main.py --samples --resume      # resume compatible sample run
python code/main.py --quiet                 # compact console output
python code/main.py --verbose               # additional diagnostics
python code/evaluation/main.py              # sample/custom evaluation and reports
```

`--quiet` and `--verbose` are mutually exclusive. These commands are implemented by the CLI entry points.

Run shared extraction once, use the agreed retry limits, and checkpoint each finished case. Cache/checkpoint files and diagnostics live in an ignored root runtime directory outside `code/`. Reuse checkpoints only when inputs, policy/code configuration, and selected model/prompt settings are compatible. An interrupted run can resume without repeating accepted model extraction. Do not label a checkpoint or partial diagnostic file as the completed 518-row submission.

Catch recoverable per-case processing errors, log them visibly, and pass the best available context through Stage 4's fallback so later cases continue. When all requests have rows, validate exact expected case coverage and write sorted CSV. A successfully completed run exits 0 even if it used documented fallbacks; actual inability to read mandatory inputs or write an output is reported clearly as a command failure rather than pretending a valid artifact exists. The always-output requirement assumes readable inputs and writable output storage; it does not justify fabricated case IDs.

### Evaluation

Generate sample predictions without reading sample labels. Only the evaluator opens `sample_output.csv`. Compare parsed JSON, ignoring whitespace and object-key order while retaining array order.

| Metric | Definition |
| --- | --- |
| Status accuracy | Correct statuses / labeled cases |
| Step precision/recall | Exact multiset matches of step content excluding step_no, retaining phase, operation, system, resource, state, and evidence ID; report F1 as well |
| Field accuracy | Matching values among the seven fields at aligned array positions; missing/extra positions count as seven mismatches |
| Sequence accuracy | Exact ordered step-array equality, including step numbers and citations |
| Exact row accuracy | Correct status and complete parsed step array |

For empty expected and predicted step arrays, count their sequence/field/step comparison as correct. If only one array is empty, its step and field comparison scores zero. Report sample and custom-fixture metrics separately; do not claim measured hidden accuracy for the 518 unlabeled evaluation cases.

Reuse the same saved Stage 3 assessments to compare best-evidence versus conservative-INCOMPLETE handling on uncertain sample cases, without more API calls. Inspect errors before changing a rule. If estimates cause false COMPLETE decisions, change the general uncertainty branch to INCOMPLETE; fix extraction/identity/policy bugs at their source. Never choose a per-case rule from its sample answer.

Create at least four small independent fictional fixtures: multilingual affirmative/negated deletion, primary absence with replica presence, a tombstone with a permitted stable reference and prohibited identifier, and after-cutoff evidence that must not affect the result. Include malformed-model/API-failure and CLI warning/progress checks in the relevant tests. Expected custom results belong in source and the Markdown evaluation report, not only ignored raw data formats.

### Usage and packaging

Track actual provider/exact model names, calls, input/output tokens, cache reuse, and estimated costs. Count retries and schema-repair calls as actual calls; distinguish unknown usage from zero. Separate sample/development usage from the final full-dataset run. Report shared extraction once, disclose reuse from earlier runs, and compute the full-run per-request averages over 518 without double counting cached work. A free monetary cost does not mean zero tokens or quota consumption. Use verified model rates when available and label cost estimates.

Write required metrics, custom cases, failures, and improvements directly into `code/evaluation/evaluation_report.md`. Write final-run provider/model/call/token/cost totals and per-request averages directly into `code/evaluation/usage_report.md`. Maintain append-only root `log.txt` for the conversation transcript. The runner must not claim these reports exist or contain results before they are actually generated.

Before packaging, check row count and exact case coverage, headers, statuses, JSON, step fields/order, evidence references, and warning/estimate counts. Build `code.zip` with runnable code, prompts/configuration, README, tests, and both reports. Exclude dataset files, caches, checkpoints, virtual environments, credentials, and nested archives. Report output/archive paths in the CLI. Do not upload or submit artifacts automatically.

## 8. Lean implementation boundaries and build order

Keep a small source layout:

| File | Responsibility |
| --- | --- |
| `code/main.py` | CLI, progress, shared preparation, case loop, checkpoint/resume, output writing |
| `code/stage1.py` | Batched intent interpretation, fallback, guarded identity indexes |
| `code/stage2.py` | Format extraction, observation cache, scoped retrieval and link expansion |
| `code/stage3.py` | State reconstruction, policy checks, relevant flow/restore analysis, one recheck |
| `code/stage4.py` | Deterministic status rules, step templates, canonical sorting and validation |
| `code/llm.py` | Gemini/configured provider calls, response validation, retry helper and usage accounting |
| `code/evaluation/main.py` | Public/custom evaluation, uncertainty comparison and reports |
| `code/tests/test_pipeline.py` | Focused policy, fallback, temporal, serialization and CLI regression tests |

Use plain internal dictionaries/sets for case contexts, observations, and assessments. Keep prompts in source or Markdown so the code judge can inspect them. Add a shared model/helper file only if repeated structures make it necessary; do not scaffold a framework in advance.

Implementation order is: Stage 1 plus basic CLI/provider helper; shared extraction and Stage 2 retrieval; Stage 3 rules and recheck; Stage 4 output and fixed templates; Stage 5 integration/evaluation/usage reporting; final sample fixes, full run, and packaging. Tests focus on real failure modes rather than mirroring reversible implementation details. No extra design approvals or architecture expansion are required by this document; these are the finalized decisions the user asked to lock.

## 9. Acceptance and known limitations

Implementation is ready for submission when the CLI completes a full run with all 518 unique sorted case rows, structural validation passes, public/custom evaluation and uncertainty-policy comparison have been run, actual usage/evaluation reports are present, and the code archive has been inspected. Estimated and fallback cases must be visible in diagnostics and reports even when CSV structure is valid.

The 24-hour constraint is a scope constraint; the repository does not configure an official challenge end time. Exact API access, model IDs, quotas, and available credits remain runtime facts to verify, not reasons to reopen the architecture. No numeric paid API budget was supplied and the program must not enable paid billing automatically.

The selected estimates and last-resort rows guarantee coverage under recoverable uncertainty, not perfect semantic accuracy. An unread artifact or mistaken language interpretation can still affect scoring. Evaluation can justify a general fallback change, but neither a successful CLI run nor matching the public samples proves hidden-dataset accuracy.
