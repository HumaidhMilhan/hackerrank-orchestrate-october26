"""Terminal entry point for the four-stage deletion audit."""
import argparse
import csv
import json
import logging
import math
import sys
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from common import VERSION, atomic_json, digest, read_csv
from llm import ModelClient, load_env
from stage1 import IdentityIndex, interpret_requests
from stage2 import EvidenceStore
from stage3 import assess_case, load_rules, process_paths
from stage4 import build_output, validate_row

ROOT = Path(__file__).resolve().parents[1]


class Console:
    def __init__(self, quiet=False, verbose=False):
        self.quiet = quiet
        self.logger = logging.getLogger('audit')
        self.logger.handlers.clear()
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        self.logger.propagate = False
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        self.logger.addHandler(handler)
        self.warning_count = 0
        self.error_count = 0
        class Counts(logging.Handler):
            def emit(inner, record):
                if record.levelno >= logging.ERROR:
                    self.error_count += 1
                elif record.levelno >= logging.WARNING:
                    self.warning_count += 1
        self.logger.addHandler(Counts())

    def progress(self, phase, completed, total, message):
        if not self.quiet:
            self.logger.info('%s %d/%d | %s', phase, completed, total, message)


def write_output(path, rows, requests, registry):
    expected = {r['case_id']: r for r in requests}
    if len(rows) != len(expected) or {r['case_id'] for r in rows} != set(expected):
        raise ValueError('output case coverage mismatch')
    for row in rows:
        validate_row(row, registry, expected[row['case_id']]['audit_at'])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['case_id', 'deletion_status', 'steps_json'], lineterminator='\n')
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r['case_id']))
    temp.replace(path)


def input_signature(dataset, requests_file, client):
    names = ['user_identities.csv', 'user_audit_log.csv', 'system_activity.csv', 'deletion_rules.csv', 'evidence_files.csv', requests_file]
    manifest = read_csv(dataset / 'evidence_files.csv')
    files = {name: digest((dataset / name).read_bytes()) for name in names}
    evidence_root = (dataset / 'evidence').resolve()
    for row in manifest:
        path = (dataset / row['file_path']).resolve()
        if not path.is_relative_to(evidence_root):
            raise ValueError('invalid evidence path')
        files[row['file_path']] = digest(path.read_bytes()) if path.is_file() else 'missing'
    source = {p.name: digest(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')}
    return digest({'files': files, 'source': source, 'model': client.configuration(), 'version': VERSION})


def usage_summary(calls, cache_hits, count, mode, run_id):
    import os
    per_model = {}
    for call in calls:
        key = call['provider'] + '/' + call['model']
        item = per_model.setdefault(key, {'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cached_tokens': 0,
                                         'thinking_tokens': 0, 'unknown_usage_calls': 0})
        item['calls'] += 1
        for field in ['input_tokens', 'output_tokens', 'cached_tokens', 'thinking_tokens']:
            item[field] += call.get(field) or 0
        if call.get('input_tokens') is None or call.get('output_tokens') is None:
            item['unknown_usage_calls'] += 1
    def rates_for(key):
        provider, model = key.split('/', 1)
        prefixes = ['AUDIT']
        if provider == 'groq':
            defaults = {'INTENT':'openai/gpt-oss-20b', 'REVIEW':'openai/gpt-oss-120b', 'EVIDENCE':'qwen/qwen3.8-27b'}
            prefixes = ['GROQ_'+role for role, default in defaults.items()
                        if (os.getenv('GROQ_'+role+'_MODEL') or default) == model]
        candidates = []
        try:
            for prefix in prefixes:
                input_rate = float(os.environ[prefix+'_INPUT_USD_PER_MILLION'])
                output_rate = float(os.environ[prefix+'_OUTPUT_USD_PER_MILLION'])
                cached_rate = float(os.getenv(prefix+'_CACHED_USD_PER_MILLION') or input_rate)
                rates = (input_rate, output_rate, cached_rate)
                if not all(math.isfinite(rate) and rate >= 0 for rate in rates): return None
                candidates.append(rates)
        except (KeyError, ValueError, TypeError): return None
        # Shared model IDs cannot honestly use two conflicting price schedules.
        return candidates[0] if candidates and all(r == candidates[0] for r in candidates) else None
    total_cost = 0.0
    for key, item in per_model.items():
        rates = rates_for(key)
        if rates is not None and not item['unknown_usage_calls']:
            input_rate, output_rate, cached_rate = rates
            item['estimated_usd'] = ((max(0, item['input_tokens'] - item['cached_tokens']) * input_rate +
                                      item['cached_tokens'] * cached_rate +
                                      (item['output_tokens'] + item['thinking_tokens']) * output_rate) / 1_000_000)
            total_cost += item['estimated_usd']
        else:
            item['estimated_usd'] = None
    overall = {key: sum(item[key] for item in per_model.values()) for key in
               ['calls', 'input_tokens', 'output_tokens', 'cached_tokens', 'thinking_tokens', 'unknown_usage_calls']}
    overall['total_tokens'] = overall['input_tokens'] + overall['output_tokens'] + overall['thinking_tokens']
    overall['average_tokens_per_request'] = overall['total_tokens'] / count if count else 0
    overall['estimated_usd'] = total_cost if all(i['estimated_usd'] is not None for i in per_model.values()) else None
    overall['estimated_usd_per_request'] = overall['estimated_usd'] / count if count and overall['estimated_usd'] is not None else None
    return {'run_id': run_id, 'mode': mode, 'requests': count, 'models': per_model, 'overall': overall,
            'operation_counts': dict(Counter(call.get('operation', 'generate_content') for call in calls)),
            'task_counts': dict(Counter(call.get('task', 'unknown') for call in calls)),
            'response_cache_hits': cache_hits, 'notes': 'Actual calls attributable to this logical run; resumed checkpoints retain prior calls. Reused extraction from earlier runs is not billed again. Missing provider usage is not zero.'}


def write_usage_report(summary, root):
    overall = summary['overall']
    lines = ['# Final full-dataset run: model usage', '', f"Run: {summary['run_id']}", '',
             f"Requests: {summary['requests']}. Mode: {summary['mode']}.", '',
             '| Provider/model | Calls | Input | Output | Thinking | Cached input | Unknown usage calls | Estimated USD |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for model, item in summary['models'].items():
        cost = f"{item['estimated_usd']:.6f}" if item['estimated_usd'] is not None else 'unavailable'
        lines.append(f"| {model} | {item['calls']} | {item['input_tokens']} | {item['output_tokens']} | {item['thinking_tokens']} | {item['cached_tokens']} | {item['unknown_usage_calls']} | {cost} |")
    if not summary['models']:
        lines.append('| No model invoked (offline/rule fallback) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |')
    lines.extend(['', f"Overall calls: {overall['calls']}; input tokens: {overall['input_tokens']}; output tokens: {overall['output_tokens']}; thinking tokens: {overall['thinking_tokens']}.",
                  f"Total reported tokens: {overall['total_tokens']}; average per request: {overall['average_tokens_per_request']:.3f}.",
                  f"Estimated total USD: {overall['estimated_usd']}; per request: {overall['estimated_usd_per_request']}.", '',
                  f"Accepted response-cache hits: {summary['response_cache_hits']}; evidence extraction cache hits: {summary.get('evidence_cache_hits', 0)}.", '', summary['notes'], '',
                  'SDK operation counts: ' + json.dumps(summary.get('operation_counts', {}), sort_keys=True) + '. '
                  'Gemini token-count requests count toward local RPM/concurrency and reserve generation input TPM. '
                  'They do not contribute generated-model input/output totals. Groq reserves combined input/output TPM and daily budgets; '
                  'reasoning is already included in completion tokens. Failed requests retain conservative reservations.', '',
                  'Task counts (including secondary intent evaluation): ' + json.dumps(summary.get('task_counts', {}), sort_keys=True) + '.', '',
                  'Costs require explicitly configured verified per-million rates. A free tier may have zero money cost but nonzero quota/token usage. '
                  'Unknown token usage is excluded from numerical totals and disclosed above. Cached extraction construction cost from previous runs is not included in this run; '
                  'record those earlier runs separately when calculating total project expenditure. Offline runs do not verify live model/vision accuracy.', ''])
    path = root / 'code/evaluation/usage_report.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path


def package_code(root):
    path = root / 'code.zip'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        candidates = [root / 'README.md', root / 'requirements.txt', root / 'requirements.lock',root / '.env.example']
        candidates.extend(p for p in (root / 'code').rglob('*') if p.is_file() and p.suffix in {'.py', '.md', '.txt'})
        for source in sorted(set(candidates)):
            if source.is_file() and '__pycache__' not in source.parts:
                archive.write(source, source.relative_to(root).as_posix())
        # The competition names these paths relative to the archive root.
        for name in ['evaluation_report.md', 'usage_report.md']:
            report = root / 'code/evaluation' / name
            if report.is_file():
                archive.write(report, 'evaluation/' + name)
    return path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Audit deletion evidence and write deterministic CSV steps.')
    parser.add_argument('--samples', action='store_true', help='process the 32 public requests into sample_predictions.csv')
    parser.add_argument('--resume', action='store_true', help='resume a compatible checkpoint')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--quiet', action='store_true', help='hide routine progress; retain warnings and final summary')
    group.add_argument('--verbose', action='store_true', help='show additional sanitized diagnostics')
    parser.add_argument('--offline', action='store_true', help='disable all model API requests and exercise fallbacks')
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--output', type=Path, help='override the output CSV path')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--uncertainty', choices=['best-evidence', 'incomplete'], default='best-evidence')
    parser.add_argument('--package', action='store_true', help='package code after this run; requires both evaluation reports')
    return parser.parse_args(argv)


def run(args):
    start = time.monotonic()
    console = Console(args.quiet, args.verbose)
    logger = console.logger
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    load_env(args.env_file)
    client = ModelClient(runtime / 'model_cache', args.offline)
    if not client.enabled:
        logger.warning('Model API unavailable/unconfigured; using deterministic intent fallback and available local evidence. Configure key AND model IDs for live interpretation.')
    mode = 'samples' if args.samples else 'evaluation'
    request_name = 'sample_deletion_requests.csv' if args.samples else 'deletion_requests.csv'
    dataset = args.dataset.resolve()
    requests = read_csv(dataset / request_name)
    if len({r['case_id'] for r in requests}) != len(requests):
        raise ValueError('duplicate input case IDs')
    if dataset == (ROOT / 'dataset').resolve() and len(requests) != (32 if args.samples else 518):
        raise ValueError('unexpected input case count')
    output = args.output or ROOT / ('sample_predictions.csv' if args.samples else 'output.csv')
    if output.resolve().is_relative_to(dataset):
        raise ValueError('output must not overwrite participant input data')
    console.progress('START', 0, len(requests), f"mode={mode} | provider={client.configuration()['provider']} | model={client.text_model or 'none'}")
    if hasattr(client, 'role_config'):
        for role, config in client.role_config.items():
            console.progress('MODEL', 0, len(requests), f"{role}={config['model']} | RPM={config['rpm']} | combined TPM={config['tpm']} | RPD={config['rpd']} | TPD={config['tpd']} | output cap={config['max_output_tokens']} | reasoning={config['reasoning_effort']} | format={config['format']}")
        console.progress('QUOTA', 0, len(requests), f'provider concurrency={client.max_concurrency} | separate model queues | review threshold={client.intent_confidence_threshold} | transient retry budget={client.max_retries}')
    else:
        console.progress('QUOTA', 0, len(requests), f'RPM={client.rpm} | input TPM={client.tpm} | concurrency={client.max_concurrency} | shared async SDK queue')
    signature = digest({'inputs': input_signature(dataset, request_name, client), 'uncertainty': args.uncertainty})
    checkpoint_path = runtime / f'checkpoint-{mode}.json'
    checkpoint = {'signature': signature, 'run_id': datetime.now(timezone.utc).isoformat(), 'results': {}, 'calls': []}
    if args.resume and checkpoint_path.is_file():
        candidate = json.loads(checkpoint_path.read_text(encoding='utf-8'))
        if candidate.get('signature') == signature:
            checkpoint = candidate
            logger.info('RESUME: %d compatible cases restored', len(checkpoint['results']))
        else:
            logger.warning('Checkpoint does not match current inputs/configuration; starting a new run')
    identities = IdentityIndex(read_csv(dataset / 'user_identities.csv'), read_csv(dataset / 'user_audit_log.csv'))
    pending = [r for r in requests if r['case_id'] not in checkpoint['results']]
    intents = interpret_requests(pending, client, console.progress)
    store = EvidenceStore(dataset, client, runtime / 'evidence_cache', console.progress)
    store.prepare()
    rules = load_rules(dataset)
    registry = {r['file_id']: r['captured_at'] for r in read_csv(dataset / 'evidence_files.csv')}
    registry.update({r['activity_id']: r['event_time'] for r in read_csv(dataset / 'system_activity.csv')})
    registry.update({r['audit_id']: r['event_time'] for r in read_csv(dataset / 'user_audit_log.csv')})
    counts = Counter(value['row']['deletion_status'] for value in checkpoint['results'].values())
    prior_calls = list(checkpoint.get('calls', []))
    for index, case in enumerate(sorted(pending, key=lambda r: r['case_id']), 1):
        cid = case['case_id']
        context = None
        assessment = None
        try:
            intent = intents[cid]
            context = identities.resolve(case, intent['intent'])
            context['warnings'].extend(intent['warnings'])
            observations = []
            if context['intent'] == 'DELETION':
                console.progress('AUDIT', len(checkpoint['results']), len(requests), f'{cid} | Stage 2: evidence retrieval')
                observations = store.retrieve(context)
            assessment = assess_case(context, observations, rules, store.warnings_for(context) if context['intent'] == 'DELETION' else [])
            assessment['process_paths'] = process_paths(observations)
            if context['intent'] == 'DELETION' and any(r['assessment'] == 'UNCERTAIN' for r in assessment['resources']):
                console.progress('RECHECK', len(checkpoint['results']), len(requests), f'{cid} | Stage 3: one targeted recheck')
                observations = store.recheck(context, observations)
                assessment = assess_case(context, observations, rules, store.warnings_for(context))
                assessment['recheck_used'] = True
                assessment['process_paths'] = process_paths(observations)
            console.progress('AUDIT', len(checkpoint['results']), len(requests), f'{cid} | Stage 4: status and canonical steps')
            row, diagnostic = build_output(assessment, args.uncertainty)
            validate_row(row, registry, case['audit_at'])
        except Exception as exc:
            logger.error('%s: processing error (%s); writing a supported fallback and continuing', cid, type(exc).__name__)
            assessment = {'case_id': cid, 'audit_at': case['audit_at'], 'intent': context['intent'] if context else intents[cid]['intent'],
                          'resources': [], 'warnings': ['case processing exception: ' + type(exc).__name__], 'uncertain': True}
            row, diagnostic = build_output(assessment, args.uncertainty)
            diagnostic['exception_fallback'] = True
        counts[row['deletion_status']] += 1
        checkpoint['results'][cid] = {'row': row, 'assessment': assessment, 'diagnostic': diagnostic}
        checkpoint['calls'] = prior_calls + client.calls
        atomic_json(checkpoint_path, checkpoint)
        console.progress('CASE', len(checkpoint['results']), len(requests),
                         f"{cid} | {row['deletion_status']} | warnings={len(diagnostic['warnings'])} | COMPLETE={counts['COMPLETE']} INCOMPLETE={counts['INCOMPLETE']} NOT_APPLICABLE={counts['NOT_APPLICABLE']}")
        if diagnostic.get('estimated'):
            logger.warning('%s: estimated/fallback result; details in diagnostics', cid)
    results = checkpoint['results']
    rows = [results[r['case_id']]['row'] for r in requests]
    write_output(output, rows, requests, registry)
    atomic_json(runtime / f'assessments-{mode}.json', {cid: result['assessment'] for cid, result in results.items()})
    atomic_json(runtime / f'diagnostics-{mode}.json', {cid: result['diagnostic'] for cid, result in results.items()})
    usage = usage_summary(checkpoint.get('calls', []), client.cache_hits, len(requests), mode, checkpoint['run_id'])
    usage['evidence_cache_hits'] = store.cache_hits
    atomic_json(runtime / f'usage-{mode}.json', usage)
    if not args.samples:
        report = write_usage_report(usage, ROOT)
        logger.info('USAGE REPORT: %s', report)
    if args.package:
        required = [ROOT / 'code/evaluation/evaluation_report.md', ROOT / 'code/evaluation/usage_report.md']
        if all(p.is_file() for p in required):
            logger.info('ARCHIVE: %s', package_code(ROOT))
        else:
            logger.warning('Archive not created: run sample evaluation and a full audit to generate required reports first')
    estimated = sum(bool(result['diagnostic'].get('estimated')) for result in results.values())
    total_warnings = sum(len(result['diagnostic']['warnings']) for result in results.values())
    logger.info('DONE | %.1fs | rows=%d | %s | estimated=%d | case warnings=%d | logged errors=%d | model calls=%d tokens=%d | output=%s | diagnostics=%s',
                time.monotonic() - start, len(rows), dict(counts), estimated, total_warnings, console.error_count,
                usage['overall']['calls'], usage['overall']['total_tokens'], output, runtime / f'diagnostics-{mode}.json')
    client.close()
    return 0


def main(argv=None):
    args = parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        logging.getLogger('audit').error('Interrupted; finished cases are checkpointed. Use --resume to continue.')
        return 130
    except Exception as exc:
        logging.getLogger('audit').error('Cannot complete command (%s). Check input/output paths and configuration; no artifact success is claimed.', type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
