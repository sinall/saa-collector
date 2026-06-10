from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import mysql.connector
from django.conf import settings


DEFAULT_SQL_MIGRATION_SEARCH = 'sql/migrations:*.sql,.:upgrade_*.sql'


def parse_sql_migration_search(search_spec: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw_item in search_spec.split(','):
        item = raw_item.strip()
        if not item:
            continue
        if ':' in item:
            directory, pattern = item.split(':', 1)
        else:
            directory, pattern = item, '*.sql'
        directory = directory.strip()
        pattern = pattern.strip() or '*.sql'
        if directory:
            pairs.append((directory, pattern))
    return pairs


def discover_sql_migration_files(
    base_dir: Path | None = None,
    search_spec: str | None = None,
) -> list[Path]:
    base_path = Path(base_dir or settings.BASE_DIR)
    resolved_files: list[Path] = []
    seen: set[Path] = set()
    spec = search_spec or os.getenv('SAA_SQL_MIGRATION_SEARCH', DEFAULT_SQL_MIGRATION_SEARCH)

    for directory, pattern in parse_sql_migration_search(spec):
        migration_dir = base_path / directory
        if not migration_dir.exists():
            continue

        for migration_path in sorted(migration_dir.glob(pattern)):
            if not migration_path.is_file():
                continue
            resolved_path = migration_path.resolve()
            if resolved_path in seen:
                continue
            seen.add(resolved_path)
            resolved_files.append(migration_path)

    return resolved_files


def build_mysql_connector_config(database_settings: dict) -> dict:
    options = database_settings.get('OPTIONS') or {}
    connector_config = {
        'user': database_settings.get('USER', ''),
        'password': database_settings.get('PASSWORD', ''),
        'host': database_settings.get('HOST', 'localhost'),
        'port': int(database_settings.get('PORT', 3306)),
        'database': database_settings.get('NAME', ''),
    }

    charset = options.get('charset')
    if charset:
        connector_config['charset'] = charset

    return connector_config


def open_mysql_connection():
    return mysql.connector.connect(**build_mysql_connector_config(settings.DATABASES['default']))


def apply_sql_migrations(
    migration_files: Iterable[Path],
    connection=None,
) -> list[Path]:
    owned_connection = connection is None
    connection = connection or open_mysql_connection()
    applied_files: list[Path] = []

    try:
        for migration_path in migration_files:
            sql_text = migration_path.read_text(encoding='utf-8')
            print(f"__sql_migration_start__ file={migration_path.name}")
            cursor = connection.cursor()
            try:
                result = cursor.execute(sql_text, multi=True)
                if result is not None:
                    for _ in result:
                        pass
                connection.commit()
                applied_files.append(migration_path)
                print(f"__sql_migration_done__ file={migration_path.name}")
            finally:
                cursor.close()
    finally:
        if owned_connection:
            connection.close()

    return applied_files
