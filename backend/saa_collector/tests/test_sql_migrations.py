from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock

from saa_collector.sql_migrations import (
    apply_sql_migrations,
    build_mysql_connector_config,
    discover_sql_migration_files,
    parse_sql_migration_search,
    split_sql_statements,
    _migration_checksum,
)


class SqlMigrationSearchTest(TestCase):
    def test_parse_sql_migration_search_supports_multiple_directories(self):
        self.assertEqual(
            [
                ('sql/migrations', '*.sql'),
                ('.', 'upgrade_*.sql'),
            ],
            parse_sql_migration_search('sql/migrations:*.sql,.:upgrade_*.sql'),
        )

    def test_discover_sql_migration_files_uses_canonical_dir_and_legacy_fallback(self):
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            canonical_dir = base_dir / 'sql' / 'migrations'
            canonical_dir.mkdir(parents=True)
            (canonical_dir / '20260607_add_users.sql').write_text('SELECT 1;', encoding='utf-8')
            (canonical_dir / '20260608_add_orders.sql').write_text('SELECT 2;', encoding='utf-8')
            (base_dir / 'upgrade_20260609_add_cache.sql').write_text('SELECT 3;', encoding='utf-8')
            (base_dir / 'upgrade_20260610_add_views.sql').write_text('SELECT 4;', encoding='utf-8')
            (base_dir / 'sql' / 'mfactor_derived_views.sql').write_text('SELECT 5;', encoding='utf-8')

            discovered = discover_sql_migration_files(base_dir=base_dir)

            self.assertEqual(
                [
                    'sql/migrations/20260607_add_users.sql',
                    'sql/migrations/20260608_add_orders.sql',
                    'upgrade_20260609_add_cache.sql',
                    'upgrade_20260610_add_views.sql',
                ],
                [path.relative_to(base_dir).as_posix() for path in discovered],
            )

    def test_legacy_root_migrations_use_guarded_reapply_patterns(self):
        backend_dir = Path(__file__).resolve().parents[2]
        migration_names = [
            'upgrade_celery_queue_fields.sql',
            'upgrade_trigger_type.sql',
            'upgrade_saa_stocks_listing_dates.sql',
        ]

        for migration_name in migration_names:
            migration_text = (backend_dir / migration_name).read_text(encoding='utf-8')
            self.assertIn('information_schema.COLUMNS', migration_text)
            self.assertIn('PREPARE', migration_text)
            self.assertIn('DEALLOCATE PREPARE', migration_text)
            self.assertNotIn('\nCOMMENT ', migration_text)

    def test_financial_report_date_migration_covers_statement_tables(self):
        backend_dir = Path(__file__).resolve().parents[2]
        migration_text = (
            backend_dir / 'sql' / 'migrations' / '20260618_refactor_financial_report_dates.sql'
        ).read_text(encoding='utf-8')

        for table_name in [
            'saa_raw_balance_sheet',
            'saa_raw_income_statement',
            'saa_raw_cash_flow_statement',
            'saa_raw_main_business',
        ]:
            self.assertIn(table_name, migration_text)
            self.assertIn(
                f'ALTER TABLE {table_name} CHANGE COLUMN date report_date date NOT NULL',
                migration_text,
            )
            self.assertIn(
                f'ALTER TABLE {table_name} ADD COLUMN disclosure_date date NULL AFTER report_date',
                migration_text,
            )
            self.assertIn(
                f'ALTER TABLE {table_name} ADD PRIMARY KEY',
                migration_text,
            )
            self.assertIn(
                f"DELETE FROM {table_name} WHERE CAST(`date` AS CHAR) = ''0000-00-00''",
                migration_text,
            )

        self.assertIn('INTERVAL 120 DAY', migration_text)
        self.assertIn('INTERVAL 60 DAY', migration_text)
        self.assertIn('INTERVAL 90 DAY', migration_text)
        self.assertIn("index_name = 'PRIMARY'", migration_text)
        self.assertIn('@primary_exists = 0', migration_text)


class SqlMigrationApplyTest(TestCase):
    def test_split_sql_statements_ignores_semicolons_inside_quotes(self):
        self.assertEqual(
            [
                "SELECT 'a;b';",
                'SELECT `semi;colon` FROM t;',
                'SELECT 1',
            ],
            split_sql_statements("SELECT 'a;b'; SELECT `semi;colon` FROM t; SELECT 1"),
        )

    def test_build_mysql_connector_config_maps_standard_database_settings(self):
        config = build_mysql_connector_config(
            {
                'NAME': 'saa',
                'USER': 'collector',
                'PASSWORD': 'secret',
                'HOST': 'db.example.com',
                'PORT': '3307',
                'OPTIONS': {'charset': 'utf8mb4'},
            }
        )

        self.assertEqual(
            {
                'user': 'collector',
                'password': 'secret',
                'host': 'db.example.com',
                'port': 3307,
                'database': 'saa',
                'charset': 'utf8mb4',
            },
            config,
        )

    def test_apply_sql_migrations_executes_files_in_order_and_commits_each_file(self):
        connection = MagicMock()
        ensure_cursor = MagicMock()
        history_cursor = MagicMock()
        history_cursor.fetchall.return_value = []
        first_cursor = MagicMock()
        first_cursor.execute.return_value = []
        second_cursor = MagicMock()
        second_cursor.execute.return_value = []
        connection.cursor.side_effect = [
            ensure_cursor,
            history_cursor,
            first_cursor,
            second_cursor,
        ]

        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            first = base_dir / 'first.sql'
            second = base_dir / 'second.sql'
            first.write_text('CREATE TABLE first_table (id INT);', encoding='utf-8')
            second.write_text('CREATE TABLE second_table (id INT);', encoding='utf-8')

            applied = apply_sql_migrations([first, second], connection=connection, base_dir=base_dir)

        self.assertEqual([first, second], applied)
        self.assertEqual(4, connection.cursor.call_count)
        self.assertEqual(2, first_cursor.execute.call_count)
        self.assertEqual(2, second_cursor.execute.call_count)
        self.assertFalse(first_cursor.execute.call_args_list[0].kwargs)
        self.assertFalse(second_cursor.execute.call_args_list[0].kwargs)
        self.assertIn('INSERT INTO `collector_sql_migrations`', first_cursor.execute.call_args_list[1].args[0])
        self.assertIn('INSERT INTO `collector_sql_migrations`', second_cursor.execute.call_args_list[1].args[0])
        self.assertEqual(
            ('first.sql', _migration_checksum('CREATE TABLE first_table (id INT);')),
            first_cursor.execute.call_args_list[1].args[1],
        )
        self.assertEqual(
            ('second.sql', _migration_checksum('CREATE TABLE second_table (id INT);')),
            second_cursor.execute.call_args_list[1].args[1],
        )
        self.assertEqual(2, connection.commit.call_count)
        self.assertEqual(1, first_cursor.close.call_count)
        self.assertEqual(1, second_cursor.close.call_count)
        connection.close.assert_not_called()

    def test_apply_sql_migrations_drains_select_results_between_statements(self):
        connection = MagicMock()
        ensure_cursor = MagicMock()
        history_cursor = MagicMock()
        history_cursor.fetchall.return_value = []
        migration_cursor = MagicMock()
        migration_cursor.with_rows = True
        migration_cursor.fetchall.return_value = [(1,)]
        migration_cursor.nextset.return_value = None
        connection.cursor.side_effect = [
            ensure_cursor,
            history_cursor,
            migration_cursor,
        ]

        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            migration = base_dir / 'guarded.sql'
            migration.write_text('SELECT 1; SELECT 2;', encoding='utf-8')

            applied = apply_sql_migrations([migration], connection=connection, base_dir=base_dir)

        self.assertEqual([migration], applied)
        self.assertEqual(3, migration_cursor.fetchall.call_count)
        self.assertEqual(3, migration_cursor.nextset.call_count)
        self.assertEqual(3, migration_cursor.execute.call_count)
        connection.commit.assert_called_once()

    def test_apply_sql_migrations_skips_files_already_recorded(self):
        connection = MagicMock()
        ensure_cursor = MagicMock()
        history_cursor = MagicMock()
        first_sql = 'CREATE TABLE first_table (id INT);'
        second_sql = 'CREATE TABLE second_table (id INT);'
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            first = base_dir / 'first.sql'
            second = base_dir / 'second.sql'
            first.write_text(first_sql, encoding='utf-8')
            second.write_text(second_sql, encoding='utf-8')

            history_cursor.fetchall.return_value = [
                ('first.sql', _migration_checksum(first_sql)),
            ]
            second_cursor = MagicMock()
            second_cursor.execute.return_value = []
            connection.cursor.side_effect = [
                ensure_cursor,
                history_cursor,
                second_cursor,
            ]

            applied = apply_sql_migrations([first, second], connection=connection, base_dir=base_dir)

        self.assertEqual([second], applied)
        self.assertEqual(3, connection.cursor.call_count)
        self.assertEqual(2, second_cursor.execute.call_count)
        self.assertIn('INSERT INTO `collector_sql_migrations`', second_cursor.execute.call_args_list[1].args[0])
        self.assertEqual(
            ('second.sql', _migration_checksum(second_sql)),
            second_cursor.execute.call_args_list[1].args[1],
        )
        self.assertEqual(1, connection.commit.call_count)
        self.assertEqual(1, second_cursor.close.call_count)
        connection.close.assert_not_called()
