"""Ordered, bounded source arbitration rules. No field merging or I/O."""
from decimal import Decimal, localcontext
from itertools import combinations
import json


SAME_DAY_RELATIVE_TOLERANCE = Decimal('0.05')


def select_numeric_equivalent(candidates, fields):
    """Select one whole row only after all same-rank pairs pass tolerance."""
    fields = sorted(fields)
    changed = [field for field in fields
               if len({row[field] for row in candidates}) > 1]
    if not changed:
        return None
    max_difference = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 50
        for left, right in combinations(candidates, 2):
            for field in changed:
                a, b = left[field], right[field]
                if a == b:
                    continue
                if a is None or b is None or a * b < 0:
                    return None
                delta, denominator = 2 * abs(a - b), abs(a) + abs(b)
                if delta > SAME_DAY_RELATIVE_TOLERANCE * denominator:
                    return None
                max_difference = max(max_difference, delta / denominator)
    # Lexical order is only a reproducibility tie-break among equivalent rows,
    # not evidence that one source value is more authoritative.
    ordered = sorted(candidates, key=lambda row: (
        tuple('NULL' if row[f] is None else str(row[f]) for f in fields),
        json.dumps(row['source_metadata'], sort_keys=True)))
    records = [dict(values={f: None if row[f] is None else str(row[f]) for f in changed},
                    source={k: row['source_metadata'][k] for k in
                            ('report_type', 'update_flag', 'comp_type', 'ann_date', 'f_ann_date')
                            if k in row['source_metadata']}) for row in ordered]
    unique_records = list(dict.fromkeys(json.dumps(r, sort_keys=True) for r in records))
    audit = json.dumps(dict(rule='symmetric_relative_v1', threshold=str(SAME_DAY_RELATIVE_TOLERANCE),
                           max_relative_difference=str(max_difference),
                           selection='lexical_whole_row', selected=json.loads(unique_records[0]),
                           candidates=[json.loads(r) for r in unique_records]), sort_keys=True)
    if len(audit) > 4096:
        return None  # Never silently discard audit evidence to accept a conflict.
    selected = dict(ordered[0], source_metadata=dict(ordered[0]['source_metadata']))
    selected['source_metadata']['numeric_tolerance_audit'] = audit
    return selected


def _match_current_report_comp_type(candidates, references):
    first = candidates[0]
    types = {row['source_metadata'].get('comp_type') for row in candidates}
    if len(types) < 2 or None in types or first['version_type'] != 'RESTATED':
        return None
    visible = [row for row in references if row['version_type'] == 'LATEST'
               and row['symbol'] == first['symbol']
               and row['report_date'] == first['report_date']
               and row['disclosure_date'] <= first['disclosure_date']]
    updated = [row for row in visible if row['source_metadata'].get('update_flag') == '1']
    reference_types = {row['source_metadata'].get('comp_type') for row in (updated or visible)}
    if len(reference_types) != 1 or None in reference_types:
        return None
    selected = [row for row in candidates
                if row['source_metadata'].get('comp_type') in reference_types]
    return selected if len(selected) == 1 else None


RULES = (('match_current_report_comp_type_v1', _match_current_report_comp_type),)


def arbitrate_candidates(candidates, references):
    if len(candidates) < 2:
        return candidates, None
    for name, rule in RULES:
        selected = rule(candidates, references)
        if selected is not None:
            return selected, name
    return candidates, None
