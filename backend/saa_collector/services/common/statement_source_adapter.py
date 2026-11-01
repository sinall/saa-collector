"""Pure financial source normalization; no requests, connections or writes.

The frozen XLS mapping defines field coverage. Missing mapped response columns
are errors, not NULL. The explicitly listed unmapped fields remain unsupported;
they are never inherited from another disclosure or provider.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re

import pandas as pd

from .financial_statement_contract import content_hash, financial_fields, financial_scale
from .statement_version_writer import prepare_version, StatementVersionConflict, conflict_issue


TUSHARE_RESOURCES = {
    'saa_raw_balance_sheet': 'balancesheet',
    'saa_raw_income_statement': 'income',
    'saa_raw_cash_flow_statement': 'cashflow',
}
TUSHARE_REPORT_TYPES = ('1', '4', '5')
TUSHARE_VERSION_TYPES = {'1': 'LATEST', '4': 'RESTATED', '5': 'ORIGINAL'}
# Existing XLS coverage, not a blanket policy for newly missing fields.
TUSHARE_UNMAPPED = {
    'saa_raw_balance_sheet': frozenset({
        'amounts_due_from_related_companies', 'due_to_related_parties',
        'non_normal_operating_items_gain_adjustment'}),
    'saa_raw_income_statement': frozenset({
        'subsidy_income', 'other_items_affecting_total_profit',
        'other_items_affecting_net_profit'}),
    'saa_raw_cash_flow_statement': frozenset(),
}


def _missing(value):
    return value is None or (not isinstance(value, (dict, list, tuple)) and bool(pd.isna(value)))


def disclosure_date(value):
    if type(value) is date:
        return value
    if isinstance(value, str):
        for pattern, format_ in ((r'\d{8}', '%Y%m%d'), (r'\d{4}-\d{2}-\d{2}', '%Y-%m-%d')):
            if re.fullmatch(pattern, value):
                return datetime.strptime(value, format_).date()
    raise ValueError('Missing or invalid source date')


class CompleteStatementHistory(list):
    """Returned only after all three type queries and their pages succeeded."""


def tushare_snapshots(table, raw_records, mapping, *, latest_query_complete=False):
    endpoint = TUSHARE_RESOURCES[table]
    fields = financial_fields(table)
    selected = mapping[mapping['Field'].isin(fields)]
    if selected['Field'].duplicated().any():
        raise ValueError('Duplicate mapping for financial field')
    if set(selected['Field']) != set(fields):
        raise ValueError('Incomplete financial mapping')
    configs = {row['Field']: row for row in selected.to_dict('records')}
    for field, config in configs.items():
        source = config.get('TushareField')
        if (_missing(source) or source == '') and field not in TUSHARE_UNMAPPED[table]:
            raise ValueError('Unreviewed unmapped financial field: ' + field)

    versions = {}
    for raw in raw_records:
        report_type = str(raw.get('report_type', ''))
        if report_type not in TUSHARE_REPORT_TYPES:
            raise ValueError('Unsupported Tushare consolidated/YTD report type: ' + report_type)
        code = raw.get('ts_code', '')
        if not isinstance(code, str) or not re.fullmatch(r'\d{6}\.(SH|SZ|BJ)', code):
            raise ValueError('Invalid Tushare security code')
        period = disclosure_date(raw.get('end_date'))
        if (period.month, period.day) not in {(3, 31), (6, 30), (9, 30), (12, 31)}:
            raise ValueError('Unsupported non-quarter-end report period')
        published = raw.get('f_ann_date')
        if _missing(published) or published == '':
            published = raw.get('ann_date')
        row = dict(symbol=code[:6], report_date=period,
                   version_type=TUSHARE_VERSION_TYPES[report_type],
                   disclosure_date=disclosure_date(published), provider='tushare',
                   source_metadata=dict(upstream='tushare', endpoint=endpoint,
                                        report_type=report_type))
        for name in ('ann_date', 'f_ann_date'):
            if not _missing(raw.get(name)) and raw[name] != '':
                row['source_metadata'][name] = disclosure_date(raw[name]).strftime('%Y%m%d')
        if not _missing(raw.get('update_flag')):
            row['source_metadata']['update_flag'] = str(raw['update_flag'])
        omitted = sorted(field for field, config in configs.items()
                         if _missing(config.get('TushareField')) or config.get('TushareField') == '')
        if omitted:
            row['source_metadata']['omitted_fields'] = omitted
        for field, config in configs.items():
            source = config.get('TushareField')
            if _missing(source) or source == '':
                row[field] = None
                continue
            source = source.strip()
            if source not in raw:
                raise ValueError('Missing source field: ' + source)
            value = raw[source]
            if _missing(value):
                row[field] = None
                continue
            unit = config.get('TushareUnit', 1)
            unit = 1 if _missing(unit) else unit
            try:
                with localcontext() as ctx:
                    ctx.prec = 40
                    number = Decimal(str(value)) * Decimal(str(unit))
                    if not number.is_finite():
                        raise ValueError('Nonfinite source financial value')
                    # Financial columns use the frozen SQL scale; normalization
                    # precedes hashing so stored values and hashes agree.
                    scale = financial_scale(table, field)
                    row[field] = number.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
            except InvalidOperation as exc:
                raise ValueError('Invalid source financial value: ' + field) from exc
        prepare_version(table, row)
        key = (row['symbol'], row['report_date'], row['disclosure_date'], row['version_type'])
        versions.setdefault(key, []).append(row)

    result = []
    for key in sorted(versions):
        candidates = versions[key]
        updated = [row for row in candidates if row['source_metadata'].get('update_flag') == '1']
        eligible = updated or candidates
        row = eligible[0]
        conflicting = next((other for other in eligible
                            if content_hash(table, other) != content_hash(table, row)), None)
        if conflicting is not None:
            changed = [field for field in fields if conflicting[field] != row[field]]
            raise StatementVersionConflict(
                'Same-day source content conflict: table={} key={} fields={}'.format(
                    table, key, ','.join(changed)),
                issue=conflict_issue(table, row, conflicting))
        result.append(row)
    if latest_query_complete:
        by_period = {}
        for row in result:
            by_period.setdefault((row['symbol'], row['report_date']), []).append(row)
        for rows in by_period.values():
            if any(row['version_type'] == 'LATEST' for row in rows):
                continue
            source = max(rows, key=lambda row: (
                row['disclosure_date'], row['version_type'] == 'RESTATED'))
            metadata = dict(source['source_metadata'])
            for key in ('report_type', 'update_flag'):
                metadata.pop(key, None)
            metadata.update(snapshot_origin='derived_latest',
                            derived_from_type=source['version_type'],
                            derived_from_hash=content_hash(table, source))
            derived = dict(source, version_type='LATEST', source_metadata=metadata)
            prepare_version(table, derived)
            result.append(derived)
    return result
