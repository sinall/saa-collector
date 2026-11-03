"""Opt-in MySQL checks using only a disposable, network-disabled container.

No Django bootstrap, vault, host port or application DB settings.
The only host mount is a test-owned temporary Unix socket directory.
Run with PIT_MYSQL_DOCKER_TESTS=1 after pulling the official mysql:8.0 image.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import mysql.connector

from saa_collector.services.common import financial_statement_contract as contract
from saa_collector.services.common.statement_version_writer import (
    StatementVersionConflict, write_versions,
)
from saa_collector.services.common.statement_migration_plan import (
    legacy_snapshot, shadow_statements, latest_combined_definition, cutover_rename_sql,
    combined_view_cutover_sql, pre_ingestion_restore_sql,
)
from saa_collector.utils.db import DB
from saa_collector.services.common.statement_legacy_guard import assert_legacy_write_allowed
from saa_collector.services.common.statement_shadow_copy import copy_legacy_to_shadow, verify_legacy_shadow
from saa_collector.services.common.statement_ingestion import save_version_bundle
from saa_collector.services.common.statement_cache_publisher import CACHE_COLUMNS, publish_statement_caches
from saa_collector.services.common.statement_maintain_service import StatementMaintainService
from saa_collector.services.common.statement_locks import statement_locks


@unittest.skipUnless(os.environ.get('PIT_MYSQL_DOCKER_TESTS') == '1',
                     'Requires explicit disposable MySQL opt-in')
class IsolatedStatementMySQLTest(unittest.TestCase):
    def test_derived_latest_lifecycle_preserves_history_and_rolls_back(self):
        from saa_collector.services.common.statement_kind_migration import render_packet
        table = 'saa_raw_income_statement'
        packet = render_packet()
        self.query(packet['01-version-kinds.sql'])
        self.query(packet['02-latest-views.sql'])
        row = dict.fromkeys(contract.financial_fields(table))
        row.update(symbol='600036', report_date=date(2012, 12, 31),
                   disclosure_date=date(2014, 3, 29), provider='tushare',
                   version_type='RESTATED', source_metadata={'report_type': '4'}, net_profit=110)
        derived = dict(row, version_type='LATEST', source_metadata=dict(
            snapshot_origin='derived_latest', derived_from_type='RESTATED',
            derived_from_hash=contract.content_hash(table, row)))
        connection = self.connection()
        connection.rollback()
        connection.start_transaction()
        write_versions(connection, table, [row, derived])
        connection.commit()
        before = self.query('SELECT id,version_type,net_profit FROM ' + table + ' ORDER BY id').stdout
        real = dict(row, version_type='LATEST', disclosure_date=date(2013, 3, 29),
                    source_metadata={'report_type': '1'}, net_profit=100)
        connection.start_transaction()
        result = write_versions(connection, table, [real])
        self.assertEqual(len(result[0]['superseded_derived_latest']), 1)
        connection.rollback()
        self.assertEqual(before, self.query('SELECT id,version_type,net_profit FROM ' + table + ' ORDER BY id').stdout)
        connection.start_transaction()
        write_versions(connection, table, [real])
        connection.commit()
        self.assertEqual(self.query('SELECT net_profit FROM saa_latest_income_statement').stdout.strip(), '100.00')
        self.assertEqual(self.query("SELECT net_profit FROM " + table + " WHERE version_type='RESTATED'").stdout.strip(), '110.00')
        connection.start_transaction()
        self.assertEqual(write_versions(connection, table, [derived])[0]['reason'], 'GENUINE_LATEST_EXISTS')
        connection.commit()
        self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table).stdout.strip(), '2')
        connection.close()

    def test_genuine_latest_same_value_promotes_provenance_and_preserves_id(self):
        from saa_collector.services.common.statement_kind_migration import render_packet
        table = 'saa_raw_income_statement'
        self.query(render_packet()['01-version-kinds.sql'])
        row = dict.fromkeys(contract.financial_fields(table))
        row.update(symbol='600036', report_date=date(2012, 12, 31),
                   disclosure_date=date(2014, 3, 29), provider='tushare',
                   version_type='LATEST', net_profit=110)
        row['source_metadata'] = dict(snapshot_origin='derived_latest',
            derived_from_type='RESTATED', derived_from_hash=contract.content_hash(table, row))
        connection = self.connection()
        connection.rollback()
        connection.start_transaction()
        first = write_versions(connection, table, [row])[0]
        connection.commit()
        connection.start_transaction()
        real = dict(row, source_metadata={'report_type': '1'})
        second = write_versions(connection, table, [real])[0]
        connection.commit()
        self.assertEqual(first['id'], second['id'])
        self.assertTrue(second['updated'])
        self.assertEqual(self.query("SELECT JSON_UNQUOTE(JSON_EXTRACT(source_metadata, '$.report_type')) FROM " + table).stdout.strip(), '1')
        connection.close()

    def test_signed_impairment_update_and_metadata_are_idempotent_and_rollbackable(self):
        from decimal import Decimal
        from saa_collector.services.common.statement_kind_migration import render_packet
        table = 'saa_raw_income_statement'
        self.query(render_packet()['01-version-kinds.sql'])
        row = dict.fromkeys(contract.financial_fields(table))
        row.update(symbol='600284', report_date=date(2018, 12, 31),
                   disclosure_date=date(2019, 3, 12), provider='tushare',
                   version_type='LATEST', asset_impairment_loss=Decimal('11574269.74'),
                   source_metadata={'report_type': '1'})
        connection = self.connection()
        connection.rollback()
        connection.start_transaction()
        first = write_versions(connection, table, [row])[0]
        connection.commit()
        corrected = dict(row, asset_impairment_loss=Decimal('-11574269.74'),
            source_metadata={'report_type': '1', 'normalization_rule': 'impairment_signed_v1'})
        connection.start_transaction()
        replacement = write_versions(connection, table, [corrected])[0]
        self.assertTrue(replacement['updated'])
        self.assertEqual(first['id'], replacement['id'])
        connection.rollback()
        self.assertEqual(self.query('SELECT asset_impairment_loss FROM ' + table).stdout.strip(),
                         '11574269.74')
        connection.start_transaction()
        write_versions(connection, table, [corrected])
        connection.commit()
        connection.start_transaction()
        duplicate = write_versions(connection, table, [corrected])[0]
        self.assertEqual(duplicate, {'id': first['id'], 'created': False})
        connection.commit()
        proof = dict(corrected, source_metadata=dict(corrected['source_metadata'],
                     impairment_source_value='11574269.74'))
        connection.start_transaction()
        self.assertTrue(write_versions(connection, table, [proof])[0]['metadata_updated'])
        connection.commit()
        connection.start_transaction()
        self.assertEqual(write_versions(connection, table, [proof])[0], duplicate)
        connection.commit()
        connection.close()

    def test_conflict_null_roundtrip_retains_quality_and_unchanged_profit(self):
        import pandas as pd
        from decimal import Decimal
        from saa_collector.services.common.statement_kind_migration import render_packet
        from saa_collector.services.common.statement_source_adapter import tushare_snapshots, statement_field_issues
        table = 'saa_raw_income_statement'
        self.query(render_packet()['01-version-kinds.sql'])
        source = json.loads((Path(__file__).parent / 'fixtures/tushare_conflict_300202.json').read_text())
        mapping = pd.read_excel(Path(__file__).parents[1] / 'config/table-config.xls', sheet_name=table)
        rows = tushare_snapshots(table, source, mapping, normalize_signs=True)
        connection = self.connection()
        connection.rollback()
        connection.start_transaction()
        first = write_versions(connection, table, rows)
        connection.commit()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT * FROM ' + table + " WHERE symbol='300202'")
        stored = cursor.fetchone()
        self.assertIsNone(stored['share_of_profits_in_associates_and_joint_ventures'])
        self.assertEqual(stored['net_profit'], Decimal('-83984934.88'))
        self.assertEqual(stored['content_hash'], contract.content_hash(table, stored))
        stored['source_metadata'] = json.loads(stored['source_metadata'])
        self.assertTrue(statement_field_issues(table, stored))
        connection.rollback()
        connection.start_transaction()
        second = write_versions(connection, table, rows)
        self.assertEqual(second[0]['id'], first[0]['id'])
        self.assertFalse(second[0].get('updated', False))
        connection.commit()
        cursor.close()
        connection.close()

    def test_version_kind_migration_and_typed_collection(self):
        from saa_collector.services.common.statement_kind_migration import render_packet
        from saa_collector.services.common.statement_version_writer import prepare_version
        table = 'saa_raw_income_statement'
        self.insert(table, 'net_profit', 100, '2013-03-29')
        before = self.query('SELECT id,net_profit,content_hash FROM ' + table).stdout
        packet = render_packet()
        self.query(packet['01-version-kinds.sql'])
        self.assertEqual(before, self.query('SELECT id,net_profit,content_hash FROM ' + table).stdout)
        self.assertEqual(self.query('SELECT version_type FROM ' + table).stdout.strip(), 'LATEST')
        self.query(packet['02-latest-views.sql'])
        connection = self.connection()
        connection.rollback()
        row = dict.fromkeys(contract.financial_fields(table))
        row.update(symbol='600036', report_date=date(2012, 12, 31),
                   disclosure_date=date(2013, 3, 29), provider='tushare',
                   source_metadata={'report_type': '5'}, version_type='ORIGINAL', net_profit=90)
        adjusted = dict(row, version_type='RESTATED', net_profit=110,
                        source_metadata={'report_type': '4'})
        connection.start_transaction()
        result = write_versions(connection, table, [row, adjusted])
        connection.commit()
        self.assertTrue(all(r['created'] for r in result))
        self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table).stdout.strip(), '3')
        self.assertEqual(self.query('SELECT net_profit FROM saa_latest_income_statement').stdout.strip(), '100.00')
        connection.start_transaction()
        self.assertTrue(all(not r['created'] for r in write_versions(connection, table, [row, adjusted])))
        connection.commit()
        self.assertEqual(prepare_version(table, row)['content_hash'], contract.content_hash(table, row))
        self.assertNotEqual(self.query("UPDATE {} SET version_type='INVALID'".format(table), False).returncode, 0)

    def test_inplace_receipt_rejects_new_versions_and_rolls_back_bad_backfill(self):
        from saa_collector.services.common.statement_inplace_migration import (
            backfill_legacy_inplace, verify_inplace,
        )
        table = 'saa_raw_income_statement'
        self.insert(table, 'net_profit', 100, '2013-03-29')
        self.query('ALTER TABLE {} MODIFY content_hash CHAR(64) NULL'.format(table))
        self.query('UPDATE {} SET content_hash=NULL'.format(table))
        receipt = dict(table=table, rows=1, digest='bad-original-digest')
        connection = self.connection()
        connection.rollback()
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            backfill_legacy_inplace(connection, table, receipt)
        self.assertEqual(self.query('SELECT content_hash FROM ' + table).stdout.strip(), 'NULL')
        self.insert(table, 'net_profit', 150, '2014-03-29')
        with self.assertRaisesRegex(ValueError, 'Multiple versions'):
            verify_inplace(connection, table, receipt)

    def test_inplace_packet_phases_and_full_roundtrip(self):
        import importlib.util
        path = Path(__file__).resolve().parents[4] / 'scripts/financial_pit_preflight.py'
        spec = importlib.util.spec_from_file_location('isolated_preflight', path)
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        from saa_collector.services.common.statement_inplace_migration import (
            legacy_receipt, backfill_legacy_inplace,
        )
        ddl = json.loads(Path(__file__).with_name('fixtures').joinpath(
            'financial_raw_legacy_20261031.json').read_text())
        metadata = {'objects': {}}
        receipts = {}
        connection = self.connection()
        connection.rollback()
        for table in self.fields:
            self.query('DROP TABLE ' + table)
            self.query(ddl[table])
            self.query("INSERT INTO {} (symbol,report_date,disclosure_date) "
                       "VALUES ('600036','2012-12-31','2013-03-29')".format(table))
            metadata['objects'][table] = {'columns': [{'Field': c} for c in
                ['symbol', 'report_date', 'disclosure_date', *self.fields[table]]]}
            receipts[table] = legacy_receipt(connection, table)
        original = ('CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW '
                    'saa_financial_statements_combined AS SELECT b.symbol,b.report_date '
                    'FROM saa_raw_balance_sheet b LEFT JOIN saa_raw_income_statement i '
                    'USING(symbol,report_date) LEFT JOIN saa_raw_cash_flow_statement c '
                    'USING(symbol,report_date)')
        metadata['objects'][renderer.VIEWS[0]] = {'create': {'Create View': original}}
        self.query(original)
        before = self.query('SELECT * FROM saa_financial_statements_combined').stdout
        packet = renderer.render_packet(metadata)
        first, last = packet['01-migrate.sql'].split('-- STOP HERE.', 1)
        self.query(first)
        for table in self.fields:
            backfill_legacy_inplace(connection, table, receipts[table])
        self.query('-- STOP HERE.' + last)
        self.assertEqual(before, self.query('SELECT * FROM saa_financial_statements_combined').stdout)
        self.query(packet['02-restore.sql'])
        for table in self.fields:
            self.assertEqual(legacy_receipt(connection, table), receipts[table])
        self.assertEqual(before, self.query('SELECT * FROM saa_financial_statements_combined').stdout)

    def test_inplace_migration_preserves_values_and_restores_legacy_schema(self):
        from saa_collector.services.common.statement_migration_plan import (
            inplace_expand_sql, inplace_finalize_sql, inplace_restore_sql,
        )
        from saa_collector.services.common.statement_inplace_migration import (
            legacy_receipt, backfill_legacy_inplace, verify_inplace,
        )
        ddl = json.loads(Path(__file__).with_name('fixtures').joinpath(
            'financial_raw_legacy_20261031.json').read_text())
        for table in self.fields:
            self.query('DROP TABLE ' + table)
            self.query(ddl[table])
            field = next(iter(self.fields[table]))
            self.query("INSERT INTO {} (symbol,report_date,disclosure_date,{}) "
                       "VALUES ('600036','2012-12-31','2013-03-29',123.45)".format(table, field))
            schema = self.query('SHOW COLUMNS FROM ' + table).stdout
            indexes = self.query('SHOW INDEX FROM ' + table).stdout
            values = self.query('SELECT * FROM ' + table).stdout
            connection = self.connection()
            connection.rollback()
            receipt = legacy_receipt(connection, table)
            self.query(inplace_expand_sql(table))
            self.assertNotEqual(self.query(inplace_finalize_sql(table), False).returncode, 0)
            self.assertEqual(backfill_legacy_inplace(connection, table, receipt), receipt)
            self.assertEqual(backfill_legacy_inplace(connection, table, receipt), receipt)
            self.query(inplace_finalize_sql(table))
            self.assertEqual(verify_inplace(connection, table, receipt), receipt)
            self.query('UPDATE {} SET {}=999'.format(table, field))
            with self.assertRaises(ValueError):
                verify_inplace(connection, table, receipt)
            self.query('UPDATE {} SET {}=123.45'.format(table, field))
            self.query(inplace_restore_sql(table))
            self.assertEqual(schema, self.query('SHOW COLUMNS FROM ' + table).stdout)
            self.assertEqual(values, self.query('SELECT * FROM ' + table).stdout)
            # Cardinality estimates can change after DDL; compare index identity/columns.
            def index_contract(text):
                return sorted(tuple(row.split('\t')[i] for i in (1, 2, 3, 4))
                              for row in text.splitlines())
            self.assertEqual(index_contract(indexes), index_contract(
                self.query('SHOW INDEX FROM ' + table).stdout))

    @classmethod
    def docker(cls, *args, input=None, check=True):
        return subprocess.run(
            ['docker', '--host', 'unix:///var/run/docker.sock', *args],
            input=input, capture_output=True, text=True, timeout=120, check=check,
        )

    @classmethod
    def setUpClass(cls):
        cls.name = 'pit-mysql-test-' + uuid.uuid4().hex[:12]
        # Resolve an already-pulled image; tests never implicitly pull or build.
        cls.image = cls.docker('image', 'inspect', 'mysql:8.0',
                               '--format', '{{.Id}}').stdout.strip()
        cls.socket_dir = tempfile.TemporaryDirectory(prefix='pit-mysql-socket-')
        cls.addClassCleanup(cls.socket_dir.cleanup)
        # MySQL chowns its socket directory. Keep a host-owned parent so
        # cleanup can remove that child without /tmp sticky-bit restrictions.
        cls.socket_path = cls.socket_dir.name + '/socket'
        os.mkdir(cls.socket_path, 0o777)
        os.chmod(cls.socket_path, 0o777)
        cls.addClassCleanup(cls.remove_container)
        cls.docker('run', '--detach', '--pull=never', '--name', cls.name,
                   '--label', 'saa.purpose=isolated-pit-test', '--network', 'none',
                   '--memory', '2g', '--cpus', '2',
                   '--tmpfs', '/var/lib/mysql:rw,size=1g',
                   '--mount', 'type=bind,src={},dst=/test-socket'.format(cls.socket_path),
                   '--env', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes',
                   cls.image, '--skip-networking', '--socket=/test-socket/mysql.sock')
        inspected = json.loads(cls.docker('inspect', cls.name).stdout)[0]
        binds = [(mount['Source'], mount['Destination']) for mount in inspected['Mounts']
                 if mount['Type'] == 'bind']
        if (inspected['HostConfig']['NetworkMode'] != 'none'
                or inspected['HostConfig'].get('PortBindings')
                or binds != [(cls.socket_path, '/test-socket')]):
            raise RuntimeError('Container isolation preflight failed')
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            process = cls.docker('exec', cls.name, 'cat', '/proc/1/comm', check=False)
            probe = cls.docker('exec', cls.name, 'mysql', '--protocol=socket',
                               '--socket=/test-socket/mysql.sock',
                               '-uroot', '-Nse', 'SELECT 1', check=False)
            if probe.returncode == 0 and process.stdout.strip() == 'mysqld':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Isolated MySQL did not become ready')
        cls.fields = json.loads(Path(contract.__file__).with_name(
            'financial_statement_fields.json').read_text())

    @classmethod
    def remove_container(cls):
        # This UUID name belongs only to this test invocation.
        cls.docker('rm', '--force', '--volumes', cls.name, check=False)

    @classmethod
    def sql(cls, statement, check=True):
        return cls.docker('exec', '-i', cls.name, 'mysql', '--protocol=socket',
                          '--socket=/test-socket/mysql.sock',
                          '-uroot', '--batch', '--skip-column-names',
                          input=statement, check=check)

    def connection(self):
        connection = mysql.connector.connect(
            unix_socket=self.socket_path + '/mysql.sock', user='root',
            database='pit_fixture', autocommit=False, connection_timeout=5,
        )
        self.addCleanup(connection.close)
        connection.start_transaction()
        return connection

    def version(self, **changes):
        row = dict.fromkeys(self.fields['saa_raw_income_statement'])
        row.update(symbol='600036', report_date=date(2012, 12, 31),
                   disclosure_date=date(2013, 3, 29), provider='tushare',
                   source_metadata={'endpoint': 'income'}, net_profit=100)
        row.update(changes)
        return row

    def test_writer_repeat_preserves_provenance_and_new_date_creates_version(self):
        table = 'saa_raw_income_statement'
        connection = self.connection()
        first = write_versions(connection, table, [self.version()])[0]
        repeated = write_versions(connection, table, [self.version(provider='akshare')])[0]
        self.assertEqual(repeated, {'id': first['id'], 'created': False})
        revision = write_versions(connection, table, [self.version(
            disclosure_date=date(2014, 3, 29), net_profit=120)])[0]
        self.assertTrue(revision['created'])
        self.assertNotEqual(first['id'], revision['id'])
        self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table).stdout.strip(), '0')
        connection.commit()
        self.assertEqual(self.query('SELECT provider,net_profit FROM ' + table +
                                    ' ORDER BY disclosure_date').stdout.splitlines(),
                         ['tushare\t100.00', 'tushare\t120.00'])

    def test_same_day_update_preserves_other_days_and_can_roll_back(self):
        table = 'saa_raw_income_statement'
        connection = self.connection()
        first = write_versions(connection, table, [self.version()])[0]
        write_versions(connection, table, [self.version(
            disclosure_date=date(2014, 3, 29), net_profit=130)])
        connection.commit()
        updated = self.version(net_profit=120, source_metadata={
            'endpoint': 'income', 'report_type': '1', 'update_flag': '1'})
        connection.start_transaction()
        result = write_versions(connection, table, [updated])[0]
        self.assertEqual(result['id'], first['id'])
        self.assertTrue(result['updated'])
        connection.rollback()
        self.assertEqual(self.query('SELECT net_profit FROM ' + table +
                                    ' ORDER BY disclosure_date').stdout.splitlines(), ['100.00', '130.00'])
        connection.start_transaction()
        write_versions(connection, table, [updated])
        connection.commit()
        self.assertEqual(self.query('SELECT net_profit FROM ' + table +
                                    ' ORDER BY disclosure_date').stdout.splitlines(), ['120.00', '130.00'])
        connection.start_transaction()
        self.assertEqual(write_versions(connection, table, [updated]),
                         [{'id': first['id'], 'created': False}])

    def test_security_master_upsert_disambiguates_target_name(self):
        from saa_collector.services.common.security_master_service import SecurityMasterRefreshService
        self.query('CREATE TABLE saa_stocks (symbol VARCHAR(8), name VARCHAR(30), '
                   'listing_date DATE, delisting_date DATE, type VARCHAR(10), market VARCHAR(4)); '
                   'CREATE TABLE saa_securities (code VARCHAR(8) PRIMARY KEY, display_name VARCHAR(30), '
                   'name VARCHAR(30), start_date DATE, end_date DATE, type VARCHAR(10)); '
                   "INSERT INTO saa_stocks VALUES ('600036','New name','2002-01-01',NULL,'STOCK','A'); "
                   "INSERT INTO saa_securities VALUES ('600036','Old display','Keep name','2001-01-01',NULL,'stock');")
        connection = self.connection()
        with patch('saa_collector.services.common.security_master_service.ConfigService'):
            SecurityMasterRefreshService().refresh_from_stocks(connection)
        self.assertEqual(self.query('SELECT display_name,name,start_date FROM saa_securities').stdout.strip(),
                         'New name\tKeep name\t2002-01-01')

    def test_three_table_ingestion_failure_rolls_back_all_tables(self):
        connection = self.connection()
        write_versions(connection, 'saa_raw_income_statement', [self.version()])
        connection.commit()
        bundle = {}
        for table, fields in self.fields.items():
            row = dict.fromkeys(fields)
            row.update(symbol='600036', report_date=date(2012, 12, 31),
                       disclosure_date=date(2013, 3, 29), provider='tushare')
            if table == 'saa_raw_income_statement':
                row['net_profit'] = 120
            bundle[table] = [row]
        with patch('saa_collector.services.common.statement_ingestion.mysql.connector.connect',
                   return_value=connection), self.assertRaises(StatementVersionConflict):
            save_version_bundle({}, bundle)
        for table in self.fields:
            expected = '1' if table == 'saa_raw_income_statement' else '0'
            self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table).stdout.strip(), expected)

    def test_cross_disclosure_omission_preserves_old_snapshot_without_inheritance(self):
        connection = self.connection()
        write_versions(connection, 'saa_raw_income_statement',
                       [self.version(subsidy_income=12)])
        connection.commit()
        bundle = {}
        for table, fields in self.fields.items():
            row = dict.fromkeys(fields)
            row.update(symbol='600036', report_date=date(2012, 12, 31),
                       disclosure_date=date(2014, 3, 29), provider='tushare')
            if table == 'saa_raw_income_statement':
                row['source_metadata'] = {'omitted_fields': ['subsidy_income']}
            bundle[table] = [row]
        with patch('saa_collector.services.common.statement_ingestion.mysql.connector.connect',
                   return_value=connection):
            save_version_bundle({}, bundle)
        for table in self.fields:
            expected = '2' if table == 'saa_raw_income_statement' else '1'
            self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table).stdout.strip(), expected)
        self.assertEqual(self.query('SELECT subsidy_income FROM saa_raw_income_statement '
                                    'ORDER BY disclosure_date').stdout.splitlines(), ['12.00', 'NULL'])

    def test_snapshot_omission_clears_same_day_and_preserves_other_days(self):
        table = 'saa_raw_income_statement'
        connection = self.connection()
        original = self.version(subsidy_income=12)
        revision = self.version(disclosure_date=date(2014, 3, 29),
                                source_metadata={'omitted_fields': ['subsidy_income']})
        write_versions(connection, table, [revision, original])
        connection.commit()
        self.assertEqual(self.query('SELECT subsidy_income FROM ' + table +
                                    ' ORDER BY disclosure_date').stdout.splitlines(), ['12.00', 'NULL'])
        connection.start_transaction()
        replacement = self.version(source_metadata={'endpoint': 'income', 'report_type': '1',
                                                     'update_flag': '0',
                                                     'omitted_fields': ['subsidy_income']})
        self.assertTrue(write_versions(connection, table, [replacement])[0]['updated'])
        connection.rollback()
        self.assertEqual(self.query('SELECT subsidy_income FROM ' + table +
                                    ' ORDER BY disclosure_date').stdout.splitlines(), ['12.00', 'NULL'])
        connection.start_transaction()
        write_versions(connection, table, [replacement])
        connection.commit()
        self.assertEqual(self.query('SELECT subsidy_income FROM ' + table +
                                    ' ORDER BY disclosure_date').stdout.splitlines(), ['NULL', 'NULL'])

    def create_cache_fixture(self):
        definitions = []
        for field in CACHE_COLUMNS:
            if field in {'report_date', 'disclosure_date'}:
                sql_type = 'DATE'
            elif field in {'symbol', 'name', 'market', 'exchange', 'board',
                           'industry_classification_id', 'industry_classification_name'}:
                sql_type = 'VARCHAR(100)'
            else:
                sql_type = 'DECIMAL(18,2)'
            definitions.append('`{}` {}'.format(field, sql_type))
        for table in ('cache_source', 'saa_integrated_reports_cache', 'saa_ttm_reports_cache'):
            primary = 'symbol' if table == 'saa_ttm_reports_cache' else 'symbol,report_date'
            self.query('CREATE TABLE {} ({}, PRIMARY KEY({})) ENGINE=InnoDB'.format(
                table, ','.join(definitions), primary))
        for table in ('saa_integrated_reports_cache', 'saa_ttm_reports_cache'):
            self.query('ALTER TABLE {} MODIFY `exchange` VARCHAR(2)'.format(table))
        projected = ','.join('`{}`'.format(c) for c in CACHE_COLUMNS
                             if c not in {'report_date', 'disclosure_date'})
        self.query('CREATE VIEW saa_integrated_reports_impl AS SELECT {},report_date AS `date` '
                   'FROM cache_source'.format(projected))
        self.query('CREATE VIEW saa_financial_statements_combined AS SELECT '
                   'symbol,report_date,disclosure_date FROM cache_source')
        self.query('CREATE VIEW saa_ttm_reports_interface AS SELECT * FROM saa_ttm_reports_cache')
        self.query('CREATE TABLE saa_dividends '
                   '(symbol VARCHAR(8),`date` DATE,dividend DECIMAL(18,2)) ENGINE=InnoDB')
        # Reproduce the production view and its strict-mode query failure.
        self.query("CREATE VIEW saa_yearly_dividend_impl AS SELECT symbol,"
                   "STR_TO_DATE(CONCAT(YEAR(`date`),'-12-31'),'%Y-%m-%d') AS `date`,"
                   "SUM(dividend) AS dividend FROM saa_dividends GROUP BY symbol,YEAR(`date`)")
        year = date.today().year - 1
        for table, value in [('cache_source', 120), ('saa_integrated_reports_cache', 100),
                             ('saa_ttm_reports_cache', 100)]:
            self.query("INSERT INTO {} (symbol,report_date,disclosure_date,net_profit) "
                       "VALUES ('600036','{}-12-31','{}-03-29',{})".format(table, year, year + 1, value))
        self.query("UPDATE cache_source SET `exchange`='SSE'")

    def test_cache_publication_retains_absent_old_period_and_reports_it(self):
        self.create_cache_fixture()
        self.query("INSERT INTO saa_integrated_reports_cache (symbol,report_date,net_profit) "
                   "VALUES ('600036','2006-12-31',0)")
        connection = self.connection()
        connection.rollback()
        result = publish_statement_caches(connection, object.__new__(StatementMaintainService), '600036')
        self.assertEqual(self.query("SELECT net_profit FROM saa_integrated_reports_cache "
                                    "WHERE report_date='2006-12-31'").stdout.strip(), '0.00')
        self.assertEqual(result['issues'][0]['action'], 'RETAIN_EXISTING_CONTINUE')
        self.assertEqual(result['issues'][0]['report_date'], '2006-12-31')
        self.assertEqual(self.query('SELECT net_profit FROM saa_ttm_reports_cache').stdout.strip(), '120.00')
        connection.close()

    def test_nonquarter_raw_record_survives_write_and_hash_validation(self):
        from saa_collector.services.common.statement_kind_migration import render_packet
        table = 'saa_raw_income_statement'
        self.query(render_packet()['01-version-kinds.sql'])
        row = self.version(report_date=date(2019, 8, 31),disclosure_date=date(2020, 1, 3))
        row['version_type'] = 'LATEST'
        connection = self.connection()
        connection.rollback()
        connection.start_transaction()
        write_versions(connection, table, [row])
        connection.commit()
        self.assertEqual(self.query('SELECT report_date FROM '+table).stdout.strip(), '2019-08-31')
        connection.close()

    def test_publisher_yearly_dividends_under_strict_group_by(self):
        self.create_cache_fixture()
        year = date.today().year - 1
        self.query("INSERT INTO saa_dividends VALUES "
                   "('600036','{0}-06-30',1.25),('600036','{0}-12-31',2.50),"
                   "('600519','{0}-12-31',99)".format(year))
        connection = self.connection()
        cursor = connection.cursor()
        cursor.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY'")
        cursor.close()
        connection.rollback()
        publish_statement_caches(connection, object.__new__(StatementMaintainService), '600036')
        for table in ('saa_integrated_reports_cache', 'saa_ttm_reports_cache'):
            self.assertEqual(self.query('SELECT dividend FROM ' + table).stdout.strip(), '3.75')
            self.assertEqual(self.query('SELECT `exchange` FROM ' + table).stdout.strip(), 'SS')

    def test_real_publisher_rolls_back_second_write_then_publishes_both(self):
        self.create_cache_fixture()
        self.query("CREATE TRIGGER fail_ttm BEFORE UPDATE ON saa_ttm_reports_cache FOR EACH ROW "
                   "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='injected TTM failure'")
        connection = self.connection()
        connection.rollback()
        service = object.__new__(StatementMaintainService)
        with self.assertRaises(mysql.connector.Error):
            publish_statement_caches(connection, service, '600036')
        for table in ('saa_integrated_reports_cache', 'saa_ttm_reports_cache'):
            self.assertEqual(self.query('SELECT net_profit FROM ' + table).stdout.strip(), '100.00')
        self.query('DROP TRIGGER fail_ttm')
        result = publish_statement_caches(connection, service, '600036')
        self.assertEqual(result['ttm_rows'], 1)
        for table in ('saa_integrated_reports_cache', 'saa_ttm_reports_cache'):
            self.assertEqual(self.query('SELECT net_profit FROM ' + table).stdout.strip(), '120.00')

    def test_waiting_publisher_reads_snapshot_after_writer_releases_lock(self):
        self.create_cache_fixture()
        writer = self.connection()
        writer.rollback()
        waiting = Event()

        def publish():
            connection = mysql.connector.connect(
                unix_socket=self.socket_path + '/mysql.sock', user='root',
                database='pit_fixture', autocommit=False, connection_timeout=5)
            try:
                waiting.set()
                return publish_statement_caches(
                    connection, object.__new__(StatementMaintainService), '600036')
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with statement_locks(writer, ['600036']):
                future = executor.submit(publish)
                self.assertTrue(waiting.wait(2))
                writer.start_transaction()
                cursor = writer.cursor()
                try:
                    cursor.execute('UPDATE cache_source SET net_profit=180 WHERE symbol=%s', ('600036',))
                    writer.commit()
                finally:
                    cursor.close()
                self.assertFalse(future.done())
            self.assertEqual(future.result(timeout=10)['ttm_rows'], 1)
        for table in ('saa_integrated_reports_cache', 'saa_ttm_reports_cache'):
            self.assertEqual(self.query('SELECT net_profit FROM ' + table).stdout.strip(), '180.00')

    def test_writer_conflict_allows_caller_to_roll_back_entire_batch(self):
        table = 'saa_raw_income_statement'
        connection = self.connection()
        write_versions(connection, table, [self.version()])
        connection.commit()
        connection.start_transaction()
        with self.assertRaises(StatementVersionConflict):
            write_versions(connection, table, [self.version(symbol='000001'),
                                               self.version(net_profit=120)])
        connection.rollback()
        self.assertEqual(self.query('SELECT symbol,net_profit FROM ' + table).stdout.strip(),
                         '600036\t100.00')

    def test_writer_concurrent_duplicate_uses_current_read(self):
        table = 'saa_raw_income_statement'
        for changed in (False, True):
            with self.subTest(conflicting=changed):
                self.query('DELETE FROM ' + table)
                first = self.connection()
                inserted = write_versions(first, table, [self.version()])[0]
                ready = Event()

                def competing_write():
                    connection = mysql.connector.connect(
                        unix_socket=self.socket_path + '/mysql.sock', user='root',
                        database='pit_fixture', autocommit=False, connection_timeout=5,
                    )
                    try:
                        connection.start_transaction(isolation_level='REPEATABLE READ')
                        cursor = connection.cursor()
                        cursor.execute('SET SESSION innodb_lock_wait_timeout=5')
                        # Establish an older read view before the other commit.
                        cursor.execute('SELECT COUNT(*) FROM ' + table)
                        self.assertEqual(cursor.fetchone()[0], 0)
                        cursor.close()
                        ready.set()
                        result = write_versions(connection, table, [self.version(
                            net_profit=120 if changed else 100)])
                        connection.commit()
                        return result
                    finally:
                        connection.rollback()
                        connection.close()

                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(competing_write)
                    try:
                        self.assertTrue(ready.wait(5))
                    finally:
                        first.commit()
                    if changed:
                        with self.assertRaises(StatementVersionConflict):
                            future.result(timeout=10)
                    else:
                        self.assertEqual(future.result(timeout=10),
                                         [{'id': inserted['id'], 'created': False}])
                self.assertEqual(self.query('SELECT net_profit FROM ' + table).stdout.strip(),
                                 '100.00')

    def test_shadow_migration_preserves_legacy_values_and_latest_contract(self):
        for table, fields in self.fields.items():
            with self.subTest(table=table):
                self.query('DROP TABLE ' + table)
                financial = ','.join('`{}` {} NULL'.format(name, kind)
                                     for name, kind in fields.items())
                self.query('CREATE TABLE `{}` (symbol VARCHAR(8) NOT NULL, '
                           'report_date DATE NOT NULL, disclosure_date DATE NULL, {}, '
                           'PRIMARY KEY(symbol,report_date), '
                           'KEY ix_disclosure(disclosure_date)) ENGINE=InnoDB'.format(table, financial))
                field = next(iter(fields))
                self.query("INSERT INTO {} (symbol,report_date,disclosure_date,{}) VALUES "
                           "('600036','2012-12-31','2013-03-29',100),"
                           "('000001','2012-12-31','2013-04-01',-12.34)".format(table, field))
                columns = ['symbol', 'report_date', 'disclosure_date', *fields]
                before = self.query('SELECT * FROM ' + table + ' ORDER BY symbol').stdout
                old_connection = self.connection()
                old_cursor = old_connection.cursor()
                assert_legacy_write_allowed(old_cursor, table)
                old_cursor.close()
                old_connection.rollback()
                for sql in shadow_statements(table, columns):
                    self.query(sql)
                copy_connection = self.connection()
                copy_connection.rollback()
                manifest = copy_legacy_to_shadow(copy_connection, table, batch_size=1)
                self.assertEqual(manifest['rows'], 2)
                self.assertEqual(manifest['source_digest'], manifest['shadow_digest'])
                with self.assertRaisesRegex(ValueError, 'not empty'):
                    copy_legacy_to_shadow(copy_connection, table, batch_size=1)
                connection = self.connection()
                cursor = connection.cursor(dictionary=True)
                cursor.execute('SELECT * FROM ' + table + ' ORDER BY symbol')
                originals = cursor.fetchall()
                connection.commit()
                cursor.close()
                self.assertEqual(before, self.query('SELECT * FROM ' + table + ' ORDER BY symbol').stdout)
                selected = ','.join('`{}`'.format(name) for name in columns)
                self.assertEqual(before, self.query('SELECT ' + selected + ' FROM ' + table +
                                                   '_pit_shadow ORDER BY symbol').stdout)
                # Rehearse cutover only inside this synthetic, isolated schema.
                self.query('RENAME TABLE {0} TO {0}_legacy, {0}_pit_shadow TO {0}'.format(table))
                with self.assertRaisesRegex(ValueError, 'version'):
                    DB().to_sql([dict(originals[0])], connection, table,
                                ['symbol', 'report_date'])
                connection.rollback()
                self.query(contract.latest_view_sql(table, columns))
                view = table.replace('saa_raw_', 'saa_latest_', 1)
                self.assertEqual(before, self.query('SELECT * FROM ' + view + ' ORDER BY symbol').stdout)
                connection.start_transaction()
                revision = dict(originals[1], disclosure_date=date(2014, 3, 29),
                                provider='tushare', source_metadata=None)
                revision[field] = 120
                write_versions(connection, table, [revision])
                connection.commit()
                self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table).stdout.strip(), '3')
                self.assertEqual(self.query('SELECT COUNT(*) FROM ' + view).stdout.strip(), '2')
                self.assertEqual(before, self.query('SELECT * FROM ' + table + '_legacy ORDER BY symbol').stdout)

    def test_shadow_copy_rolls_back_prior_batches_on_invalid_date(self):
        table = 'saa_raw_income_statement'
        self.query('ALTER TABLE {} DROP PRIMARY KEY, DROP INDEX uq_statement_disclosure, '
                   'DROP COLUMN id, DROP COLUMN provider, DROP COLUMN source_metadata, '
                   'DROP COLUMN content_hash, MODIFY disclosure_date DATE NULL, '
                   'ADD PRIMARY KEY(symbol,report_date)'.format(table))
        self.query("INSERT INTO {} (symbol,report_date,disclosure_date,net_profit) VALUES "
                   "('000001','2023-12-31','2024-03-29',100),"
                   "('000002','2023-12-31',NULL,200)".format(table))
        columns = ['symbol', 'report_date', 'disclosure_date', *self.fields[table]]
        for sql in shadow_statements(table, columns):
            self.query(sql)
        connection = self.connection()
        connection.rollback()
        with self.assertRaises(ValueError):
            copy_legacy_to_shadow(connection, table, batch_size=1)
        self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table).stdout.strip(), '2')
        self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table + '_pit_shadow').stdout.strip(), '0')

    def test_captured_production_ddl_shadow_copy_preserves_indexes_and_values(self):
        definitions = json.loads(Path(__file__).with_name('fixtures').joinpath(
            'financial_raw_legacy_20261031.json').read_text())
        for table, ddl in definitions.items():
            self.query('DROP TABLE ' + table)
            self.query(ddl)
            field = next(iter(self.fields[table]))
            self.query("INSERT INTO {} (symbol,report_date,disclosure_date,{}) VALUES "
                       "('600036','2023-12-31','2024-03-29',123.45)".format(table, field))
            columns = ['symbol', 'report_date', 'disclosure_date', *self.fields[table]]
            for sql in shadow_statements(table, columns):
                self.query(sql)
            connection = self.connection()
            connection.rollback()
            receipt = copy_legacy_to_shadow(connection, table, batch_size=1)
            self.assertEqual(receipt['rows'], 1)
            self.assertEqual(verify_legacy_shadow(connection, table, receipt), receipt)
            index_query = ("SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME,NON_UNIQUE "
                           "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='pit_fixture' "
                           "AND TABLE_NAME='{}' AND INDEX_NAME NOT IN ('PRIMARY','uq_statement_disclosure') "
                           "ORDER BY INDEX_NAME,SEQ_IN_INDEX")
            self.assertEqual(self.query(index_query.format(table)).stdout,
                             self.query(index_query.format(table + '_pit_shadow')).stdout)

    def test_precutover_verification_detects_changes_since_copy(self):
        table = 'saa_raw_income_statement'
        self.query('ALTER TABLE {} DROP PRIMARY KEY, DROP INDEX uq_statement_disclosure, '
                   'DROP COLUMN id, DROP COLUMN provider, DROP COLUMN source_metadata, '
                   'DROP COLUMN content_hash, MODIFY disclosure_date DATE NULL, '
                   'ADD PRIMARY KEY(symbol,report_date)'.format(table))
        self.query("INSERT INTO {} (symbol,report_date,disclosure_date,net_profit) VALUES "
                   "('600036','2023-12-31','2024-03-29',100)".format(table))
        for sql in shadow_statements(table, ['symbol', 'report_date', 'disclosure_date', *self.fields[table]]):
            self.query(sql)
        connection = self.connection()
        connection.rollback()
        receipt = copy_legacy_to_shadow(connection, table)
        self.assertEqual(verify_legacy_shadow(connection, table, receipt), receipt)
        self.query('UPDATE {} SET net_profit=200'.format(table))
        with self.assertRaisesRegex(ValueError, 'changed|mismatch'):
            verify_legacy_shadow(connection, table, receipt)
        self.query('UPDATE {} SET net_profit=100'.format(table))
        self.query('UPDATE {}_pit_shadow SET net_profit=200'.format(table))
        with self.assertRaisesRegex(ValueError, 'changed|mismatch'):
            verify_legacy_shadow(connection, table, receipt)
        self.query('UPDATE {}_pit_shadow SET net_profit=100'.format(table))
        self.assertEqual(verify_legacy_shadow(connection, table, receipt), receipt)

    def test_three_table_cutover_and_pre_ingestion_restore_preserve_values(self):
        before = {}
        for table, fields in self.fields.items():
            self.query('ALTER TABLE {} DROP PRIMARY KEY, DROP INDEX uq_statement_disclosure, '
                       'DROP COLUMN id, DROP COLUMN provider, DROP COLUMN source_metadata, '
                       'DROP COLUMN content_hash, MODIFY disclosure_date DATE NULL, '
                       'ADD PRIMARY KEY(symbol,report_date)'.format(table))
            field = next(iter(fields))
            self.query("INSERT INTO {} (symbol,report_date,disclosure_date,{}) VALUES "
                       "('600036','2012-12-31','2013-03-29',123.45)".format(table, field))
            before[table] = self.query('SELECT * FROM ' + table).stdout
            columns = ['symbol', 'report_date', 'disclosure_date', *fields]
            for sql in shadow_statements(table, columns):
                self.query(sql)
            connection = self.connection()
            connection.rollback()
            copy_legacy_to_shadow(connection, table)
        self.query(cutover_rename_sql('fixture'))
        for table, fields in self.fields.items():
            self.query(contract.latest_view_sql(table, ['symbol', 'report_date', 'disclosure_date', *fields]))
            view = table.replace('saa_raw_', 'saa_latest_', 1)
            self.assertEqual(self.query('SELECT * FROM ' + view).stdout, before[table])
            self.assertEqual(self.query('SELECT * FROM ' + table + '_legacy_fixture').stdout, before[table])
        # Only valid before any new version writes: retain migrated tables too.
        for table in self.fields:
            self.query('DROP VIEW ' + table.replace('saa_raw_', 'saa_latest_', 1))
        self.query(pre_ingestion_restore_sql('fixture'))
        for table in self.fields:
            self.assertEqual(self.query('SELECT * FROM ' + table).stdout, before[table])
            self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table + '_pit_retained_fixture').stdout.strip(), '1')

    def test_combined_cutover_keeps_definer_security_and_columns(self):
        for table, fields in self.fields.items():
            self.insert(table, next(iter(fields)), 100, '2013-03-29')
            self.query(contract.latest_view_sql(table, ['symbol', 'report_date', 'disclosure_date', *fields]))
        self.query('CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER '
                   'VIEW saa_financial_statements_combined AS '
                   'SELECT b.symbol,b.report_date,b.disclosure_date '
                   'FROM saa_raw_balance_sheet b '
                   'LEFT JOIN saa_raw_income_statement i USING(symbol,report_date) '
                   'LEFT JOIN saa_raw_cash_flow_statement c USING(symbol,report_date)')
        connection = self.connection()
        connection.rollback()
        cursor = connection.cursor()
        try:
            cursor.execute('SHOW CREATE VIEW saa_financial_statements_combined')
            original = cursor.fetchone()[1]
        finally:
            cursor.close()
        security = self.query("SELECT DEFINER,SECURITY_TYPE FROM information_schema.VIEWS "
                              "WHERE TABLE_SCHEMA='pit_fixture' AND TABLE_NAME='saa_financial_statements_combined'").stdout
        columns = self.query('SHOW COLUMNS FROM saa_financial_statements_combined').stdout
        values = self.query('SELECT * FROM saa_financial_statements_combined').stdout
        self.query(combined_view_cutover_sql(original))
        self.assertEqual(columns, self.query('SHOW COLUMNS FROM saa_financial_statements_combined').stdout)
        self.assertEqual(values, self.query('SELECT * FROM saa_financial_statements_combined').stdout)
        self.assertEqual(security, self.query("SELECT DEFINER,SECURITY_TYPE FROM information_schema.VIEWS "
                                              "WHERE TABLE_SCHEMA='pit_fixture' AND TABLE_NAME='saa_financial_statements_combined'").stdout)

    def test_result_json_default_allows_old_worker_inserts(self):
        import importlib
        from unittest.mock import Mock
        migration = importlib.import_module('saa_collector.migrations.0005_collect_job_result')
        self.query('CREATE TABLE collector_collect_job (id BIGINT PRIMARY KEY, '
                   'result JSON NOT NULL) ENGINE=InnoDB')
        apps, editor = Mock(), Mock()
        apps.get_model.return_value._meta.db_table = 'collector_collect_job'
        editor.connection.vendor = 'mysql'
        editor.quote_name.side_effect = lambda name: '`' + name + '`'
        editor.execute.side_effect = self.query
        migration.preserve_mysql_insert_default(apps, editor)
        self.query('INSERT INTO collector_collect_job (id) VALUES (1)')
        self.assertEqual(self.query('SELECT result FROM collector_collect_job').stdout.strip(), '{}')

    def test_real_django_upgrade_from_0003_preserves_jobs_and_schedule_dates(self):
        # A fresh process owns explicit isolated settings; never import the
        # application's development/production database configuration.
        code = '''
import sys
from django.conf import settings
settings.configure(SECRET_KEY="isolated", USE_TZ=True,
    INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "saa_collector"],
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    DATABASES={"default": {"ENGINE": "mysql.connector.django", "NAME": "pit_fixture",
        "USER": "root", "PASSWORD": "", "HOST": "", "PORT": "",
        "OPTIONS": {"unix_socket": sys.argv[1]}}})
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
old_target = [("saa_collector", "0003_external_api_cache_raw_response_body")]
executor = MigrationExecutor(connection)
executor.migrate(old_target)
old_apps = executor.loader.project_state(old_target).apps
OldJob = old_apps.get_model("saa_collector", "CollectJob")
OldSchedule = old_apps.get_model("saa_collector", "CollectSchedule")
job = OldJob.objects.create(data_type="income", message="preserved")
schedule = OldSchedule.objects.create(name="isolated", data_type="financial_statements",
    cron_expression="0 0 * * *", params={"date_start": "T-1", "date_end": "T"})
new_target = [("saa_collector", "0005_collect_job_result")]
executor = MigrationExecutor(connection)
executor.migrate(new_target)
new_apps = executor.loader.project_state(new_target).apps
Job = new_apps.get_model("saa_collector", "CollectJob")
Schedule = new_apps.get_model("saa_collector", "CollectSchedule")
assert Job.objects.get(pk=job.pk).result == {}
assert Job.objects.get(pk=job.pk).message == "preserved"
assert Schedule.objects.get(pk=schedule.pk).params == {"start_date": "T-1", "end_date": "T"}
old_worker_job = OldJob.objects.create(data_type="income", message="old worker")
assert Job.objects.get(pk=old_worker_job.pk).result == {}
Job.objects.filter(pk=job.pk).update(result={"schema_version": 1})
assert Job.objects.get(pk=job.pk).result == {"schema_version": 1}
connection.close()
print("Django 0003 -> 0005 migration and legacy inserts verified")
'''
        result = subprocess.run([sys.executable, '-c', code, self.socket_path + '/mysql.sock'],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def setUp(self):
        self.sql('DROP DATABASE IF EXISTS pit_fixture; CREATE DATABASE pit_fixture;')
        for table, fields in self.fields.items():
            financial = ', '.join('`{}` {} NULL'.format(name, kind)
                                  for name, kind in fields.items())
            self.query('CREATE TABLE `{}` (id BIGINT AUTO_INCREMENT PRIMARY KEY, '
                       'symbol VARCHAR(8) NOT NULL, report_date DATE NOT NULL, '
                       'disclosure_date DATE NOT NULL, provider VARCHAR(32) NOT NULL, '
                       'source_metadata JSON NULL, content_hash CHAR(64) NOT NULL, {}, '
                       'UNIQUE KEY uq_statement_disclosure '
                       '(symbol,report_date,disclosure_date)) ENGINE=InnoDB'.format(table, financial))

    def query(self, sql, check=True):
        return self.sql("USE pit_fixture; SET SESSION sql_mode="
                        "'STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE'; " + sql, check)

    def insert(self, table, field, value, disclosure, period='2012-12-31'):
        from datetime import date
        row = {key: None for key in self.fields[table]}
        row.update(symbol='600036', report_date=date.fromisoformat(period),
                   disclosure_date=date.fromisoformat(disclosure))
        row[field] = value
        fingerprint = contract.content_hash(table, row)
        self.query("INSERT INTO {} (symbol,report_date,disclosure_date,provider,content_hash,{}) "
                   "VALUES ('600036','{}','{}','unknown','{}',{})".format(
                       table, field, period, disclosure, fingerprint, value))

    def test_latest_views_preserve_columns_and_join_cardinality(self):
        for index, (table, fields) in enumerate(self.fields.items()):
            field = next(iter(fields))
            self.insert(table, field, 100, '2013-03-29')
            self.insert(table, field, 120, '2014-03-{:02}'.format(27 + index))
            self.insert(table, field, 150, '2014-04-01', period='2013-12-31')
            columns = ['symbol', 'report_date', 'disclosure_date', *fields]
            self.query(contract.latest_view_sql(table, columns))
            view = table.replace('saa_raw_', 'saa_latest_', 1)
            self.assertEqual(self.query('SELECT {} FROM {} ORDER BY report_date'.format(
                field, view)).stdout.splitlines(), ['120.00', '150.00'])
            actual = self.query('SHOW COLUMNS FROM ' + view).stdout.splitlines()
            self.assertEqual([line.split('\t')[0] for line in actual], columns)
        self.assertEqual(self.query('SELECT COUNT(*) FROM saa_latest_balance_sheet b '
                                    'LEFT JOIN saa_latest_income_statement i USING(symbol,report_date) '
                                    'LEFT JOIN saa_latest_cash_flow_statement c USING(symbol,report_date)').stdout.strip(), '2')

    def test_production_combined_definition_preserves_values_and_prevents_fanout(self):
        import sqlparse
        from sqlparse.tokens import Name
        definition = Path(__file__).with_name('fixtures').joinpath(
            'financial_combined_legacy.sql').read_text().strip()
        # Only relocate schema identifiers into the disposable fixture schema.
        parsed = sqlparse.parse(definition)[0]
        definition = ''.join('`pit_fixture`' if token.ttype in Name and token.value == '`saa`'
                             else token.value for token in parsed.flatten())
        for table, fields in self.fields.items():
            self.insert(table, next(iter(fields)), 100, '2013-03-29')
            self.insert(table, next(iter(fields)), 150, '2014-04-01', period='2013-12-31')
            self.query(contract.latest_view_sql(table, ['symbol', 'report_date',
                                                       'disclosure_date', *fields]))
        self.query('CREATE VIEW combined_fixture AS ' + definition)
        signature = self.query('SHOW COLUMNS FROM combined_fixture').stdout
        before = self.query('SELECT * FROM combined_fixture ORDER BY report_date').stdout
        self.query('CREATE OR REPLACE VIEW combined_fixture AS ' + latest_combined_definition(definition))
        self.assertEqual(signature, self.query('SHOW COLUMNS FROM combined_fixture').stdout)
        self.assertEqual(before, self.query('SELECT * FROM combined_fixture ORDER BY report_date').stdout)
        for index, (table, fields) in enumerate(self.fields.items()):
            self.insert(table, next(iter(fields)), 120, '2014-03-{:02}'.format(27 + index))
        self.assertEqual(self.query('SELECT COUNT(*) FROM combined_fixture').stdout.strip(), '2')
        self.assertEqual(self.query("SELECT disclosure_date FROM combined_fixture "
                                    "WHERE report_date='2012-12-31'").stdout.strip(), '2014-03-29')
        # Recovery of the compatible view preserves every newly stored version.
        self.query('DROP VIEW combined_fixture')
        self.query('CREATE VIEW combined_fixture AS ' + latest_combined_definition(definition))
        self.assertEqual(self.query('SELECT COUNT(*) FROM combined_fixture').stdout.strip(), '2')
        for table in self.fields:
            self.assertEqual(self.query('SELECT COUNT(*) FROM ' + table).stdout.strip(), '3')

    def test_daily_unique_constraint_rejects_duplicate_and_null(self):
        table = 'saa_raw_income_statement'
        self.insert(table, 'net_profit', 100, '2013-03-29')
        duplicate = self.query('INSERT INTO {} (symbol,report_date,disclosure_date,provider,content_hash) '
                               'SELECT symbol,report_date,disclosure_date,provider,content_hash FROM {}'.format(table, table), False)
        self.assertIn('1062', duplicate.stderr)
        missing = self.query("INSERT INTO {} (symbol,report_date,disclosure_date,provider,content_hash) "
                             "VALUES ('A','2012-12-31',NULL,'unknown',REPEAT('a',64))".format(table), False)
        self.assertIn('1048', missing.stderr)
        invalid = self.query("INSERT INTO {} (symbol,report_date,disclosure_date,provider,content_hash) "
                             "VALUES ('A','2012-12-31','0000-00-00','unknown',REPEAT('a',64))".format(table), False)
        self.assertNotEqual(invalid.returncode, 0)

    def test_strict_cutoff_selects_original_then_revision(self):
        table = 'saa_raw_income_statement'
        self.insert(table, 'net_profit', 100, '2013-03-29')
        self.insert(table, 'net_profit', 120, '2014-03-29')
        for cutoff, expected in [('2013-03-29', ''), ('2013-04-01', '100.00'),
                                 ('2014-03-29', '100.00'), ('2014-03-30', '120.00')]:
            result = self.query("SELECT net_profit FROM {} WHERE disclosure_date < '{}' "
                                "ORDER BY disclosure_date DESC LIMIT 1".format(table, cutoff))
            self.assertEqual(result.stdout.strip(), expected)

    def test_mysql_transaction_rolls_back_synthetic_versions(self):
        table = 'saa_raw_income_statement'
        self.insert(table, 'net_profit', 100, '2013-03-29')
        self.query('START TRANSACTION; UPDATE {} SET net_profit=999; ROLLBACK;'.format(table))
        self.assertEqual(self.query('SELECT net_profit FROM ' + table).stdout.strip(), '100.00')

    def test_caller_owned_writes_roll_back_both_synthetic_caches(self):
        for table in ('integrated_fixture', 'ttm_fixture'):
            self.query('CREATE TABLE {} (symbol VARCHAR(8) PRIMARY KEY, '
                       'amount DECIMAL(18,2) NOT NULL) ENGINE=InnoDB'.format(table))
            self.query("INSERT INTO {} VALUES ('A',100)".format(table))
        connection = self.connection()
        writer = DB()
        writer.to_sql([dict(symbol='A', amount=120)], connection,
                      'integrated_fixture', 'symbol', commit=False)
        with self.assertRaises(mysql.connector.Error):
            writer.to_sql([dict(symbol='A', amount=None)], connection,
                          'ttm_fixture', 'symbol', commit=False)
        # Independent readers must still see the last committed batch.
        for table in ('integrated_fixture', 'ttm_fixture'):
            self.assertEqual(self.query('SELECT amount FROM ' + table).stdout.strip(), '100.00')
        connection.rollback()
        for table in ('integrated_fixture', 'ttm_fixture'):
            self.assertEqual(self.query('SELECT amount FROM ' + table).stdout.strip(), '100.00')
        connection.start_transaction()
        for table in ('integrated_fixture', 'ttm_fixture'):
            writer.to_sql([dict(symbol='A', amount=120)], connection,
                          table, 'symbol', commit=False)
        connection.commit()
        for table in ('integrated_fixture', 'ttm_fixture'):
            self.assertEqual(self.query('SELECT amount FROM ' + table).stdout.strip(), '120.00')
