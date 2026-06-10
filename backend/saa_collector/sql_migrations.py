from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

import mysql.connector
from django.conf import settings


DEFAULT_SQL_MIGRATION_SEARCH = 'sql/migrations:*.sql,.:upgrade_*.sql'
SQL_MIGRATION_HISTORY_TABLE = 'collector_sql_migrations'


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


def _migration_key(migration_path: Path, base_dir: Path | None = None) -> str:
    if base_dir is None:
        return migration_path.as_posix()
    try:
        return migration_path.relative_to(base_dir).as_posix()
    except ValueError:
        return migration_path.as_posix()


def _migration_checksum(sql_text: str) -> str:
    return hashlib.sha256(sql_text.encode('utf-8')).hexdigest()


def ensure_sql_migration_history_table(connection) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS `{SQL_MIGRATION_HISTORY_TABLE}` (
                `filename` VARCHAR(255) NOT NULL PRIMARY KEY,
                `checksum` CHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
    finally:
        cursor.close()


def load_applied_sql_migrations(connection) -> dict[str, str]:
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"SELECT `filename`, `checksum` FROM `{SQL_MIGRATION_HISTORY_TABLE}`"
        )
        return {filename: checksum for filename, checksum in cursor.fetchall()}
    finally:
        cursor.close()


def apply_sql_migrations(
    migration_files: Iterable[Path],
    connection=None,
    base_dir: Path | None = None,
) -> list[Path]:
    owned_connection = connection is None
    connection = connection or open_mysql_connection()
    base_path = Path(base_dir or settings.BASE_DIR)
    applied_files: list[Path] = []

    try:
        ensure_sql_migration_history_table(connection)
        applied_migrations = load_applied_sql_migrations(connection)

        for migration_path in migration_files:
            sql_text = migration_path.read_text(encoding='utf-8')
            migration_key = _migration_key(migration_path, base_dir=base_path)
            checksum = _migration_checksum(sql_text)

            if migration_key in applied_migrations:
                if applied_migrations[migration_key] != checksum:
                    raise RuntimeError(
                        f"SQL migration {migration_key} was modified after it was applied."
                    )
                print(f"__sql_migration_skip__ file={migration_path.name} reason=already-applied")
                continue

            print(f"__sql_migration_start__ file={migration_path.name}")
            cursor = connection.cursor()
            try:
                result = cursor.execute(sql_text, multi=True)
                if result is not None:
                    for _ in result:
                        pass
                cursor.execute(
                    f"""
                    INSERT INTO `{SQL_MIGRATION_HISTORY_TABLE}` (`filename`, `checksum`)
                    VALUES (%s, %s)
                    """,
                    (migration_key, checksum),
                )
                connection.commit()
                applied_files.append(migration_path)
                print(f"__sql_migration_done__ file={migration_path.name}")
            finally:
                cursor.close()
    finally:
        if owned_connection:
            connection.close()

    return applied_files
