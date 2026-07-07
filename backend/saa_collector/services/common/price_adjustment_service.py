# -*- coding: utf-8 -*-
import pandas as pd


DEFAULT_MIN_MONTHLY_RATIO = 0.1
DEFAULT_MAX_MONTHLY_RATIO = 10.0


def find_adjusted_price_discontinuities(
        price_frame,
        code_column='code',
        date_column='date',
        price_column='price',
        min_ratio=DEFAULT_MIN_MONTHLY_RATIO,
        max_ratio=DEFAULT_MAX_MONTHLY_RATIO):
    if price_frame is None or price_frame.empty:
        return pd.DataFrame(columns=[
            code_column,
            'previous_date',
            date_column,
            'previous_price',
            price_column,
            'ratio',
        ])

    required_columns = {code_column, date_column, price_column}
    missing_columns = required_columns - set(price_frame.columns)
    if missing_columns:
        raise ValueError(f"Missing price columns: {sorted(missing_columns)}")

    df = price_frame[[code_column, date_column, price_column]].copy()
    df[date_column] = pd.to_datetime(df[date_column])
    df[price_column] = pd.to_numeric(df[price_column], errors='coerce')
    df = df.dropna(subset=[code_column, date_column, price_column])
    df = df.sort_values([code_column, date_column])

    grouped = df.groupby(code_column, sort=False)
    df['previous_date'] = grouped[date_column].shift(1)
    df['previous_price'] = grouped[price_column].shift(1)
    df['ratio'] = df[price_column] / df['previous_price'].replace(0, pd.NA)

    mask = df['previous_price'].notna() & ~df['ratio'].between(min_ratio, max_ratio)
    return df.loc[
        mask,
        [code_column, 'previous_date', date_column, 'previous_price', price_column, 'ratio']
    ].reset_index(drop=True)
