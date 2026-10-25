"""Deterministic temporal state reconstruction and supplied policy application."""
import re
from collections import defaultdict

from common import EMAIL_RE, eligible, flatten, normalize, read_csv, timestamp, truth


EXPECTED = {'DELETE': 'ABSENT', 'REDACT': 'REDACTED', 'ANONYMIZE': 'ANONYMIZED',
            'RETAIN': 'PRESENT', 'DISABLE': 'DISABLED', 'BLOCK_RESTORE': 'BLOCKED'}


def load_rules(dataset):
    return {row['data_category']: row for row in read_csv(dataset / 'deletion_rules.csv')}


def nonempty(value):
    return value is not None and normalize(value) not in {'', 'null', 'none', '[redacted]', 'redacted', 'anonymous', 'anonymized', 'n/a',
                                                         '\u2014','-','[removed]'}


def exposed(facts, category, context):
    fields = flatten(facts)
    # Search/lookup arguments and retained internal support references are not current payload PII.
    direct = ['email', 'phone', 'email_hash', 'name', 'full_name', 'display_name', 'requester_name',
              'requester_email', 'requester_phone', 'owner_email', 'owner_phone', 'customer_email']
    if any(nonempty(fields.get(field)) for field in direct):
        return True
    if category in {'ANALYTICS_PROFILE', 'PRODUCT_TELEMETRY'}:
        if any(nonempty(fields.get(field)) for field in ['user_id', 'customer_reference', 'subject_reference', 'subject_ref']):
            return True
    if fields.get('matched_value') and nonempty(fields['matched_value']):
        return True
    if fields.get('direct_identifiers') is not None:
        return normalize(fields['direct_identifiers']) not in {'0', 'false', 'none'}
    for key in ['message_text', 'message_excerpt', 'body', 'text', 'document_text']:
        text = str(fields.get(key, ''))
        if any(normalize(email) in context['identifiers'] for email in EMAIL_RE.findall(text)):
            return True
    return False


def observed_state(obs, context):
    facts = obs['facts']
    fields = flatten(facts)
    category = obs['category']
    result = str(fields.get('result', '')).upper()
    if result in {'NOT_FOUND', 'ABSENT', 'DELETED'} or str(fields.get('status_code', fields.get('http_status'))) == '404':
        return 'ABSENT'
    if str(fields.get('rows')) == '0' or str(fields.get('total_hits')) == '0':
        return 'ABSENT'
    hits = facts.get('hits')
    if isinstance(hits, dict) and hits.get('total') == 0:
        return 'ABSENT'
    if category == 'DATA_FLOW':
        enabled = truth(fields.get('enabled'))
        if enabled is not None:
            return 'ACTIVE' if enabled else 'DISABLED'
        return result if result in {'ACTIVE', 'DISABLED'} else 'UNKNOWN'
    if category == 'BACKUP_ARCHIVE':
        allowed = truth(fields.get('restore_allowed'))
        if allowed is not None:
            return 'ACTIVE' if allowed else 'BLOCKED'
        if truth(fields.get('deletion_block')) is True:
            return 'BLOCKED'
        if truth(fields.get('eligible')) is True and truth(fields.get('deletion_block')) is False:
            return 'ACTIVE'
        if normalize(fields.get('decision')) in {'deny', 'denied'} and normalize(fields.get('policy')) == 'privacy_deletion':
            return 'BLOCKED'
        return result if result in {'ACTIVE', 'BLOCKED'} else 'UNKNOWN'
    if category in {'SUPPORT_MESSAGE', 'EMAIL_DELIVERY_LOG', 'ACCOUNT_TOMBSTONE', 'ANALYTICS_PROFILE', 'PRODUCT_TELEMETRY'}:
        treatment = 'ANONYMIZED' if category in {'ANALYTICS_PROFILE', 'PRODUCT_TELEMETRY'} else 'REDACTED'
        if exposed(facts, category, context):
            return 'IDENTIFIABLE'
        if str(fields.get('rows')) == '1' and ('lookup_completed' in str(fields.get('event', '')) or 'query_completed' in str(fields.get('event', ''))):
            for key in ['lookup_key', 'match_key', 'correlation_key']:
                value = normalize(fields.get(key))
                if value and value in context['identifiers'] and ('@' in value or re.fullmatch(r'[a-f0-9]{64}', value)):
                    return 'IDENTIFIABLE'
        if result == 'IDENTIFIABLE':
            return 'IDENTIFIABLE'
        if category == 'ACCOUNT_TOMBSTONE' and not any(nonempty(fields.get(k)) for k in ['subject_reference', 'customer_reference', 'user_id', 'subject_ref']):
            return 'UNKNOWN'
        if fields.get('direct_identifiers') is not None and normalize(fields['direct_identifiers']) == '0':
            return treatment
        if fields.get('pii_fields') is not None and normalize(fields['pii_fields']) == '0':
            return treatment
        # Missing fields in a partial read do not prove removal. Accept a complete
        # snapshot payload, or an explicitly inspected set covering the identifiers.
        contact_coverage = {'email', 'phone', 'email_hash'}.issubset(fields)
        unlink_coverage = any(key in fields for key in ['user_id', 'subject_reference', 'customer_reference', 'subject_ref'])
        if obs.get('payload_complete') or contact_coverage and (unlink_coverage if treatment == 'ANONYMIZED' else 'name' in fields):
            return treatment
        return 'UNKNOWN'
    # Structured row, observed existence or completed positive read.
    if fields.get('resource_id') or truth(fields.get('record_exists')) or result in {'FOUND', 'PRESENT'} or str(fields.get('rows')) == '1':
        return 'PRESENT'
    return 'UNKNOWN'


def requirement(category, rules):
    if category == 'DATA_FLOW':
        return 'DISABLE', 'DISABLED', 'process-risk'
    if category == 'BACKUP_ARCHIVE' and category in rules:
        return 'BLOCK_RESTORE', 'BLOCKED', rules[category]['rule_id']
    rule = rules.get(category)
    if not rule:
        return None, None, None
    return rule['required_action'], EXPECTED.get(rule['required_action']), rule['rule_id']


def flow_risk(obs, observations, rules, context):
    """True: prohibited payload path, False: explicit permitted scope, None: unknown."""
    facts, fields = obs['facts'], flatten(obs['facts'])
    selector = normalize(next((fields[key] for key in ['subject_selector','subject_reference','customer_reference',
                            'subject_ref','lookup_key','subject_key'] if fields.get(key)),''))
    if selector and ('@' in selector or selector.startswith('user_')) and selector not in context['identifiers']:
        return False
    categories = facts.get('data_categories', facts.get('copied_categories', fields.get('payload_category')))
    if isinstance(categories, str):
        categories = [part.strip() for part in categories.split(',')]
    if isinstance(categories, list) and categories:
        actions = [rules.get(str(category), {}).get('required_action') for category in categories]
        if all(action == 'RETAIN' for action in actions):
            return False
        if any(action in {'DELETE', 'REDACT', 'ANONYMIZE'} for action in actions):
            return True
        return None
    endpoints = {str(fields[key]) for key in ['source_resource_id', 'target_resource_id', 'destination_resource_id'] if fields.get(key)}
    related_categories = {row['category'] for row in observations if row['resource_id'] in endpoints
                          and row.get('kind') != 'claim' and eligible(row, context['audit_at'])}
    if any(rules.get(category, {}).get('required_action') in {'DELETE', 'REDACT', 'ANONYMIZE'} for category in related_categories):
        return True
    # A subject-selected customer connector feeding an analytics destination is
    # observable copy capability; a bare enabled flag supplies no such scope.
    description = normalize(str(fields.get('connector_name', '')) + ' ' + str(fields.get('destination', '')))
    if selector in context['identifiers'] and re.search(r'customer|profile|personal', description) and re.search(r'analytics|warehouse|search|export', description):
        return True
    if selector in context['identifiers'] and (fields.get('event')=='connector_heartbeat' or
        obs.get('category')=='DATA_FLOW' and fields.get('result')=='ACTIVE'):
        return True
    return None


def assess_case(context, observations, rules, extraction_warnings=None):
    warnings = list(context.get('warnings', [])) + list(extraction_warnings or [])
    grouped = defaultdict(list)
    claims = defaultdict(list)
    for obs in observations:
        if not eligible(obs, context['audit_at']):
            continue
        if obs.get('kind') == 'claim':
            claims[(obs['system_id'], obs['resource_id'])].append(obs)
        else:
            grouped[(obs['system_id'], obs['resource_id'], obs.get('scope', 'primary'))].append(obs)
    scoped = defaultdict(list)
    for (system, resource, scope), rows in sorted(grouped.items()):
        # Latest actual observation; equivalent observations have a deterministic tie break.
        # A marker/metadata check does not replace an earlier completed record read.
        conclusive=[row for row in rows if observed_state(row,context)!='UNKNOWN']
        when = max(timestamp(row['observed_at']) for row in (conclusive or rows))
        latest = [row for row in (conclusive or rows) if timestamp(row['observed_at']) == when]
        chosen = min(latest, key=lambda row: (row['evidence_id'], row['location']))
        category = chosen['category']
        # Explicit attachment metadata beats a generic support resource prefix.
        if category == 'SUPPORT_MESSAGE' and any(r['category'] == 'SUPPORT_ATTACHMENT' for r in rows):
            category = 'SUPPORT_ATTACHMENT'
        chosen = {**chosen, 'category': category}
        state = observed_state(chosen, context)
        states = {observed_state({**row, 'category': category}, context) for row in latest}
        action, expected, rule_id = requirement(category, rules)
        assessment = 'COMPLIANT' if expected and state == expected else ('UNCERTAIN' if state == 'UNKNOWN' or not expected else 'VIOLATION')
        if category == 'DATA_FLOW' and state == 'ACTIVE':
            risk = flow_risk(chosen, observations, rules, context)
            if risk is False:
                assessment, action, expected = 'PERMITTED', None, None
            elif risk is None:
                assessment = 'UNCERTAIN'
                warnings.append(f'{resource}: active flow payload scope unresolved')
        if len(states - {'UNKNOWN'}) > 1:
            assessment = 'UNCERTAIN'
            warnings.append(f'{resource}: conflicting same-time observations in {scope}')
        if not action:
            warnings.append(f'{resource}: unknown category/policy; no invented treatment')
        # Respect supplied retention/hold conditions when explicit dates/flags are available.
        fields = flatten(chosen['facts'])
        retain_until = timestamp(fields.get('retention_until', fields.get('retained_until')))
        if category in {'SECURITY_AUDIT_LOG', 'LEGAL_HOLD_RECORD'} and retain_until and retain_until < timestamp(context['audit_at']):
            assessment = 'UNCERTAIN'
            warnings.append(f'{resource}: retention expired; no replacement policy supplied')
        if category == 'LEGAL_HOLD_RECORD' and truth(fields.get('legal_hold_active')) is False:
            assessment = 'UNCERTAIN'
            warnings.append(f'{resource}: hold not active; treatment unresolved')
        for claim in claims.get((system, resource), []):
            event = claim['facts'].get('event_type', '')
            if timestamp(claim['observed_at']) > when and event in {'DELETE_RECORD', 'REDACT_RECORD', 'ANONYMIZE_RECORD', 'SYNC_RECORD', 'RESTORE_BACKUP', 'UPDATE_RECORD', 'INDEX_RECORD', 'DISABLE_DATA_FLOW', 'BLOCK_RESTORE'}:
                warnings.append(f'{resource}: later {event} claim lacks a confirming state observation')
                preserves_absence=state=='ABSENT' and event in {'DELETE_RECORD','REDACT_RECORD','ANONYMIZE_RECORD'}
                if assessment == 'COMPLIANT' and not preserves_absence:
                    assessment = 'UNCERTAIN'
        scoped[(system, resource)].append({'system_id': system, 'resource_id': resource, 'category': category,
                                           'state': state, 'action': action, 'expected_state': expected,
                                           'rule_id': rule_id, 'assessment': assessment, 'evidence_id': chosen['evidence_id'],
                                           'observed_at': chosen['observed_at'], 'scope': scope,
                                           'location': chosen['location']})
    resources = []
    for key, scopes in sorted(scoped.items()):
        violations = [r for r in scopes if r['assessment'] == 'VIOLATION']
        uncertain = [r for r in scopes if r['assessment'] == 'UNCERTAIN']
        candidates = violations or uncertain or scopes
        selected = sorted(candidates, key=lambda r: (r['observed_at'], r['evidence_id']), reverse=True)[0]
        resources.append({**selected, 'scope_assessments': scopes})
    # Claim-only resources are material unknowns, not successful operations or findings.
    for (system, resource), events in sorted(claims.items()):
        if (system, resource) in scoped:
            continue
        last = max(events, key=lambda o: o['observed_at'])
        action, expected, rule_id = requirement(last['category'], rules)
        resources.append({'system_id': system, 'resource_id': resource, 'category': last['category'],
                          'state': 'UNKNOWN', 'action': action, 'expected_state': expected, 'rule_id': rule_id,
                          'assessment': 'UNCERTAIN', 'evidence_id': '', 'scope_assessments': []})
        warnings.append(f'{resource}: operation/linkage claims only; state unknown')
    graph = process_paths([o for o in observations if eligible(o, context['audit_at'])])
    for resource in resources:
        if resource['category'] in {'DATA_FLOW', 'BACKUP_ARCHIVE'}:
            resource['reachable_resources'] = reachable_resources(graph, resource['resource_id'])
    coverage_gap=context['intent']=='DELETION' and not resources
    if coverage_gap:warnings.append('No subject-linked state evidence at the audit cutoff.')
    return {'case_id': context['case_id'], 'intent': context['intent'], 'audit_at': context['audit_at'],
            'resources': resources, 'warnings': sorted(set(warnings)),
            'process_paths': graph,
            'observation_failure':bool(extraction_warnings),
            'uncertain': coverage_gap or bool(extraction_warnings) or any(r['assessment'] == 'UNCERTAIN' for r in resources)}


def process_paths(observations):
    """Evidence-backed resource adjacency; cycles are traversed with a visited set."""
    edges = defaultdict(set)
    for obs in observations:
        source = obs['resource_id']
        for linked in obs.get('linked_resources', []):
            edges[source].add(linked)
        fields = flatten(obs['facts'])
        for key in ['source_resource_id', 'target_resource_id', 'destination_resource_id']:
            if fields.get(key):
                edges[source].add(str(fields[key]))
    return {key: sorted(value) for key, value in edges.items()}


def reachable_resources(graph, start):
    visited = {start}
    pending = list(graph.get(start, []))
    while pending:
        node = pending.pop()
        if node in visited:
            continue
        visited.add(node)
        pending.extend(graph.get(node, []))
    return sorted(visited - {start})
