"""Final deterministic status, fixed step templates and canonical validation."""
import json

PHASES = ['FINDING', 'REMEDIATION', 'VERIFICATION']
OPERATIONS = {
    'FINDING': ['REPORT_REMAINING_RECORD', 'REPORT_EXPOSED_PII', 'REPORT_ACTIVE_DATA_FLOW', 'REPORT_RESTORE_RISK'],
    'REMEDIATION': ['DISABLE_DATA_FLOW', 'BLOCK_RESTORE', 'DELETE_RECORD', 'REDACT_RECORD', 'ANONYMIZE_RECORD'],
    'VERIFICATION': ['VERIFY_RECORD_ABSENT', 'VERIFY_RECORD_PRESENT', 'VERIFY_RECORD_REDACTED', 'VERIFY_RECORD_ANONYMIZED', 'VERIFY_DATA_FLOW_DISABLED', 'VERIFY_RESTORE_BLOCKED'],
}
STATES = dict(zip(OPERATIONS['FINDING'], ['PRESENT', 'PRESENT', 'ACTIVE', 'ACTIVE']))
STATES.update(zip(OPERATIONS['REMEDIATION'], ['DISABLED', 'BLOCKED', 'ABSENT', 'REDACTED', 'ANONYMIZED']))
STATES.update(zip(OPERATIONS['VERIFICATION'], ['ABSENT', 'PRESENT', 'REDACTED', 'ANONYMIZED', 'DISABLED', 'BLOCKED']))
TEMPLATES = {
    'DELETE': ('REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT'),
    'REDACT': ('REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED'),
    'ANONYMIZE': ('REPORT_EXPOSED_PII', 'ANONYMIZE_RECORD', 'VERIFY_RECORD_ANONYMIZED'),
    'DISABLE': ('REPORT_ACTIVE_DATA_FLOW', 'DISABLE_DATA_FLOW', 'VERIFY_DATA_FLOW_DISABLED'),
    'BLOCK_RESTORE': ('REPORT_RESTORE_RISK', 'BLOCK_RESTORE', 'VERIFY_RESTORE_BLOCKED'),
    'RETAIN': (None, None, 'VERIFY_RECORD_PRESENT'),
}
STEP_FIELDS = {'step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id'}


def sort_key(step):
    return (PHASES.index(step['phase']), OPERATIONS[step['phase']].index(step['operation']), step['system_id'], step['resource_id'])


def build_output(assessment, uncertainty='best-evidence'):
    resources = assessment.get('resources', [])
    warnings = list(assessment.get('warnings', []))
    if assessment['intent'] != 'DELETION':
        return {'case_id': assessment['case_id'], 'deletion_status': 'NOT_APPLICABLE', 'steps_json': '[]'}, {'estimated': False, 'warnings': warnings}
    violations = [r for r in resources if r['assessment'] == 'VIOLATION']
    compliant = [r for r in resources if r['assessment'] == 'COMPLIANT' and r.get('evidence_id')]
    uncertain = assessment.get('uncertain', False) or any(r['assessment'] == 'UNCERTAIN' for r in resources)
    estimated = bool(uncertain and not violations)
    status = 'INCOMPLETE' if violations else ('COMPLETE' if compliant else 'INCOMPLETE')
    if uncertainty == 'incomplete' and uncertain:
        status = 'INCOMPLETE'
    if not resources or not compliant and not violations:
        estimated = True
        warnings.append('no usable state evidence; last-resort INCOMPLETE')
    if estimated:
        warnings.append('best-evidence status estimate; not fully verified')
    steps = []

    def add(resource, phase, operation, evidence=''):
        if not operation:
            return
        steps.append({'step_no': 0, 'phase': phase, 'system_id': resource['system_id'],
                      'resource_id': resource['resource_id'], 'operation': operation,
                      'state': STATES[operation], 'evidence_id': evidence})

    for resource in resources:
        template = TEMPLATES.get(resource.get('action'))
        if not template or not resource.get('system_id') or not resource.get('resource_id'):
            continue
        finding, remedy, verification = template
        if status == 'COMPLETE':
            if resource['assessment'] == 'COMPLIANT' and resource.get('evidence_id'):
                add(resource, 'VERIFICATION', verification, resource['evidence_id'])
        else:
            if resource['assessment'] == 'VIOLATION' and resource.get('evidence_id'):
                if finding:
                    add(resource, 'FINDING', finding, resource['evidence_id'])
                    add(resource, 'REMEDIATION', remedy)
                else:
                    warnings.append(resource['resource_id'] + ': retention violation has no allowed remediation operation')
            # Future checks can describe a known resource's required policy state.
            add(resource, 'VERIFICATION', verification)
    unique = {tuple(step[k] for k in ['phase', 'system_id', 'resource_id', 'operation', 'state']): step for step in steps}
    steps = sorted(unique.values(), key=sort_key)
    for number, step in enumerate(steps, 1):
        step['step_no'] = number
    row = {'case_id': assessment['case_id'], 'deletion_status': status,
           'steps_json': json.dumps(steps, ensure_ascii=False, separators=(',', ':'))}
    validate_row(row)
    return row, {'estimated': estimated, 'warnings': sorted(set(warnings)), 'uncertainty_policy': uncertainty}


def validate_row(row, evidence_registry=None, cutoff=None):
    from common import timestamp
    if set(row) != {'case_id', 'deletion_status', 'steps_json'} or row['deletion_status'] not in {'COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'}:
        raise ValueError('invalid output row')
    steps = json.loads(row['steps_json'])
    if not isinstance(steps, list):
        raise ValueError('steps must be an array')
    if row['deletion_status'] == 'NOT_APPLICABLE' and steps:
        raise ValueError('non-deletion case has steps')
    for number, step in enumerate(steps, 1):
        if set(step) != STEP_FIELDS or type(step['step_no']) is not int or step['step_no'] != number:
            raise ValueError('invalid step schema/number')
        if not all(isinstance(step[k], str) for k in STEP_FIELDS - {'step_no'}):
            raise ValueError('step text field type invalid')
        if step['phase'] not in OPERATIONS or step['operation'] not in OPERATIONS[step['phase']] or step['state'] != STATES[step['operation']]:
            raise ValueError('invalid operation/state/phase')
        if row['deletion_status'] == 'COMPLETE' and step['phase'] != 'VERIFICATION':
            raise ValueError('complete case has nonverification step')
        needs_evidence = step['phase'] == 'FINDING' or row['deletion_status'] == 'COMPLETE'
        if needs_evidence != bool(step['evidence_id']):
            raise ValueError('incorrect evidence assignment')
        if evidence_registry is not None and step['evidence_id']:
            when = evidence_registry.get(step['evidence_id'])
            if when is None or (cutoff and (not timestamp(when) or timestamp(when) > timestamp(cutoff))):
                raise ValueError('unknown or later evidence ID')
    if steps != sorted(steps, key=sort_key):
        raise ValueError('noncanonical step order')
    if row['deletion_status'] == 'COMPLETE' and not steps:
        raise ValueError('empty array cannot prove completion')
    return True
