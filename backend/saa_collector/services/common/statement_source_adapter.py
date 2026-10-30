"""Pure financial source normalization; no requests, connections or writes.

The frozen XLS mapping defines field coverage. Missing mapped response columns
are errors, not NULL. The explicitly listed unmapped fields remain unsupported;
they are never inherited from another disclosure or provider.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re
import logging

import pandas as pd

from .financial_statement_contract import content_hash, financial_fields, financial_scale
from .statement_version_writer import prepare_version, StatementVersionConflict, conflict_issue


TUSHARE_RESOURCES = {
    'saa_raw_balance_sheet': 'balancesheet',
    'saa_raw_income_statement': 'income',
    'saa_raw_cash_flow_statement': 'cashflow',
}
TUSHARE_REPORT_TYPES = ('1', '4', '5')
# Daily projection policy: latest consolidated, adjusted comparative, pre-adjustment.
# This is not a chronology across disclosure dates, nor an upstream tie-break guarantee.
TUSHARE_REPORT_PRIORITY = {'1': 0, '4': 1, '5': 2}
logger = logging.getLogger(__name__)
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


def tushare_snapshots(table, raw_records, mapping):
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
                   disclosure_date=disclosure_date(published), provider='tushare',
                   source_metadata=dict(upstream='tushare', endpoint=endpoint,
                                        report_type=report_type))
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
        key = (row['symbol'], row['report_date'], row['disclosure_date'])
        versions.setdefault(key, []).append(row)

    result = []
    for key in sorted(versions):
        candidates = versions[key]
        best_type = min((row['source_metadata']['report_type'] for row in candidates),
                        key=TUSHARE_REPORT_PRIORITY.__getitem__)
        typed = [row for row in candidates if row['source_metadata']['report_type'] == best_type]
        updated = [row for row in typed if row['source_metadata'].get('update_flag') == '1']
        eligible = updated or typed
        row = eligible[0]
        conflicting = next((other for other in eligible
                            if content_hash(table, other) != content_hash(table, row)), None)
        if conflicting is not None:
            changed = [field for field in fields if conflicting[field] != row[field]]
            raise StatementVersionConflict(
                'Same-day source content conflict: table={} key={} fields={}'.format(
                    table, key, ','.join(changed)),
                issue=conflict_issue(table, row, conflicting))
        if len(typed) < len(candidates):
            logger.info('Resolved same-day statement candidates: table=%s key=%s '
                        'selected_report_type=%s update_flag=%s discarded_types=%s',
                        table, key, best_type, row['source_metadata'].get('update_flag'),
                        sorted({r['source_metadata']['report_type'] for r in candidates
                                if r['source_metadata']['report_type'] != best_type}))
        result.append(row)
    return result
