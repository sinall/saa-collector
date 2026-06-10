import os

from django.core.management.base import BaseCommand, CommandError

from saa_collector.sql_migrations import (
    apply_sql_migrations,
    discover_sql_migration_files,
)


class Command(BaseCommand):
    help = 'Apply collector-owned SQL migration files in deterministic order.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--search',
            default=os.getenv('SAA_SQL_MIGRATION_SEARCH'),
            help='Comma-separated search spec such as "sql/migrations:*.sql,.:upgrade_*.sql".',
        )

    def handle(self, *args, **options):
        migration_files = discover_sql_migration_files(search_spec=options['search'])
        if not migration_files:
            self.stdout.write('No SQL migrations found.')
            return

        self.stdout.write(
            f"Applying SQL migrations: {', '.join(path.name for path in migration_files)}"
        )

        try:
            applied_files = apply_sql_migrations(migration_files)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f"Applied SQL migrations: {', '.join(path.name for path in applied_files)}"
        )
