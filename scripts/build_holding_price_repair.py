#!/usr/bin/env python3
"""Build an offline collect-plan request; never calls an API or a database."""
import argparse
import csv
from datetime import date
import hashlib
import json
from pathlib import Path


def parse_missing(value):
    if value in (True, 'True', 'true', '1'):
        return True
    if value in (False, 'False', 'false', '0'):
        return False
    raise ValueError(f'Invalid missing flag: {value!r}')


def build_plan(rows):
    grouped = {}
    for row in rows:
        code = row['code']
        if len(code) != 6 or not code.isdigit():
            raise ValueError(f'Invalid stock code: {code!r}')
        target_date = date.fromisoformat(row['return_date']).isoformat()
        for data_type, flag in (
            ('historical_quote', 'missing_exact_price'),
            ('price_adjust_factor', 'missing_exact_adjustment'),
        ):
            if parse_missing(row[flag]):
                grouped.setdefault(data_type, set()).add((code, target_date))
    return {
        'name': '持有期月末行情与复权缺口修复',
        'execution_mode': 'SEQUENTIAL',
        'jobs': [
            {
                'data_type': data_type, 'stock_scope': 'SELECTED',
                'symbols': sorted({code for code, _ in targets}),
                'start_date': min(target for _, target in targets),
                'end_date': max(target for _, target in targets),
                'data_frequency': 'monthly',
                'end_date_mode': 'FIXED', 'skip_existing': False,
            }
            for data_type, targets in sorted(grouped.items())
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_file', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    content = args.csv_file.read_bytes()
    with args.csv_file.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    plan = build_plan(rows)
    counts = {
        data_type: len({(row['code'], row['return_date']) for row in rows if parse_missing(row[flag])})
        for data_type, flag in (
            ('historical_quote', 'missing_exact_price'),
            ('price_adjust_factor', 'missing_exact_adjustment'),
        )
    }
    scopes = []
    for job in plan['jobs']:
        start = date.fromisoformat(job['start_date'])
        end = date.fromisoformat(job['end_date'])
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        scopes.append({
            'data_type': job['data_type'], 'stocks': len(job['symbols']),
            'start_date': job['start_date'], 'end_date': job['end_date'],
            'months': months, 'max_stock_month_targets': months * len(job['symbols']),
        })
    manifest = {
        'source_file': args.csv_file.name, 'source_sha256': hashlib.sha256(content).hexdigest(),
        'unique_stock_dates': len({(row['code'], row['return_date']) for row in rows}),
        'stocks': len({row['code'] for row in rows}),
        'jobs': len(plan['jobs']), 'target_counts': counts,
        'job_scopes': scopes,
        'max_stock_month_targets': sum(scope['max_stock_month_targets'] for scope in scopes),
        'executed': False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in [('collect-plan-request.json', plan), ('manifest.json', manifest)]:
        (args.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
