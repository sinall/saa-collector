import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from saa_collector.services.common import financial_statement_contract as contract
from saa_collector.services.common.statement_version_writer import (
    StatementVersionConflict, prepare_version, write_versions,
)


class StatementVersionWriterTest(unittest.TestCase):
    table = 'saa_raw_income_statement'

    def row(self):
        row = dict.fromkeys(contract.financial_fields(self.table))
        row.update(symbol='600036', report_date=date(2012, 12, 31),
                   disclosure_date=date(2013, 3, 29), provider='tushare',
                   source_metadata={'endpoint': 'income', 'report_type': '1'},
                   net_profit=Decimal('100.00'))
        return row

    def connection(self):
        connection = Mock(in_transaction=True, autocommit=False)
        cursor = connection.cursor.return_value
        indexes = [('PRIMARY', ['id']), ('uq_disclosure',
                    ['symbol', 'report_date', 'disclosure_date'])]
        cursor.fetchall.return_value = [
            {'Key_name': name, 'Non_unique': 0, 'Seq_in_index': index,
             'Column_name': field, 'Sub_part': None}
            for name, fields in indexes for index, field in enumerate(fields, 1)]
        cursor.lastrowid = 7
        return connection, cursor

    def test_snapshot_is_complete_hash_is_recomputed_and_input_unchanged(self):
        row = self.row()
        prepared = prepare_version(self.table, row)
        self.assertEqual(prepared['content_hash'], contract.content_hash(self.table, row))
        self.assertEqual(prepared['net_profit'], Decimal('100.00'))
        self.assertIsInstance(row['source_metadata'], dict)
        self.assertNotIn('content_hash', row)

    def test_invalid_inputs_fail_before_any_sql(self):
        mutations = [dict(disclosure_date=None), dict(provider='TUSHARE'),
                     dict(source_metadata={'token': 'secret'}), dict(id=1),
                     dict(content_hash='a' * 64), dict(net_profit=float('inf')),
                     dict(symbol=' 600036'), dict(disclosure_date=date(2012, 1, 1))]
        for mutation in mutations:
            with self.subTest(mutation=list(mutation)):
                connection, cursor = self.connection()
                row = self.row()
                row.update(mutation)
                with self.assertRaises(ValueError):
                    write_versions(connection, self.table, [row])
                cursor.execute.assert_not_called()

    def test_partial_snapshot_is_not_silently_filled(self):
        row = self.row()
        del row['net_profit']
        with self.assertRaises(ValueError):
            prepare_version(self.table, row)

    def test_omitted_field_does_not_inherit_or_query_older_values(self):
        connection, cursor = self.connection()
        row = self.row()
        row['source_metadata']['omitted_fields'] = ['subsidy_income']
        cursor.fetchone.return_value = {'disclosure_date': date(2013, 3, 28),
                                       'subsidy_income': Decimal('12.00')}
        self.assertTrue(write_versions(connection, self.table, [row])[0]['created'])
        self.assertFalse(any('SELECT disclosure_date' in call.args[0]
                             for call in cursor.execute.call_args_list))
        self.assertIsNone(prepare_version(self.table, row)['subsidy_income'])

    def test_omitted_field_without_existing_value_is_traceable(self):
        import json
        connection, cursor = self.connection()
        cursor.fetchone.return_value = None
        row = self.row()
        row['source_metadata']['omitted_fields'] = ['subsidy_income']
        prepared = prepare_version(self.table, row)
        self.assertEqual(json.loads(prepared['source_metadata'])['omitted_fields'], ['subsidy_income'])
        self.assertTrue(write_versions(connection, self.table, [row])[0]['created'])

    def test_invalid_coverage_metadata_rejected(self):
        for omitted in (['token'], ['subsidy_income'] * 2, 'subsidy_income', ['net_profit']):
            row = self.row()
            row['source_metadata']['omitted_fields'] = omitted
            with self.subTest(omitted=omitted), self.assertRaises(ValueError):
                prepare_version(self.table, row)

    def test_requires_caller_transaction(self):
        connection, cursor = self.connection()
        connection.in_transaction = False
        with self.assertRaises(ValueError):
            write_versions(connection, self.table, [self.row()])
        cursor.execute.assert_not_called()

    def test_legacy_unique_key_is_rejected_before_insert(self):
        connection, cursor = self.connection()
        cursor.fetchall.return_value = [
            {'Key_name': 'PRIMARY', 'Non_unique': 0, 'Seq_in_index': index,
             'Column_name': field, 'Sub_part': None}
            for index, field in enumerate(['symbol', 'report_date'], 1)]
        with self.assertRaises(ValueError):
            write_versions(connection, self.table, [self.row()])
        self.assertFalse(any('INSERT' in call.args[0] for call in cursor.execute.call_args_list))

    def test_insert_leaves_commit_to_caller(self):
        connection, cursor = self.connection()
        self.assertEqual(write_versions(connection, self.table, [self.row()]),
                         [{'id': 7, 'created': True}])
        connection.commit.assert_not_called()
        connection.rollback.assert_not_called()
        cursor.close.assert_called_once()

    def test_duplicate_keeps_existing_provider_and_checks_financial_content(self):
        from mysql.connector import IntegrityError
        connection, cursor = self.connection()
        cursor.execute.side_effect = [None, IntegrityError(errno=1062), None]
        existing = prepare_version(self.table, self.row())
        existing.update(id=4, provider='akshare')
        cursor.fetchone.return_value = existing
        self.assertEqual(write_versions(connection, self.table, [self.row()]),
                         [{'id': 4, 'created': False}])
        self.assertIn('FOR UPDATE', cursor.execute.call_args.args[0])
        self.assertFalse(any('UPDATE ' in call.args[0] for call in cursor.execute.call_args_list))

    def test_duplicate_conflict_is_not_overwritten(self):
        from mysql.connector import IntegrityError
        connection, cursor = self.connection()
        cursor.execute.side_effect = [None, IntegrityError(errno=1062), None]
        changed = self.row()
        changed['net_profit'] = Decimal('120')
        cursor.fetchone.return_value = dict(prepare_version(self.table, changed), id=4)
        incoming = self.row()
        incoming['provider'] = 'akshare'
        with self.assertRaises(StatementVersionConflict):
            write_versions(connection, self.table, [incoming])
        connection.commit.assert_not_called()
        cursor.close.assert_called_once()

    def test_confirmed_updated_snapshot_replaces_only_same_daily_id(self):
        from mysql.connector import IntegrityError
        connection, cursor = self.connection()
        cursor.execute.side_effect = [None, IntegrityError(errno=1062), None, None]
        row = self.row()
        row['source_metadata']['update_flag'] = '1'
        old = dict(prepare_version(self.table, self.row()), id=4)
        row['net_profit'] = Decimal('120')
        cursor.fetchone.return_value = old
        result = write_versions(connection, self.table, [row])
        self.assertTrue(result[0]['updated'])
        self.assertFalse(result[0]['created'])
        sql, params = cursor.execute.call_args.args
        self.assertIn('WHERE id=%s AND content_hash=%s', sql)
        self.assertEqual(params[-2:], (4, old['content_hash']))
        self.assertEqual(result[0]['audit']['differences']['net_profit']['existing_value'], '100.00')
        connection.commit.assert_not_called()

    def test_updated_snapshot_cannot_hide_corrupt_stored_hash(self):
        from mysql.connector import IntegrityError
        connection, cursor = self.connection()
        cursor.execute.side_effect = [None, IntegrityError(errno=1062), None]
        row = self.row()
        row['source_metadata']['update_flag'] = '1'
        cursor.fetchone.return_value = dict(prepare_version(self.table, row), id=4, content_hash='bad')
        with self.assertRaises(StatementVersionConflict):
            write_versions(connection, self.table, [row])

    def test_original_snapshot_replaces_whole_row_and_clears_omission(self):
        from mysql.connector import IntegrityError
        connection, cursor = self.connection()
        cursor.execute.side_effect = [None, IntegrityError(errno=1062), None, None]
        previous = self.row()
        previous['subsidy_income'] = Decimal('12')
        old = dict(prepare_version(self.table, previous), id=4)
        row = self.row()
        row['source_metadata'].update(update_flag='0', omitted_fields=['subsidy_income'])
        row['other_comprehensive_income'] = Decimal('183958.40')
        cursor.fetchone.return_value = old
        result = write_versions(connection, self.table, [row])[0]
        self.assertTrue(result['updated'])
        self.assertEqual(result['audit']['differences']['subsidy_income']['existing_value'], '12')
        self.assertIsNone(result['audit']['differences']['subsidy_income']['candidates'][0]['value'])
        sql, params = cursor.execute.call_args.args
        fields = ('provider', 'source_metadata', 'content_hash') + tuple(contract.financial_fields(self.table))
        self.assertIsNone(params[fields.index('subsidy_income')])
        self.assertEqual(params[fields.index('other_comprehensive_income')], Decimal('183958.40'))
        self.assertEqual(params[-2:], (4, old['content_hash']))
