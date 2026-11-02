"""Ordered, bounded source arbitration rules. No field merging or I/O."""


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
