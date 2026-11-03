"""Pure financial source normalization; no requests, connections or writes.

The frozen XLS mapping defines field coverage. Missing mapped response columns
become NULL with evidence. The explicitly listed unmapped fields remain unsupported;
they are never inherited from another disclosure or provider.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re
import json

import pandas as pd

from .financial_statement_contract import content_hash, financial_fields, financial_scale
from .statement_version_writer import prepare_version, StatementVersionConflict, conflict_issue
from .statement_impairment import normalize_impairment, UnresolvedImpairment, EVIDENCE_FIELDS
from .statement_arbitration import arbitrate_candidates, select_numeric_equivalent


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


def statement_field_issues(table, row):
    """Build bounded job diagnostics from a committed row's provenance."""
    metadata = row.get('source_metadata') or {}
    issues = []
    common = dict(provider=row['provider'], symbol=row['symbol'], table=table,
                  report_date=row['report_date'].isoformat(),
                  disclosure_date=row['disclosure_date'].isoformat(),
                  version_type=row['version_type'], action='STORE_NULL_CONTINUE')
    missing = json.loads(metadata.get('missing_source_fields', '{}'))
    if missing:
        issues.append(dict(common, code='STATEMENT_SOURCE_FIELDS_MISSING', differences={
            field: dict(source_field=source, stored_value=None, reason='missing_source_column')
            for field, source in missing.items()}))
    if metadata.get('impairment_warning'):
        issues.append(dict(common, code='STATEMENT_FIELD_NULLIFIED', differences={
            'asset_impairment_loss': dict(source_value=metadata['impairment_source_value'],
                                          stored_value=None, reason=metadata['impairment_warning'])}))
    if metadata.get('conflict_null_audit'):
        audit = json.loads(metadata['conflict_null_audit'])
        issues.append(dict(common, code='STATEMENT_FIELD_NULLIFIED', differences={
            field: dict(candidates=values, stored_value=None, reason='same_identity_source_conflict')
            for field, values in audit['fields'].items()}))
    return issues


def _null_conflicting_fields(table, candidates, fields):
    # A deterministic metadata carrier; no disputed financial value survives.
    ordered = sorted(candidates, key=lambda row: (
        json.dumps(row['source_metadata'], sort_keys=True), content_hash(table, row)))
    differences = {}
    for field in sorted(fields):
        values = sorted({row[field] for row in candidates},
                        key=lambda value: 'NULL' if value is None else str(value))
        if len(values) > 1:
            differences[field] = [None if value is None else str(value) for value in values]
    audit = json.dumps(dict(rule='same_identity_conflict_null_v1', fields=differences,
        sources=[dict(content_hash=content_hash(table, row),
                      values={f: None if row[f] is None else str(row[f]) for f in differences},
                      metadata={
            k: v for k, v in row['source_metadata'].items() if k in
            {'ann_date', 'f_ann_date', 'report_type', 'update_flag', 'comp_type',
             'impairment_warning', 'missing_source_fields'}}) for row in ordered]), sort_keys=True)
    if len(audit) > 4096:
        raise StatementVersionConflict('Source conflict audit exceeds bounded metadata capacity')
    row = dict(ordered[0], source_metadata=dict(ordered[0]['source_metadata']))
    row.update(dict.fromkeys(differences))
    row['source_metadata']['conflict_null_audit'] = audit
    row['source_metadata']['arbitration_rule'] = 'same_identity_conflict_null_v1'
    prepare_version(table, row)
    return row


def tushare_snapshots(table, raw_records, mapping, *, latest_query_complete=False,
                      normalize_signs=False):
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
    raw_by_row = {}
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
        if not _missing(raw.get('comp_type')):
            row['source_metadata']['comp_type'] = str(raw['comp_type'])
        omitted = sorted(field for field, config in configs.items()
                         if _missing(config.get('TushareField')) or config.get('TushareField') == '')
        if omitted:
            row['source_metadata']['omitted_fields'] = omitted
        missing_fields = {}
        for field, config in configs.items():
            source = config.get('TushareField')
            if _missing(source) or source == '':
                row[field] = None
                continue
            source = source.strip()
            if source not in raw:
                row[field] = None
                missing_fields[field] = source
                continue
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
        if missing_fields:
            row['source_metadata']['missing_source_fields'] = json.dumps(missing_fields, sort_keys=True)
        prepare_version(table, row)
        key = (row['symbol'], row['report_date'], row['disclosure_date'], row['version_type'])
        versions.setdefault(key, []).append(row)
        raw_by_row[id(row)] = raw

    result = []
    references = [row for group in versions.values() for row in group]
    for key in sorted(versions):
        candidates = versions[key]
        updated = [row for row in candidates if row['source_metadata'].get('update_flag') == '1']
        eligible = updated or candidates
        if normalize_signs and table == 'saa_raw_income_statement':
            original_candidates = eligible
            eligible, arbitration = arbitrate_candidates(eligible, references)
            summaries = []
            for candidate in original_candidates:
                raw = raw_by_row[id(candidate)]
                summaries.append(dict(candidate['source_metadata'],
                    assets_impair_loss=None if _missing(raw.get('assets_impair_loss')) else
                    str(Decimal(str(raw['assets_impair_loss'])).quantize(Decimal('.01')))))
            summaries = sorted({json.dumps(item, sort_keys=True) for item in summaries})
            audit = json.dumps([json.loads(item) for item in summaries], sort_keys=True)
            if len(audit) > 4096:
                raise ValueError('Too many impairment arbitration candidates')
            for candidate in eligible:
                raw = raw_by_row[id(candidate)]
                try:
                    effect, evidence = normalize_impairment(raw)
                except UnresolvedImpairment as exc:
                    effect = None
                    evidence = dict(normalization_rule='impairment_unverified_null_v1',
                                    impairment_source_field='assets_impair_loss',
                                    impairment_source_value=str(raw.get('assets_impair_loss')),
                                    impairment_cost_basis='unknown', impairment_warning=str(exc))
                candidate['asset_impairment_loss'] = effect
                metadata = candidate['source_metadata']
                metadata.update(evidence)
                metadata['normalization_candidates'] = audit
                metadata['impairment_evidence'] = json.dumps({
                    name: None if _missing(raw.get(name)) else str(raw[name])
                    for name in EVIDENCE_FIELDS}, sort_keys=True)
                if arbitration:
                    metadata['arbitration_rule'] = arbitration
                prepare_version(table, candidate)
            eligible = sorted(eligible, key=lambda row: json.dumps(row['source_metadata'], sort_keys=True))
        row = eligible[0]
        conflicting = next((other for other in eligible
                            if content_hash(table, other) != content_hash(table, row)), None)
        if conflicting is not None:
            selected = select_numeric_equivalent(eligible, fields)
            if selected is not None:
                row = selected
                prepare_version(table, row)
                conflicting = None
        if conflicting is not None:
            row = _null_conflicting_fields(table, eligible, fields)
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
