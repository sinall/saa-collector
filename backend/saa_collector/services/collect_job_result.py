"""Bounded task evidence. Never serialize arbitrary exceptions or HTTP payloads."""
from copy import deepcopy
import hashlib
import json


ISSUE_FIELDS = {'code', 'provider', 'symbol', 'table', 'report_date',
                'disclosure_date', 'version_type', 'differences', 'action'}


def _encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def merge_issue(result, issue, now, *, max_issues=100, max_bytes=256 * 1024):
    if not isinstance(issue, dict) or set(issue) - ISSUE_FIELDS or not issue.get('code'):
        raise ValueError('Unsupported task issue payload')
    if (result or {}).get('schema_version', 1) != 1:
        raise ValueError('Unsupported task result schema')
    candidate = deepcopy(result or {})
    candidate.setdefault('schema_version', 1)
    candidate.setdefault('issues', [])
    fingerprint = hashlib.sha256(_encoded(issue)).hexdigest()
    for item in candidate['issues']:
        if item['fingerprint'] == fingerprint:
            item.update(occurrences=item['occurrences'] + 1,
                        last_seen_at=now, resolved_at=None)
            break
    else:
        candidate['issues'].append(dict(deepcopy(issue), fingerprint=fingerprint,
            occurrences=1, first_seen_at=now, last_seen_at=now, resolved_at=None))
    candidate['issue_count'] = len(candidate['issues'])
    if len(candidate['issues']) > max_issues or len(_encoded(candidate)) > max_bytes:
        candidate = deepcopy(result or {})
        candidate.setdefault('schema_version', 1)
        candidate.setdefault('issues', [])
        candidate['issue_count'] = len(candidate['issues'])
        candidate['truncated'] = True
        candidate['omitted_events'] = candidate.get('omitted_events', 0) + 1
    return candidate


def resolve_symbol(result, symbol, now):
    result = deepcopy(result or {})
    for item in result.get('issues', []):
        if item.get('symbol') == symbol and not item.get('resolved_at'):
            item['resolved_at'] = now
    return result


def result_message(result):
    summary = (result or {}).get('summary', {})
    if not {'succeeded_symbols', 'failed_symbols'}.issubset(summary):
        return None
    return '完成{}只，失败{}只'.format(summary['succeeded_symbols'], summary['failed_symbols'])


def record_issue(job_id, issue):
    # Called after the source transaction has unwound, in a short independent
    # Django transaction; never hold this row lock during an upstream request.
    from django.db import transaction
    from django.utils import timezone
    from saa_collector.models import CollectJob
    with transaction.atomic():
        job = CollectJob.objects.select_for_update().get(pk=job_id)
        job.result = merge_issue(job.result, issue, timezone.now().isoformat())
        job.save(update_fields=['result'])
