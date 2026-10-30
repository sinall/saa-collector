"""Offline migration primitives; no connection, execution or automatic cutover.

Production use requires reviewed source DDL, indexes, stopped writers, backups,
space/lock budgets and consumer cutover. DDL is not transactionally reversible.
CREATE LIKE preserves financial column definitions and secondary indexes; the
caller must reject unreviewed unique keys, triggers and foreign dependencies.
"""
from .financial_statement_contract import financial_fields
from .statement_version_writer import prepare_version
import sqlparse
import re
from sqlparse.sql import Identifier
from sqlparse.tokens import Name, Keyword


TABLES = ('saa_raw_balance_sheet', 'saa_raw_income_statement', 'saa_raw_cash_flow_statement')


def inplace_expand_sql(table):
    """Stopped-writer expansion; hash remains NULL until canonical backfill.

    INPLACE may rebuild InnoDB and consume temporary disk. SHARED permits
    readers, not writers; neither clause promises a lock-free operation.
    """
    financial_fields(table)
    return (
        "ALTER TABLE `{}` DROP PRIMARY KEY, "
        "ADD COLUMN `id` BIGINT NOT NULL AUTO_INCREMENT FIRST, ADD PRIMARY KEY (`id`), "
        "MODIFY COLUMN `disclosure_date` DATE NOT NULL AFTER `report_date`, "
        "ADD COLUMN `provider` VARCHAR(32) NOT NULL DEFAULT 'unknown' AFTER `disclosure_date`, "
        "ADD COLUMN `source_metadata` JSON NULL AFTER `provider`, "
        "ADD COLUMN `content_hash` CHAR(64) NULL AFTER `source_metadata`, "
        "ADD UNIQUE KEY `uq_statement_disclosure` (`symbol`,`report_date`,`disclosure_date`), "
        "ALGORITHM=INPLACE, LOCK=SHARED"
    ).format(table)


def inplace_finalize_sql(table):
    financial_fields(table)
    return ('ALTER TABLE `{}` MODIFY COLUMN `content_hash` CHAR(64) NOT NULL, '
            'ALTER COLUMN `provider` DROP DEFAULT, ALGORITHM=INPLACE, LOCK=SHARED').format(table)


def inplace_restore_sql(table):
    """Only before ingestion, after verifying the original receipt and backup."""
    financial_fields(table)
    return ('ALTER TABLE `{}` DROP PRIMARY KEY, DROP INDEX `uq_statement_disclosure`, '
            'DROP COLUMN `id`, DROP COLUMN `provider`, DROP COLUMN `source_metadata`, '
            'DROP COLUMN `content_hash`, ADD PRIMARY KEY (`symbol`,`report_date`), '
            'MODIFY COLUMN `disclosure_date` DATE NULL DEFAULT NULL AFTER `report_date`, '
            'ALGORITHM=INPLACE, LOCK=SHARED').format(table)


def _backup_tag(tag):
    if not isinstance(tag, str) or not re.fullmatch(r'[a-zA-Z0-9_]{1,20}', tag):
        raise ValueError('Invalid bounded migration backup tag')
    return tag


def cutover_rename_sql(backup_tag):
    """Render, never execute, a single three-table rename retaining originals.

    Caller must revalidate source/shadow digests after draining writers and
    verify destination names are absent. Views are switched before new writes.
    """
    _backup_tag(backup_tag)
    pairs = []
    for table in TABLES:
        pairs.extend(['`{0}` TO `{0}_legacy_{1}`'.format(table, backup_tag),
                      '`{0}_pit_shadow` TO `{0}`'.format(table)])
    return 'RENAME TABLE ' + ', '.join(pairs)


def pre_ingestion_restore_sql(backup_tag):
    """Render recovery only for a verified, stopped, pre-ingestion cutover.

    The executor must prove that no new versions were accepted and restore view
    definitions separately. Never execute this after ingestion has been enabled.
    No table is dropped; retained targets must not already exist.
    """
    _backup_tag(backup_tag)
    pairs = []
    for table in TABLES:
        pairs.extend(['`{0}` TO `{0}_pit_retained_{1}`'.format(table, backup_tag),
                      '`{0}_legacy_{1}` TO `{0}`'.format(table, backup_tag)])
    return 'RENAME TABLE ' + ', '.join(pairs)


def combined_view_cutover_sql(show_create):
    """Preserve a reviewed SHOW CREATE VIEW header; change only raw inputs.

    Existing DEFINER, ALGORITHM and SQL SECURITY are retained verbatim. Capture
    and verify session charset/collation and grants separately before execution.
    """
    statements = sqlparse.parse(show_create)
    if len(statements) != 1 or statements[0].get_type() != 'CREATE':
        raise ValueError('Expected one SHOW CREATE VIEW statement')
    tokens = statements[0].tokens
    significant = [(index, token) for index, token in enumerate(tokens) if not token.is_whitespace]
    if significant[0][1].normalized != 'CREATE':
        raise ValueError('Expected original CREATE VIEW definition')
    views = [offset for offset, (_, token) in enumerate(significant)
             if token.ttype in Keyword and token.normalized == 'VIEW']
    if len(views) != 1 or len(significant) <= views[0] + 2:
        raise ValueError('Expected one named view')
    name = significant[views[0] + 1][1]
    as_index, as_token = significant[views[0] + 2]
    if (not isinstance(name, Identifier)
            or name.get_real_name() != 'saa_financial_statements_combined'
            or name.get_parent_name() not in (None, 'saa')
            or as_token.ttype not in Keyword or as_token.normalized != 'AS'):
        raise ValueError('Unexpected combined view identity or definition')
    header = ''.join(token.value for token in tokens[:as_index + 1])
    body = ''.join(token.value for token in tokens[as_index + 1:])
    header = re.sub(r'\bCREATE\b', 'CREATE OR REPLACE', header, count=1, flags=re.IGNORECASE)
    return header + latest_combined_definition(body)


def latest_combined_definition(definition):
    """Change only the three reviewed input identifiers in a SELECT definition.

    Preserve expressions, aliases, comments and literals byte-for-byte. This
    does not render CREATE VIEW privileges/definer; the execution package must
    preserve those separately from SHOW CREATE VIEW.
    """
    statements = sqlparse.parse(definition)
    if len(statements) != 1 or statements[0].get_type() != 'SELECT':
        raise ValueError('Expected one combined SELECT definition')
    tables = {'saa_raw_balance_sheet', 'saa_raw_income_statement',
              'saa_raw_cash_flow_statement'}
    counts = dict.fromkeys(tables, 0)
    output = []
    for token in statements[0].flatten():
        name = token.value.strip('`')
        if token.ttype in Name and name in tables:
            if not isinstance(token.parent, Identifier) or token.parent.get_real_name() != name:
                raise ValueError('Unexpected raw-table identifier context')
            counts[name] += 1
            replacement = name.replace('saa_raw_', 'saa_latest_', 1)
            output.append('`' + replacement + '`' if token.value.startswith('`') else replacement)
        else:
            output.append(token.value)
    if any(count != 1 for count in counts.values()):
        raise ValueError('Combined definition must reference each raw input exactly once')
    return ''.join(output)


def shadow_statements(table, legacy_columns):
    """Render empty shadow-table DDL without overwriting existing objects.

The reviewed source has a nullable DATE disclosure column without a comment
or expression. This is not a general-purpose arbitrary-schema migrator.
"""
    try:
        fields = financial_fields(table)
    except KeyError as exc:
        raise ValueError('Unknown financial table') from exc
    columns = tuple(legacy_columns)
    expected = ('symbol', 'report_date', 'disclosure_date', *fields)
    if columns != expected:
        raise ValueError('Legacy columns differ from the reviewed ordered contract')
    shadow = table + '_pit_shadow'
    return (
        'CREATE TABLE `{}` LIKE `{}`'.format(shadow, table),
        ('ALTER TABLE `{}` DROP PRIMARY KEY, '
         'ADD COLUMN `id` BIGINT NOT NULL AUTO_INCREMENT FIRST, '
         'ADD PRIMARY KEY (`id`), '
         'MODIFY COLUMN `disclosure_date` DATE NOT NULL AFTER `report_date`, '
         'ADD COLUMN `provider` VARCHAR(32) NOT NULL AFTER `disclosure_date`, '
         'ADD COLUMN `source_metadata` JSON NULL AFTER `provider`, '
         'ADD COLUMN `content_hash` CHAR(64) NOT NULL AFTER `source_metadata`, '
         'ADD UNIQUE KEY `uq_statement_disclosure` '
         '(`symbol`,`report_date`,`disclosure_date`)').format(shadow),
    )


def legacy_snapshot(table, row):
    """Prepare preserved values without certifying historical PIT provenance."""
    expected = {'symbol', 'report_date', 'disclosure_date', *financial_fields(table)}
    if set(row) != expected:
        raise ValueError('Unexpected or incomplete legacy financial snapshot')
    return prepare_version(table, dict(row, provider='unknown', source_metadata=None))
