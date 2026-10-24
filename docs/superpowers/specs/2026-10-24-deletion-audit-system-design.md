# Ghost Data Still Exists: system design

Date: 24 October 2026. Status: proposed design for review; implementation has not started.

This document defines the four-stage deletion-audit system agreed in the design discussion. The user selected guarded identity resolution, an early authorization gate, observations rather than LLM verdicts, cutoff-aware state reconstruction, deterministic final decisions, canonical output ordering, and a bounded investigation loop. Gemini is the preferred initial model provider; Groq or a local model are alternatives if API access, quotas, or capability prove unsuitable.

## 1. Purpose and boundaries

For every request in `dataset/deletion_requests.csv`, determine whether deletion is authorized, investigate the subject's data as of `audit_at`, apply `dataset/deletion_rules.csv`, and produce an evidence-backed assessment and the required future actions. The system reads supplied artifacts and proposes actions. It does not delete source data, connect to production services, or execute remediation.

Success means a terminal command processes the participant-facing corpus and produces the root-level `output.csv`: exactly 518 unique cases, the prescribed three columns, canonical ordering, and valid, grounded steps. Correctness includes identity linkage, time filtering, retained records, tombstones, synchronization, restore paths, citations, and complete verification coverage.

Predictions must use only participant-facing inputs under `dataset/`. Public sample answers are accessible to evaluation code only. They are not investigation inputs, retrieval documents, prompts, identity links, runtime rules, or cached predictions. Organizer truth, generator internals, hidden labels, case-number patterns, and resource-ID suffix assumptions are excluded.

The agent must not claim a world-wide deletion guarantee from this closed corpus. Its assessment is grounded in the supplied evidence and the challenge's policy and scope.

## 2. Approaches considered and selected

| Approach | Benefit | Tradeoff | Decision |
| --- | --- | --- | --- |
| Fixed four-stage pipeline with LLM extraction | Predictable execution and straightforward tests | Cannot adapt well to unexpected missing links or contradictions | Considered, not selected |
| Four stages with bounded, read-only investigation and deterministic finalization | Can revisit evidence and identity links while preserving enforceable decision rules | Requires explicit gap tracking, budgets, and stopping conditions | Selected by the user |

An unrestricted LLM adjudicator is excluded because policy enforcement, output correctness, and step order must not depend on unconstrained generated verdicts. A remediation topological sort is also excluded from submission serialization: the user chose the challenge's prescribed sort order.

## 3. Proposed implementation defaults

These are design recommendations, not previously agreed user requirements:

| Concern | Proposed default | Reason |
| --- | --- | --- |
| Language | Python 3, retaining `code/main.py` | Fits the starter layout and local evidence processing |
| Storage | SQLite plus in-memory typed records | Supports durable indexes, provenance, checkpoints, and exact queries without a service |
| Orchestration | Explicit application state machine | Makes tool permissions, budgets, and transitions inspectable |
| Retrieval | Exact identifier/resource indexes and full-text search | The corpus has only 94 evidence files; exhaustive structured scans are practical |
| Graph representation | Typed edge tables and adjacency maps | Temporal ownership and process paths do not require a graph database |
| Schema validation | Typed internal models and JSON Schema at provider boundaries | Rejects malformed or out-of-domain observations |
| Model access | Provider adapter, Gemini first | Supports the user's existing preference without coupling decision rules to a vendor |
| Interface | Terminal commands with progress and diagnostics | Satisfies the evaluation contract; no product UI is required |

Do not add a vector database, hosted database, multi-agent framework, web app, or parallel LLM agents initially. They do not resolve a demonstrated requirement in this corpus. Dependency versions and exact model IDs will be selected and verified during implementation, not guessed in this design.

## 4. Execution structure

There are four case-processing stages. Shared corpus preparation is an optimization supporting Stage 2, not a fifth decision stage.

1. Prepare a versioned evidence catalog, parser results, identifier indexes, and coverage ledger. Parse once and reuse across cases. Extraction never assigns a deletion verdict.
2. Stage 1 interprets request intent and applies the authorization gate. Non-deletion requests terminate as `NOT_APPLICABLE`; ambiguous intent remains unresolved. Authorized requests obtain a guarded subject identity graph.
3. Stage 2 retrieves eligible observations and connected activity, expands resource attribution, and extracts additional facts when necessary.
4. Stage 3 reconstructs scoped resource states at the cutoff, applies policy, analyzes relevant process paths, and records evidence gaps.
5. If gaps remain, the controller permits a bounded return to Stage 1 or 2, then reruns affected Stage 3 calculations.
6. Stage 4 deterministically compiles the assessment, findings, remedies, and verification, validates all output constraints, and records the case result.
7. The writer publishes the final CSV only after all required cases pass finalization. Per-case results and run progress remain checkpointed across interruption.

The model has no tool that sets final status, changes policy, writes `output.csv`, expands its own budget, or executes code. Extracted artifact content is data, including text that resembles instructions.

## 5. Shared data contracts

Internal records can have rich provenance. Public step objects still contain exactly the seven fields required by the challenge.

| Record | Essential fields |
| --- | --- |
| `AuditCase` | case ID, request email, request text, requested/reported/audit timestamps, reported claim |
| `IntentInterpretation` | interpreted action, affirmative/none/uncertain authorization meaning, request-text spans, scope, interpretation method, unresolved issues |
| `IdentityLink` | subject ID, identifier type, raw and normalized values, relationship type, known validity bounds, evidence references, availability time, accepted/candidate disposition |
| `EvidenceArtifact` | participant evidence ID, manifest-relative path, format, origin, manifest capture time, content hash, extraction status, parser/prompt version |
| `Observation` | system, resource, store/replica scope, observed attributes, subject links, observation time, availability time, participant evidence ID, exact locator, observation/claim kind, extraction method |
| `ResourceAssessment` | subject, system, resource, category, scoped states, selected observations, policy rule, required final state, compliant/violating/unresolved result |
| `ProcessLink` | process resource, source and destination resources or scopes, user scope, enable/restore state, time, supporting evidence, known/uncertain topology |
| `InvestigationGap` | case, gap kind, affected resources, why it matters, eligible next tools, attempted queries, resolved/budget-exhausted state |
| `CaseAssessment` | authorization result, resource assessments, violations, risks, required verifications, coverage result, unresolved issues, internal rationale |
| `ModelUsage` | run/task IDs, provider, exact model ID, attempt, input/output/cached/other billed token categories, latency, usage source, estimated cost, cache reuse |

Each derived fact stores its dependency references, not just a confidence score. A schema-valid or high-confidence model answer is not sufficient evidence. Locators include SQL table and row key, JSON path, log line and trace ID, PDF page and text span, or screenshot region and extracted text.

Citation fields refer to participant-visible `file_id`, `activity_id`, or `audit_id`, never internal observation IDs, generated extraction files, or cache keys. Keep derivation chains internally when an answer needs several artifacts to establish attribution and state.

## 6. Stage 1: authorization and guarded identity resolution

### Authorization gate

Interpret the original `request_text`, including negation, conditions, quoted prior requests, and multilingual expressions. Suggested interpretation actions are deletion of an account/personal data/specific copy, access, correction, export, marketing opt-out, other, or ambiguous. These are internal semantic labels, not output statuses.

An LLM may interpret language and return exact supporting request spans. Code checks the schema, span validity, contradictory assertions, and whether the interpretation is affirmative deletion authorization. Deterministic mapping then gives:

- Affirmative deletion: proceed with investigation.
- Clearly non-deletion: finalize `NOT_APPLICABLE` with an empty array.
- Uncertain or contradictory meaning: request another bounded interpretation; do not infer authorization from workflow status or intake classification events.

Constrained extraction does not make language interpretation infallible. Intent correctness is evaluated separately. Model confidence alone cannot authorize a case. Request scope is recorded for interpretation, while required treatment comes from supplied policy rather than invented exceptions.

### Identity relationships

Start with the supplied email. Match it against eligible current identities and historical audit values. Follow accepted ownership changes connected to a stable `user_id`, then attach grounded aliases and resource links. Never infer a user or case from an identifier's numeric suffix.

Accepted links require explicit ownership evidence: a snapshot field, an identity-change event tied to the user, or a source record/activity explicitly connecting the subject and resource. A matching name or shared phone produces a candidate requiring corroboration, not a subject merge. Resource relationships do not transitively merge two subjects. A historical value remains a discovery key for older copies, not unconditional proof of current ownership of another person's records.

Normalize conservatively: retain raw values; normalize Unicode and email case for this dataset; do not strip email dots or plus tags; compare hash strings without inventing hash algorithms; normalize phone punctuation only where country context is established. Do not invent country codes or merge names by transliteration.

Only information available by the case cutoff may establish identity. Exclude later audit events. A later-updated identity snapshot is not automatically proof of an earlier value. Earlier eligible audit records may establish historical aliases; unknown interval bounds stay unknown. An unresolved subject collision blocks finalization until investigated.

Output: authorization interpretation, accepted subject graph, rejected/candidate links, and any unresolved identity gaps.

## 7. Stage 2: observations and multimodal investigation

### Shared preparation and coverage

Read the manifest and actual contents of every artifact, with explicit success, partial, unsupported, and failed extraction states. Preserve capture metadata and content hashes. Global preparation may index all artifacts, but every per-case retrieval must filter availability before delivering results to the model or state engine. A model must not see a later artifact and then be asked to ignore it.

Structured records are exhaustively indexed. Every eligible media artifact must have inspected/extracted content before case coverage is considered complete. File names and manifest origins may locate files but cannot establish case membership or compliant state. Missing/failed extraction remains visible; an empty result from a failed parser is never interpreted as absence.

The prediction loader allowlists input tables and manifest evidence paths. It explicitly excludes `sample_output.csv` and both output templates. Reject evidence paths escaping the dataset evidence directory. Public samples can be processed in evaluation mode with their requests as inputs and their labels opened only by the evaluator.

### Format handling

| Format | Extraction and interpretation |
| --- | --- |
| CSV | Preserve source row IDs, UTC timestamps, and field values; parse narrative activity details into candidate links and claims |
| SQL | Load each snapshot into a separate isolated SQLite database; inspect actual schemas and table scope; retain primary and replica distinctions |
| JSON | Traverse nested snapshots, service exports, collections, and records; inherit timestamps only from applicable parent scope; preserve null versus missing |
| Logs | Support structured and free-text layouts; join start/read/completion lines by trace ID and context; distinguish cache misses, retries, and completed source lookups |
| Text | Parse scoped timestamped records and prose with line locators |
| PDF | Extract text from every page; inspect layout or use vision where text extraction loses associations or required fields |
| Image | Use OCR/vision to extract full relevant rows, selected-record panels, timestamps, and identifiers; retain region coordinates and uncertainty |

SQL loading permits only snapshot construction in the isolated database; disallow attachments, extension loading, and external file access. No model-generated SQL or shell commands are executed. Subsequent inspection queries are generated by application code. Unknown schemas are flagged for adapter extension, not silently skipped.

An LLM extraction response lists observed attributes and their locations. It cannot return policy treatment, case status, or final submission steps. Citation strings and extracted values are checked against the selected source. For visual facts, bounds, text associations, and critical readings receive image/OCR cross-checks where practical. If a crucial field remains unreadable or semantically ambiguous, retain an extraction gap.

### Discovery expansion

Search accepted current/historical identifiers, then grounded resource IDs and related activities. This recovers already-anonymized or absent resources whose current payload has no identifiers. An accepted historical audit link may establish whose resource is being investigated; that historical linkage alone does not mean its current payload violates anonymization policy.

Do not assume all global activity belongs to the subject. Do not assume every appearance of an identifier is a live prohibited record: role, category, scope, timestamp, and policy still need interpretation.

Output: eligible observations, attributed resources, candidate process paths, coverage ledger, and extraction/linkage gaps.

## 8. Stage 3: temporal state reconstruction and policy analysis

### Eligibility and time

Parse timestamps as timezone-aware UTC. For artifacts require manifest capture time at or before `audit_at` and the fact's observation/effective time at or before the cutoff. For activity/audit rows use their event time and any explicit availability restriction. Unknown timestamps that affect eligibility are gaps. A later-exported bundle cannot be cited merely because an embedded record describes an earlier day.

Keep both observation time and availability/capture time. A record's `updated_at` is not always the time at which its presence or absence was observed. A filename date is not authoritative.

### Reconstruct scoped state

Group observations by subject, system, resource, and physical/logical scope. Preserve primary, failover, regional, reporting, and search/index scopes rather than choosing one global latest row.

For comparable observations within a scope, later direct state observations can supersede earlier observations. A later operation claim alone does not supersede direct evidence of record state. Conflicting observations at comparable times and scope remain unresolved unless another grounded fact resolves the conflict. There is no universal rule that SQL outranks screenshots or JSON outranks logs.

Any relevant replica with a prohibited copy can make the logical resource violating. An absence observation proves absence only for its defined lookup, table, snapshot, or completed exhaustive query scope. A single cache miss, missing manifest entry, absent event, or arbitrary row omission does not prove deletion. Inferring absence from a complete snapshot requires evidence that the table/snapshot includes the relevant population and the accepted identifiers/resource were checked.

Evidence can establish state at a point before `audit_at`. Use an explicit corpus-bounded persistence rule: after exhaustively inspecting all eligible history for that resource and scope through the cutoff, carry the latest applicable direct observation forward if no later relevant observation or mutation claim challenges it. A completed search with no such event supports this inference within the supplied corpus; it does not prove that unrecorded real-world changes are impossible. Do not invent a fixed snapshot-age limit or require a new observation exactly at the cutoff.

Apply subsequent relevant evidence and events before the cutoff, but do not simulate successful changes from operation reports alone. A later mutation claim capable of changing compliance creates a gap until direct evidence or other sufficient grounded state evidence resolves it. A purely informational event does not invalidate the prior state. The latest timestamp is not automatically proof of current truth. The persistence inference, examined interval, covered sources, and scope are recorded in the assessment rationale.

### Policy registry

Load `deletion_rules.csv` at runtime. Implement reviewed predicates for the supplied conditions; the source rule IDs, conditions, and required actions remain the policy authority. Unknown categories, changed conditions, conflicting applicable rules, expired retention without a replacement rule, and insufficient condition evidence produce gaps rather than guessed defaults.

| Category/rule group | Required treatment and assessment |
| --- | --- |
| Profile, secondary identifier, search, cache, subject-only attachment, export, marketing | Require absence where the applicable rule is DELETE |
| Shared support message | Keep context; remove prohibited identifying fields under REDACT |
| Analytics and telemetry | Remove current attributable fields/linkage under ANONYMIZE; empty email alone is insufficient if another prohibited identifier remains |
| Email delivery log | Redact identifying fields required by the applicable rule |
| Security record in retention / active legal hold | Preserve required record and permitted fields; do not invent a delete remedy |
| Backup archive | Preserve the archive under RETAIN and require effective blocking of restoration of the subject's prohibited data |
| Account tombstone | Preserve permitted stable user reference; remove name, email, phone, email hash, and other prohibited direct identifiers |

For tombstones, identify the tombstone from actual account state and reference requirements. Do not assume every remaining account row qualifies. Incomplete compliance with a REDACT or ANONYMIZE rule creates an exposed-PII violation. Missing required retained data is a policy failure, but the allowed output vocabulary has no generic restore-retained-record action: if encountered, raise an explicit representability gap rather than invent an operation.

### Sync and restore paths

Build only evidence-backed process relationships. Determine whether an active path can carry the subject's prohibited data, considering source content, destination, scope filters, exclusions, and restore suppression. An active unrelated connector is not automatically a risk; a generic enabled flag may need further investigation. An unknown topology is not proof of safety.

Follow paths transitively across connected systems. Cycles do not require a remediation topological sort: analyze reachability with a visited set, identify the relevant active process resources, and require their disabling or effective restore blocking. A benign path that only preserves permitted records is not a prohibited recreation path.

Output: policy assessments, established violations and risks, required final-state checks, and unresolved gaps. Stage 3 may calculate compliance predicates; it does not serialize or ask an LLM to select the final status.

## 9. Bounded investigation controller

The controller owns a case work queue. It chooses a concrete gap, permits the model to propose an allowlisted read, validates its arguments against eligible IDs and case scope, executes it, merges supported observations, and reruns affected identity/state calculations.

Allowlisted tools are:

- `search_identifiers`: exact aliases in eligible indexed content, with context.
- `find_resource_history`: scoped activity and observations for a resource.
- `read_evidence`: bounded eligible text/rows/JSON nodes.
- `inspect_media`: a specified page or image region plus enough surrounding context.
- `trace_process_path`: evidence-backed source/destination relationships.
- `compare_scope_states`: eligible observations across named replica/store scopes.

The tools accept typed parameters, not free-form code. They provide deterministic pagination and explicit truncation flags. The controller drains required pages or leaves a coverage gap. Tool results cannot change the request, policy, evidence registry, or case cutoff. The model can identify possible gaps, but code owns gap closure and budget accounting.

Proposed initial defaults, adjustable after sample evaluation:

| Limit | Default |
| --- | --- |
| Investigation rounds per case | 3 |
| Read tools per round | 4 |
| Investigation interpretation calls | At most 1 per round |
| Additional schema-repair calls for investigation | At most 1 per case |
| Intent interpretation calls | At most 2 including repair/review |
| Extraction attempts per shared model-assisted artifact task | At most 2 including repair |

Thus case-specific semantic calls have a default maximum of six, separate from shared extraction work. Provider transport retries are separately bounded and counted; a successful response followed by semantic repair is a new model call. Shared extraction tasks also have configurable input/output and global spend limits. Each prompt has a size ceiling; application pagination must not silently truncate evidence needed to close a gap.

Stop when supported facts reach a fixed point and all material gaps are closed, or when an explicit budget, quota, error, or repeated-no-progress condition is reached. Deterministic indexing and required scans are not skipped because the agent loop has run out of calls. Exhaustion checkpoints an unresolved case. It does not create a fourth CSV status, an empty COMPLETE verification set, or invented INCOMPLETE findings.

An unresolved case is an engineering failure to finish that case. The run can resume with corrected adapters, more quota, or configured fallback. There is no truthful universally valid forced-label fallback. A final full-dataset run succeeds only when all 518 cases are resolvable and valid. Partial diagnostics must not be presented as the completed submission.

## 10. Stage 4: deterministic decisions and output compilation

### Decision rules

Let A mean affirmative deletion authorization; V the established policy violations or prohibited recreation risks; G material unresolved issues; and C the evidence coverage needed for all discovered obligations.

| Condition | Result |
| --- | --- |
| Clearly non-deletion intent | NOT_APPLICABLE and `[]` |
| Uncertain intent | Unresolved internally; no fabricated final row |
| A, no material G, complete C, at least one V | INCOMPLETE |
| A, no material G, complete C, no V, every required treatment and retained record positively supported | COMPLETE |
| Any other combination | Unresolved internally; investigate or resume |

A single proven violation can establish that deletion is incomplete even before the investigation finishes. However, finalizing its row still requires the full findings, remedies, and verification coverage. A model self-assessment of completeness never satisfies C.

Coverage means all eligible artifacts have usable extraction or a resolved reason they cannot affect this case, accepted aliases and grounded resource histories have been searched, relevant scopes/processes are accounted for, and no candidate link or contradiction capable of changing the output remains. This is a corpus-bounded proof obligation, not a numerical confidence threshold or a claim that unknown real-world stores were searched.

### Step generation

| Assessed issue | Finding | Remediation | Verification |
| --- | --- | --- | --- |
| DELETE-required record present | REPORT_REMAINING_RECORD / PRESENT | DELETE_RECORD / ABSENT | VERIFY_RECORD_ABSENT / ABSENT |
| REDACT-required identifiers present | REPORT_EXPOSED_PII / PRESENT | REDACT_RECORD / REDACTED | VERIFY_RECORD_REDACTED / REDACTED |
| ANONYMIZE-required attribution present | REPORT_EXPOSED_PII / PRESENT | ANONYMIZE_RECORD / ANONYMIZED | VERIFY_RECORD_ANONYMIZED / ANONYMIZED |
| Prohibited active copy process | REPORT_ACTIVE_DATA_FLOW / ACTIVE | DISABLE_DATA_FLOW / DISABLED | VERIFY_DATA_FLOW_DISABLED / DISABLED |
| Prohibited restore path | REPORT_RESTORE_RISK / ACTIVE | BLOCK_RESTORE / BLOCKED | VERIFY_RESTORE_BLOCKED / BLOCKED |

Also generate required verification for compliant records/processes in the established case scope: absent records, retained records, redacted/anonymized records, disabled flows, and blocked restores. Public samples demonstrate that verification can extend beyond the resources being remediated.

Project obligations onto the most specific required terminal check. Ordinary retained security/legal records use VERIFY_RECORD_PRESENT; tombstones use VERIFY_RECORD_REDACTED; backup archives use VERIFY_RESTORE_BLOCKED. Preservation of the archive or stable tombstone reference is still checked internally and is part of the specialized check's meaning. Do not mechanically add a duplicate VERIFY_RECORD_PRESENT for every resource with a preservation obligation. For a backup, evidence of blocking must concern the existing affected archive or its effective subject suppression, not an unrelated deny rule.

For COMPLETE, output only the evidence-backed verification set. For INCOMPLETE, output findings for every established issue, all required remediation, and the entire required future verification set. All remediation and all verification in an INCOMPLETE case use `evidence_id=""`, including checks concerning already-compliant retained records. Findings and COMPLETE checks cite eligible participant evidence proving the stated fact.

Deduplicate by phase, operation, system, resource, and target state. Multiple observations of one logical violation do not create duplicate remedies. Preserve scope-specific proof internally; do not invent replica resource IDs absent from the sources.

### Canonical order is authoritative

Sort first by phase rank, then the operation rank below, then `system_id` and `resource_id` ascending as literal strings. Assign consecutive step numbers only after sorting. Sort case IDs as literal strings; do not extract their numeric suffixes to redefine the specified ordering.

| Phase | Operation sequence |
| --- | --- |
| FINDING | REPORT_REMAINING_RECORD, REPORT_EXPOSED_PII, REPORT_ACTIVE_DATA_FLOW, REPORT_RESTORE_RISK |
| REMEDIATION | DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE_RECORD, REDACT_RECORD, ANONYMIZE_RECORD |
| VERIFICATION | VERIFY_RECORD_ABSENT, VERIFY_RECORD_PRESENT, VERIFY_RECORD_REDACTED, VERIFY_RECORD_ANONYMIZED, VERIFY_DATA_FLOW_DISABLED, VERIFY_RESTORE_BLOCKED |

Do not run a topological sort, add intermediate verification steps out of phase, or apply downstream-first tie breakers to the submitted array. The prescribed order already puts disabling and blocking before record changes. Keep grounded dependency concerns in the internal explanation and diagnostics. If a demonstrated execution dependency conflicts with canonical serialization, report that limitation in diagnostics while retaining the user's chosen canonical output order. This audit system does not execute the plan or claim the array alone guarantees safe execution under contradictory constraints.

### Evidence selection

Select an eligible direct observation that proves the output assertion in its relevant scope. Use the latest applicable proving observation when it supersedes older ones; for equivalent proofs prefer an explicit resource observation with precise locator, then a deterministic evidence-ID/locator tie break. Recency does not make a claim stronger than a state observation. A replica-present finding cites the replica evidence rather than a primary-absence result. Do not choose citations to imitate sample labels.

The internal derivation can include multiple evidence references even though a public step has one evidence ID. The selected citation must actually establish the asserted state; other links establish attribution and context. If no single permitted citation can substantiate the output assertion, retain a representability/evidence gap rather than invent a combined ID.

## 11. Final validation and artifact writing

Validate schema and semantics before any result is accepted:

- Exact CSV columns, allowed status, unique expected case IDs, sorted order, and 518 rows in final evaluation mode.
- JSON array only; exactly the seven allowed step fields; correct types, consecutive numbering, canonical order, and operation/state/phase compatibility.
- NOT_APPLICABLE has no steps; COMPLETE contains verification only; INCOMPLETE contains supported findings and complete remedies/checks.
- Every nonempty evidence ID exists in the participant registry, is eligible at the cutoff, and supports the stated assertion and attribution chain.
- Every remedy has a policy-supported issue; every required treatment and process has verification; retention and tombstone constraints are preserved.
- No unresolved identity, temporal, extraction, policy, representation, or coverage issue is hidden by finalization.

Write a temporary CSV in the destination directory and replace root `output.csv` atomically only after every row validates. On failure, leave an earlier valid output untouched, return a failing exit status, and identify the current run as failed so an old output cannot be mistaken for a new result. Sample runs and diagnostic partial files use separate explicit paths. Never modify `dataset/output.csv` or any participant input.

## 12. Provider access, fallback, quotas, and cost

The user has a Gemini Pro subscription. This is a preference and possible development benefit, not verified API entitlement. Google's current documentation distinguishes AI Studio subscription benefits from direct Gemini API billing and quotas. Some eligible subscribers may receive Cloud credits with additional requirements. We have not inspected this user's account, billing, model availability, or limits. [Google AI plans](https://ai.google.dev/gemini-api/docs/google-ai-plans)

Implementation starts with a small API preflight using credentials supplied through environment variables: confirm authentication, one text schema task, one image task if needed, response usage metadata, and the project's available model limits. Do not enable paid billing or assume unlimited/free API usage. The exact model must be configured from actually available IDs and recorded for every response. Text and vision may use different model IDs where appropriate.

Use a provider interface with structured interpretation/extraction, optional image inputs, capability inspection, response normalization, and usage accounting. Gemini is the first implementation target. Groq and local backends use the same internal schemas when configured; their exact models and capabilities remain to be tested. A text-only fallback cannot silently stand in for visual extraction. Unsupported tasks stay unresolved or use a separately validated extraction path.

Google documents request-per-minute, input-token-per-minute, and request-per-day limits at project level, with active limits visible in AI Studio. Configure a conservative single-worker start, a project/model-aware limiter, bounded exponential backoff with jitter for transient errors, and resumable checkpoints for daily exhaustion. Do not create extra API keys to bypass project quotas. [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)

The initial cost policy is free-tier-first when the account and selected model support it; no numeric paid budget has been supplied. A nonzero paid-spend ceiling must be explicitly configured before a paid full run. Fallback uses only configured endpoints/credentials and never signs up for services or changes billing. Provider changes are recorded, not hidden. Re-evaluate interpretation quality when a fallback model is introduced.

Cache accepted extraction and interpretation responses by content hash, schema/prompt/parser versions, exact model ID, task, and all relevant cutoff/scope inputs. Failures and truncated results are not reusable successes. Reuse shared media extraction across cases; keep case eligibility filtering separate. Warm caches improve reproducibility but do not guarantee fresh model calls are deterministic.

Structured outputs improve format consistency; local validation still checks meaning, provenance, enums, and evidence eligibility. [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)

Usage reporting separates actual final-run calls/tokens/cost from reused-cache construction costs. Count successful, retried, repaired, and failed calls where usage is reported. Include provider-reported billed categories, actual versus estimated token counts, exact model names, and cached token pricing where relevant. Shared extraction cost is reported once overall and allocated across cases for averages without double counting. A free-tier call may have zero monetary cost while still consuming tokens and quota. Local compute is described separately from API charges. Missing usage is explicitly estimated or marked unavailable rather than recorded as zero.

## 13. Proposed source boundaries

This is an intended module map, not files to scaffold before the design is accepted.

| Module | Responsibility |
| --- | --- |
| `code/main.py` | CLI, path resolution, run lifecycle, progress, exit status |
| `code/audit/contracts.py` | Typed records, enums, output schema |
| `code/audit/config.py` | Provider roles, limits, non-secret settings, environment access |
| `code/audit/inputs.py` | Allowlisted CSV and manifest loading |
| `code/audit/identity.py` | Intent gate mapping and guarded identity graph |
| `code/audit/evidence/` | Format adapters, provenance, extraction coverage, exact/full-text indexes |
| `code/audit/state.py` | Eligibility, scoped timelines, contradictions, effective state |
| `code/audit/policy.py` | Supplied rule loading and reviewed predicates |
| `code/audit/flows.py` | Relevant sync/restore reachability and risk assessments |
| `code/audit/investigation.py` | Gap queue, allowlisted tools, bounded loop, stopping criteria |
| `code/audit/decision.py` | Deterministic case decision, supported step generation, canonical sorting |
| `code/audit/validation.py` | Independent structural and semantic checks |
| `code/audit/providers/` | Gemini adapter and configured fallback implementations |
| `code/audit/prompts/` | Versioned intent, observation, visual extraction, and investigation instructions |
| `code/audit/run_store.py` | Checkpoints, caches, hashes, run manifests, usage ledger |
| `code/evaluation/main.py` | Label-isolated sample evaluator and participant-created fixtures |

Run caches and diagnostics live in an ignored root runtime directory outside `code/`; they are excluded from packaging. Prompts, setup instructions, tests, and required Markdown reports are included in the runnable archive. No framework orchestration state is required outside the project.

Proposed CLI responsibilities are preflight, prepare/index, audit samples, audit evaluation, resume a run, validate output, evaluate samples/custom fixtures, and produce usage reports. Exact command syntax is left to the implementer and documented in README. Production mode is unable to load sample labels. Strict reproduction mode uses only compatible cached accepted model responses and fails on missing cache entries; live mode records any newly generated interpretations.

## 14. Evaluation and acceptance

Use all 32 labeled samples as the public regression suite while recognizing that they contain no NOT_APPLICABLE examples. Hidden evaluation labels are unavailable; do not claim measured 518-case accuracy.

Report these clearly defined local metrics:

- Case status accuracy: correct status / labeled cases.
- Exact row accuracy: status and complete parsed step array both match.
- Step precision/recall/F1: exact step-content matches after excluding step number for this diagnostic; retain all other fields including evidence ID. Report numerator/denominator and treatment of empty arrays.
- Field accuracy: match the seven fields at aligned step positions; missing or extra positions count as mismatches. Provide per-field values so sequence and content mistakes can be distinguished.
- Sequence accuracy: exact equality of the complete ordered parsed step array, including step numbers and citations.
- Diagnostic semantic content comparison ignoring citation choice or order, explicitly secondary to exact metrics, to explain equivalent-proof and serialization errors rather than replace them.

Create independent fictional fixtures, with expected answers directly visible in source/Markdown, covering at least:

1. Multilingual deletion authorization, a negated deletion request, and a marketing-only opt-out.
2. A profile absent from primary but present in an eligible replica; successful delete claims do not override it.
3. A tombstone that must retain `user_id` but still exposes an email hash and must be redacted.
4. An active connector or backup able to recreate prohibited data, including canonical disabling/blocking order.
5. A compliant retained security record and legal-hold record with valid retention evidence.
6. Evidence captured after the cutoff that would reverse the answer if incorrectly admitted.
7. Shared/reassigned identifiers and an anonymized resource attributable only through eligible history.
8. Contradictory same-scope observations, parser failure, exhausted quota, and unreadable media; each must remain unresolved rather than fabricate a submission row.

Check invariants: CSV row shuffling does not change results; JSON object-key order is irrelevant; adding unrelated records does not change a case; adding after-cutoff evidence does not change a case or its model context; cold and resumed runs agree given the same accepted interpretations; duplicate observations do not duplicate steps; grounded aliases can expand discovery without merging subjects.

Use evaluation findings to change general parser, policy, state, or interpretation behavior. Do not introduce sample-case or evaluation-family branches. Record failures and improvements directly in `code/evaluation/evaluation_report.md`; usage and cost go directly in `code/evaluation/usage_report.md`. Maintain the root conversation log separately. Packaging follows README: include runnable code, prompts, setup, and both reports; exclude the dataset, caches, environments, credentials, and nested archives.

Acceptance requires a clean end-to-end run producing all 518 valid rows with no unresolved material gaps, a successful independent output validator, reproducible checkpoint/resume behavior, completed reports, and an inspected archive. Passing format checks is not a substitute for semantic evaluation.

## 15. Remaining choices and known limits

The selected architecture and canonical ordering are settled. Python, SQLite, explicit orchestration, initial loop limits, and the proposed module boundaries are recommendations in this document. Provider/model IDs, actual quota, numeric paid budget, local hardware, and fallback vision capability are not yet verified. The implementer may choose extraction libraries, test tooling, and small module organization details without changing the architecture.

The design cannot guarantee perfect language/visual interpretation, prove stores absent from the supplied corpus, invent remediation operations missing from the allowed vocabulary, or force a truthful complete submission out of irreducibly ambiguous evidence. These limits are made explicit so that implementation cannot disguise them as confident statuses.

The next deliverable after design acceptance is an implementation plan with milestones, tests, provider preflight, and measurable exit criteria. No solution code or dependency installation is authorized by this design document alone.

## 16. Design review record

An independent builder review checked whether the document could support an implementation plan. It identified one consequential ambiguity: whether a direct observation can persist to the audit cutoff when no superseding evidence exists. Section 8 now explicitly defines corpus-bounded persistence after complete eligible history inspection, together with mutation-claim and scope guards. This is the author's proposed resolution and should be reviewed alongside the implementation defaults. No other consequential unanswered planning questions were identified by that review. This is a design review, not a claim that the unimplemented system passes tests or achieves a measured accuracy.
