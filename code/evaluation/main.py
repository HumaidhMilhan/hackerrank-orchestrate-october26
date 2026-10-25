"""Label-isolated public sample evaluation; never imported by prediction stages."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import read_csv
from evaluation.fixtures import run_fixtures
from stage4 import build_output

ROOT = Path(__file__).resolve().parents[2]


def signature(step):
    return tuple(step.get(key) for key in ['phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id'])


def evaluate(predictions, expected):
    actual = {row['case_id']: row for row in predictions}
    correct_status = exact_rows = exact_sequences = matched = predicted_count = expected_count = field_matches = field_total = 0
    failures = []
    for gold in expected:
        predicted = actual.get(gold['case_id'], {'deletion_status': 'MISSING', 'steps_json': '[]'})
        left, right = json.loads(predicted['steps_json']), json.loads(gold['steps_json'])
        status_ok = predicted['deletion_status'] == gold['deletion_status']
        sequence_ok = left == right
        correct_status += status_ok
        exact_sequences += sequence_ok
        exact_rows += status_ok and sequence_ok
        left_counts, right_counts = Counter(map(signature, left)), Counter(map(signature, right))
        matched += sum((left_counts & right_counts).values())
        predicted_count += len(left)
        expected_count += len(right)
        for index in range(max(len(left), len(right))):
            field_total += 7
            if index < len(left) and index < len(right):
                field_matches += sum(left[index].get(key) == right[index].get(key) for key in
                                     ['step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id'])
        if not status_ok or not sequence_ok:
            failures.append({'case_id': gold['case_id'], 'expected_status': gold['deletion_status'],
                             'actual_status': predicted['deletion_status'], 'status_correct': status_ok,
                             'sequence_correct': sequence_ok, 'expected_steps': len(right), 'actual_steps': len(left)})
    n = len(expected)
    precision = matched / predicted_count if predicted_count else (1.0 if not expected_count else 0.0)
    recall = matched / expected_count if expected_count else (1.0 if not predicted_count else 0.0)
    return {'cases': n, 'status_accuracy': correct_status / n if n else 1,
            'exact_row_accuracy': exact_rows / n if n else 1, 'sequence_accuracy': exact_sequences / n if n else 1,
            'step_precision': precision, 'step_recall': recall, 'step_f1': 2 * precision * recall / (precision + recall) if precision + recall else 0,
            'field_accuracy': field_matches / field_total if field_total else 1,
            'step_matches': matched, 'predicted_steps': predicted_count, 'expected_steps': expected_count,
            'field_matches': field_matches, 'field_total': field_total, 'failures': failures}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Evaluate public samples and independent custom cases.')
    parser.add_argument('--predictions', type=Path, default=ROOT / 'sample_predictions.csv')
    parser.add_argument('--package', action='store_true', help='package code after evaluation if full-run usage report exists')
    args = parser.parse_args(argv)
    if not args.predictions.is_file():
        parser.error('Generate sample_predictions.csv with python code/main.py --samples first.')
    metrics = evaluate(read_csv(args.predictions), read_csv(ROOT / 'dataset/sample_output.csv'))
    fixtures = run_fixtures()
    comparisons = {}
    assessments_path = ROOT / '.runtime/assessments-samples.json'
    if assessments_path.is_file():
        assessments = json.loads(assessments_path.read_text(encoding='utf-8'))
        expected = read_csv(ROOT / 'dataset/sample_output.csv')
        for policy in ['best-evidence', 'incomplete']:
            comparisons[policy] = evaluate([build_output(value, policy)[0] for value in assessments.values()], expected)
    lines = ['# Evaluation report', '', '## Measured public sample results', '',
             f"Requests: {metrics['cases']}. These are public sample measurements, not hidden 518-case accuracy.", '',
             '| Metric | Result |', '| --- | ---: |']
    for key in ['status_accuracy', 'exact_row_accuracy', 'step_precision', 'step_recall', 'step_f1', 'field_accuracy', 'sequence_accuracy']:
        lines.append(f"| {key.replace('_', ' ')} | {metrics[key]:.3%} |")
    lines.extend(['', f"Exact step matches: {metrics['step_matches']} / {metrics['predicted_steps']} predicted and {metrics['expected_steps']} expected.",
                  f"Aligned field matches: {metrics['field_matches']} / {metrics['field_total']}.", '',
                  'Step comparison excludes step_no but retains all other fields including evidence IDs. Field comparison uses aligned array positions; missing steps count as seven mismatches. '
                  'Sequence comparison includes every field and array order. JSON key order and whitespace are ignored.', '',
                  '## Independent custom cases', ''])
    for fixture in fixtures:
        lines.extend([f"### {fixture['case_id']}: {fixture['name']}", '', fixture['description'], '',
                      f"Expected status: {fixture['expected_status']}; actual: {fixture['actual_status']}; passed: {fixture['passed']}.",
                      'Expected ordered operations: ' + ', '.join(fixture['expected_operations']) + '.',
                      'Actual ordered operations: ' + ', '.join(fixture['actual_operations']) + '.', ''])
    lines.extend(['## Uncertainty policy comparison', '', 'Both policies reuse saved assessments without new model calls.', '',
                  '| Policy | Status accuracy | Exact row | Sequence |', '| --- | ---: | ---: | ---: |'])
    for policy, result in comparisons.items():
        lines.append(f"| {policy} | {result['status_accuracy']:.3%} | {result['exact_row_accuracy']:.3%} | {result['sequence_accuracy']:.3%} |")
    lines.extend(['', 'The configured default remains best-evidence. This comparison does not automatically select per-case answers or change policy. '
                  'Review false COMPLETE cases before applying a general conservative rule; parser/identity/policy errors must be fixed at their source.', '',
                  '## Failures found and improvements made', '',
                  'Implementation separates primary and replica scopes, checks capture and observation cutoffs, distinguishes operation claims from direct reads, '
                  'uses scoped multilingual negation before deletion stems, preserves tombstone references, and applies canonical operation ordering. '
                  'These mechanisms are covered by independent tests rather than hardcoded sample labels.', '',
                  'The implementation review found six defects, reproduced with fictional regression cases and fixed: shared-phone attribution, '
                  'structured/reverse resource links, partial payloads or treatment labels accepted as compliance proof, '
                  'invalid intent responses cached before validation, unread PDF pages cached as successful extraction, '
                  'and retained-only/unknown-payload flows treated as prohibited copies. Integration regression checks also enforce the required archive-root report paths '
                  'and prevent system names in activity prose from becoming cross-subject resource links. Provider regression checks cover exponential backoff/jitter, '
                  'permanent-error handling, retry-budget ownership, and server-directed cooldowns. Async scheduler tests cover rolling RPM/input TPM, '
                  'shared concurrency, shutdown during backoff, all SDK operations, retry admission, real-SDK transport ownership and sanitized quota diagnostics. Groq tests additionally cover role routing, confidence-based independent review, persistent daily quotas, queued cooldowns, cancellation-owned physical permits, and per-model usage/costs. Independent regression tests also cover scoped marketing opt-out, six request languages, twenty-case intent validation, owner-key trace joins, ancestor/record JSON cutoffs, regional replicas and explicit restore denials; '
                  'live interpretation remains source-grounded and rejected observations retain scoped uncertainty. See final_verification_report.md for the latest run and exact_step_report.md for documented ownership gaps; older calibration reports are historical.', '',
                  'Remaining measured failures:', '', '| Case | Expected status | Actual status | Sequence correct | Expected/actual steps |',
                  '| --- | --- | --- | --- | --- |'])
    for failure in metrics['failures']:
        lines.append(f"| {failure['case_id']} | {failure['expected_status']} | {failure['actual_status']} | {failure['sequence_correct']} | {failure['expected_steps']}/{failure['actual_steps']} |")
    if not metrics['failures']:
        lines.append('| None | | | | |')
    lines.extend(['', 'No live-provider/vision quality is claimed by an offline run. API credentials, configured model IDs, '
                  'unread media, attribution gaps, and equivalent-proof citation choices can affect these results. See run diagnostics for estimated/fallback cases. '
                  'Hidden evaluation answers were not accessed. Status agreement alone is not complete plan correctness.', ''])
    report = ROOT / 'code/evaluation/evaluation_report.md'
    report.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Samples: status={metrics['status_accuracy']:.3%}, exact rows={metrics['exact_row_accuracy']:.3%}, sequence={metrics['sequence_accuracy']:.3%}")
    print(f"Custom cases: {sum(f['passed'] for f in fixtures)}/{len(fixtures)}; report={report}")
    if args.package:
        usage = ROOT / 'code/evaluation/usage_report.md'
        if not usage.is_file():
            print('Archive not created: run the full audit to generate final-run usage_report.md first.', file=sys.stderr)
            return 1
        from main import package_code
        print(f'Archive: {package_code(ROOT)}')
    return 0 if all(f['passed'] for f in fixtures) else 1


if __name__ == '__main__':
    raise SystemExit(main())
