"""Small shared parsing and serialization helpers."""
import csv
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

VERSION = '1.0.0'
EMAIL_RE = re.compile(r'[\w.+%\-]+@[\w.\-]+\.[A-Za-z]{2,}', re.UNICODE)
RESOURCE_RE = re.compile(r'(?<![\w])(?:account|analytics|search|support|export|data_flow|backup|audit_record|legal_hold|tombstone|marketing|cache|delivery_log|telemetry|secondary_identifier)_[\w-]+')
USER_RE = re.compile(r'(?<![\w])user_[\w-]+')
TIME_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z')


def normalize(value):
    return unicodedata.normalize('NFKC', str(value or '')).strip().casefold()


def timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def eligible(observation, cutoff):
    end = timestamp(cutoff)
    captured = timestamp(observation.get('captured_at'))
    observed = timestamp(observation.get('observed_at'))
    extra = [timestamp(observation[key]) for key in ['snapshot_at', 'event_at'] if key in observation]
    extra.extend(timestamp(value) for value in observation.get('source_times', []))
    return bool(end and captured and observed and captured <= end and observed <= end
                and all(value and value <= end for value in extra))


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def atomic_replace(source,target):
    """Retry brief sharing denials; never claim a permanently denied write worked."""
    delays=[.02,.05,.1,.2]
    for attempt in range(len(delays)+1):
        try:
            Path(source).replace(target)
            return
        except PermissionError:
            if attempt==len(delays):raise
            time.sleep(delays[attempt])


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
    atomic_replace(temp,path)


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def scalar_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from scalar_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from scalar_values(child)
    elif value is not None:
        yield str(value)


def identifiers(value):
    result = set()
    for text in scalar_values(value):
        result.update(normalize(s) for s in EMAIL_RE.findall(text))
        result.update(normalize(s) for s in USER_RE.findall(text))
        if re.fullmatch(r'[a-fA-F0-9]{64}', text):
            result.add(normalize(text))
        if re.fullmatch(r'\+?[\d ()-]{7,25}', text):
            result.add(normalize(text))
    return result


def truth(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = normalize(value)
    if text in {'true', '1', 'yes', 'enabled', 'active', 'allowed'}:
        return True
    if text in {'false', '0', 'no', 'disabled', 'blocked', 'denied'}:
        return False
    return None


def flatten(value):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, dict):
                result.update(flatten(child))
            elif not isinstance(child, list):
                result[key] = child
    return result
