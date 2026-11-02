"""Evidence-based signed impairment effects; never infer a sign from the year.

The source's cost total is retained. Its impairment inclusion is recorded so
consumers must not subtract a signed effect twice. Unproved nonzero values are
rejected, including apparently plausible negative values.
"""
from decimal import Decimal, ROUND_HALF_UP
from itertools import product


GAINS = ('oth_income', 'asset_disp_income', 'invest_income',
         'fv_value_chg_gain', 'forex_gain', 'net_expo_hedging_benefits')
COST_COMPONENTS = ('oper_cost', 'biz_tax_surchg', 'sell_exp', 'admin_exp', 'fin_exp', 'rd_exp')
EVIDENCE_FIELDS = ('comp_type', 'total_revenue', 'total_cogs', 'total_opcost',
                   'operate_profit', 'assets_impair_loss',
                   'oth_impair_loss_assets', 'credit_impa_loss', 'other_bus_cost') + GAINS + COST_COMPONENTS
TOLERANCE = Decimal('0.05')


class UnresolvedImpairment(ValueError):
    pass


def _number(value):
    if value is None or str(value) in ('nan', 'NaN', '<NA>'):
        return None
    number = Decimal(str(value))
    if not number.is_finite():
        raise UnresolvedImpairment('Nonfinite impairment evidence')
    return number.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def normalize_impairment(raw):
    """Return a signed effect and bounded evidence, or reject ambiguity."""
    primary = _number(raw.get('assets_impair_loss'))
    # Do not fill a mapped NULL from a distinct "other impairment" concept.
    source = 'assets_impair_loss'
    value = primary
    evidence = dict(normalization_rule='impairment_signed_v1',
                    impairment_source_field=source,
                    impairment_source_value='NULL' if value is None else str(value))
    if value is None or value == 0:
        evidence['impairment_cost_basis'] = 'not_applicable'
        return value, evidence
    if any(field not in raw for field in EVIDENCE_FIELDS if field != 'other_bus_cost'):
        raise UnresolvedImpairment('Missing impairment evidence columns')
    numbers = {field: _number(raw.get(field)) for field in EVIDENCE_FIELDS if field != 'comp_type'}
    if (numbers['total_opcost'] is None and str(raw.get('comp_type')) in {'2', '4', '7'}
            and numbers['admin_exp'] is not None
            and all(numbers[k] is not None for k in ('total_revenue', 'total_cogs', 'operate_profit'))
            and abs(numbers['total_revenue'] - numbers['total_cogs'] - numbers['operate_profit'])
            <= TOLERANCE):
        if 'other_bus_cost' not in raw:
            raise UnresolvedImpairment('Missing financial expense components')
        numbers['total_opcost'] = sum(numbers[k] or Decimal(0) for k in COST_COMPONENTS + ('other_bus_cost',))
    if any(numbers[field] is None for field in
           ('total_revenue', 'total_cogs', 'total_opcost', 'operate_profit')):
        raise UnresolvedImpairment('Missing impairment reconciliation anchors')
    revenue, cost, base_cost, profit = (numbers[f] for f in
        ('total_revenue', 'total_cogs', 'total_opcost', 'operate_profit'))
    gains = sum((numbers[f] or Decimal(0)) for f in GAINS)
    credit = numbers['credit_impa_loss'] or Decimal(0)
    residuals = [('gross_revenue', profit - (revenue - base_cost + gains))]
    # Financial-style net revenue already includes the disclosed gains. It is
    # admissible only when revenue minus total expenses equals operating profit.
    if abs(revenue - cost - profit) <= TOLERANCE:
        residuals.append(('net_revenue', profit - (revenue - base_cost)))
    if (str(raw.get('comp_type')) == '1' and all(k in raw for k in COST_COMPONENTS)
            and _number(raw.get('oper_cost')) is not None
            and abs(sum((_number(raw[k]) or Decimal(0)) for k in COST_COMPONENTS)
                    - base_cost) <= TOLERANCE and abs(cost - base_cost) > TOLERANCE):
        residuals.append(('cost_components', base_cost - cost))
    matches = {}
    for effect, credit_effect in product({value, -value}, {credit, -credit}):
        total = effect + credit_effect
        if abs(cost - base_cost + total) <= TOLERANCE:
            basis = 'included'
        elif abs(cost - base_cost) <= TOLERANCE:
            basis = 'excluded'
        else:
            continue
        for mode, residual in residuals:
            if abs(residual - total) <= TOLERANCE:
                matches[(effect, credit_effect)] = (mode, basis)
    if len(matches) != 1:
        raise UnresolvedImpairment('Impairment sign is not uniquely reconciled')
    (effect, credit_effect), (mode, basis) = next(iter(matches.items()))
    evidence.update(normalization_rule='impairment_signed_v1_' + mode,
                    impairment_credit_effect=str(credit_effect),
                    impairment_cost_basis=basis)
    return effect, evidence
