from unittest import TestCase

from saa_collector.services.collect_job_result import merge_issue, resolve_symbol


class CollectJobResultTest(TestCase):
    def test_version_types_are_preserved_as_distinct_conflicts(self):
        result = {}
        for kind in ('LATEST', 'ORIGINAL', 'RESTATED'):
            issue = dict(code='STATEMENT_VERSION_CONFLICT', symbol='600036',
                         version_type=kind)
            result = merge_issue(result, issue, 'now')
            result = merge_issue(result, issue, 'later')
        self.assertEqual(result['issue_count'], 3)
        self.assertEqual([item['version_type'] for item in result['issues']],
                         ['LATEST', 'ORIGINAL', 'RESTATED'])
        self.assertEqual([item['occurrences'] for item in result['issues']], [2, 2, 2])

    def test_duplicate_retries_and_resolution_preserve_evidence(self):
        issue = {'code': 'SOURCE_FAILURE', 'symbol': '600036'}
        first = merge_issue({}, issue, '2026-10-31T00:00:00Z')
        second = merge_issue(first, issue, '2026-10-31T01:00:00Z')
        self.assertEqual(first['issues'][0]['occurrences'], 1)
        self.assertEqual(second['issue_count'], 1)
        self.assertEqual(second['issues'][0]['occurrences'], 2)
        resolved = resolve_symbol(second, '600036', '2026-10-31T02:00:00Z')
        self.assertEqual(resolved['issues'][0]['resolved_at'], '2026-10-31T02:00:00Z')
        again = merge_issue(resolved, issue, '2026-10-31T03:00:00Z')
        self.assertIsNone(again['issues'][0]['resolved_at'])

    def test_changed_evidence_is_new_issue(self):
        first = merge_issue({}, {'code': 'CONFLICT', 'symbol': '600036',
                                'differences': {'net_profit': {'value': '10'}}}, 'now')
        second = merge_issue(first, {'code': 'CONFLICT', 'symbol': '600036',
                                    'differences': {'net_profit': {'value': '20'}}}, 'later')
        self.assertEqual(second['issue_count'], 2)

    def test_limits_do_not_silently_drop_failures(self):
        first = merge_issue({}, {'code': 'FAILURE', 'symbol': '600036'}, 'now')
        second = merge_issue(first, {'code': 'FAILURE', 'symbol': '600000'}, 'now', max_issues=1)
        self.assertTrue(second['truncated'])
        self.assertEqual(second['omitted_events'], 1)
        self.assertEqual(second['issue_count'], 1)
        oversized = merge_issue({}, {'code': 'FAILURE', 'symbol': '600000',
                                     'differences': {'value': 'x' * 10000}}, 'now', max_bytes=1024)
        self.assertTrue(oversized['truncated'])

    def test_unknown_top_level_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            merge_issue({}, {'code': 'FAILURE', 'token': 'secret'}, 'now')

    def test_future_schema_is_not_rewritten(self):
        with self.assertRaises(ValueError):
            merge_issue({'schema_version': 2}, {'code': 'FAILURE'}, 'now')
