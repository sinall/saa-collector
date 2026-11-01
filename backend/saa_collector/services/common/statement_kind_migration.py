"""Offline typed-version SQL candidates, never production execution.

Requires stopped writers and the reviewed existing daily-key schema. The
caller must capture row/value digests, verify classification evidence, retain
view definers/security/grants, and approve capacity/restore before cutover.
DDL auto-commits: resume by verified phase, not by replaying the whole packet.
"""
from .financial_statement_contract import financial_fields, latest_view_sql
from .statement_migration_plan import TABLES, view_definition_parts


def render_packet(*, show_create_views=None):
    expected_views = {table.replace('saa_raw_', 'saa_latest_', 1) for table in TABLES}
    if show_create_views is not None and set(show_create_views) != expected_views:
        raise ValueError('Capture SHOW CREATE VIEW for all three latest views')
    migration = [
        '-- REVIEW CANDIDATE ONLY. Stop writers; verify backup and old schema first.',
        '-- Each ALTER commits. Do not replay completed phases or collapse the new key.',
    ]
    views = [
        '-- REVIEW CANDIDATE ONLY. Preserve production DEFINER/security/grants before execution.',
        '-- Check LATEST coverage first; do not rebuild website caches in this migration.',
    ]
    for table in TABLES:
        migration.extend([
            '\n-- {}: expand, classify existing rows, then replace the daily key.'.format(table),
            'ALTER TABLE `{}`\n'
            '    ADD COLUMN `version_type` VARCHAR(16) NULL AFTER `disclosure_date`;'.format(table),
            'UPDATE `{}`\n'
            'SET `version_type` = CASE\n'
            "    WHEN provider = 'tushare' AND JSON_UNQUOTE(JSON_EXTRACT(source_metadata, '$.report_type')) = '5' THEN 'ORIGINAL'\n"
            "    WHEN provider = 'tushare' AND JSON_UNQUOTE(JSON_EXTRACT(source_metadata, '$.report_type')) = '4' THEN 'RESTATED'\n"
            "    ELSE 'LATEST'\n"
            'END\nWHERE version_type IS NULL;'.format(table),
            'UPDATE `{}`\n'
            "SET source_metadata = JSON_SET(COALESCE(source_metadata, JSON_OBJECT()),\n"
            "    '$.migration_origin', 'legacy_unclassified')\n"
            "WHERE version_type = 'LATEST'\n"
            "    AND NOT (provider = 'tushare' AND COALESCE(JSON_UNQUOTE(\n"
            "        JSON_EXTRACT(source_metadata, '$.report_type')), '') = '1');".format(table),
            '-- STOP: verify ids/financial values/hashes unchanged and review LATEST coverage.',
            'ALTER TABLE `{}`\n'
            '    MODIFY COLUMN `version_type` VARCHAR(16) NOT NULL,\n'
            '    DROP INDEX `uq_statement_disclosure`,\n'
            '    ADD UNIQUE KEY `uq_statement_version`\n'
            '        (`symbol`, `report_date`, `disclosure_date`, `version_type`),\n'
            "    ADD CONSTRAINT `ck_{}_kind` CHECK\n"
            "        (`version_type` IN ('LATEST', 'ORIGINAL', 'RESTATED'));".format(
                table, table.replace('saa_raw_', '')),
        ])
        sql = latest_view_sql(table, ['symbol', 'report_date', 'disclosure_date',
                                     *financial_fields(table)], versioned=True)
        if show_create_views is not None:
            name = table.replace('saa_raw_', 'saa_latest_', 1)
            header, _ = view_definition_parts(show_create_views[name], name)
            _, body = view_definition_parts(sql, name)
            views.append(header + body + ';')
        else:
            views.append(sql.replace('CREATE VIEW', 'CREATE OR REPLACE VIEW', 1) + ';')
    return {'01-version-kinds.sql': '\n'.join(migration) + '\n',
            '02-latest-views.sql': '\n'.join(views) + '\n'}
