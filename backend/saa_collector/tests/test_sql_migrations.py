from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock

from saa_collector.sql_migrations import (
    apply_sql_migrations,
    build_mysql_connector_config,
    discover_sql_migration_files,
    parse_sql_migration_search,
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


class SqlMigrationApplyTest(TestCase):
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
        cursor = connection.cursor.return_value
        cursor.execute.return_value = []

        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            first = base_dir / 'first.sql'
            second = base_dir / 'second.sql'
            first.write_text('CREATE TABLE first_table (id INT);', encoding='utf-8')
            second.write_text('CREATE TABLE second_table (id INT);', encoding='utf-8')

            applied = apply_sql_migrations([first, second], connection=connection)

        self.assertEqual([first, second], applied)
        self.assertEqual(2, cursor.execute.call_count)
        self.assertEqual(
            [True, True],
            [call.kwargs.get('multi') for call in cursor.execute.call_args_list],
        )
        self.assertEqual(2, connection.commit.call_count)
        self.assertEqual(2, cursor.close.call_count)
        connection.close.assert_not_called()
