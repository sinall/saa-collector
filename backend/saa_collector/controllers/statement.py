from datetime import date, datetime

import mysql.connector
import pandas as pd
from cement import ex
from cement.utils.version import get_version_banner

from .basic import Basic
from ..core.version import get_version
from ..services.common.config_service import ConfigService

VERSION_BANNER = """
Collect financial data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Statement(Basic):
    class Meta:
        label = 'statement'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.config_service = ConfigService()
        self.db_config = self.config_service.get_db_config()
        self.statement_service = self.service_factory.create_statement_service()

    @ex(
        help='example sub produce-all-statements',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
            (['--start-date'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'start_date'}),
            (['--build'],
             {'help': 'Specify build type',
              'choices': ['all', 'missing'],
              'default': 'missing'})
        ],
    )
    def produce_all_statements(self):
        symbols = sorted(set(self.build_missing_data_points()['symbol']))
        start_date = self.build_start_date()
        self.statement_service.produce(symbols, start_date)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')

    @ex(
        help='example sub collect-all-statements',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
            (['--start-date'],
             {'help': 'notorious start-date option',
              'action': 'store',
              'dest': 'start_date'}),
        ],
    )
    def collect_all_statements(self):
        symbols = self.build_missing_data_points()
        start_date = self.build_start_date()
        self.statement_service.collect(symbols, start_date)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')

    @ex(
        help='example sub collect-main-business',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
            (['--start-date'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'start_date'}),
        ],
    )
    def collect_main_business(self):
        symbols = self.build_missing_data_points()
        start_date = self.build_start_date()
        self.statement_service.collect_main_business(symbols, start_date)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')

    def build_missing_data_points(self):
        symbols = super().build_symbols()
        df = self.get_financial_data_existence(symbols, self.app.pargs.start_date)
        return df

    @staticmethod
    def generate_quarterly_dates(start_date, end_date):
        quarter_end_days = {3: 31, 6: 30, 9: 30, 12: 31}
        dates = []
        for year in range(start_date.year, end_date.year + 1):
            for month in quarter_end_days:
                day = quarter_end_days[month]
                d = date(year, month, day)
                if start_date <= d <= end_date:
                    dates.append(d)
        return sorted(dates)

    @staticmethod
    def clean_date_column(series):
        try:
            cleaned = pd.to_datetime(series.astype(str), errors='coerce')
            return cleaned.dt.date
        except Exception as e:
            return None

    @staticmethod
    def build_where_clause(symbols=None, date_field=None, start_date=None):
        conditions = []
        if symbols:
            symbols_str = ",".join([f"'{s}'" for s in symbols])
            conditions.append(f"symbol IN ({symbols_str})")
        if start_date and date_field:
            conditions.append(f"{date_field} >= '{start_date}'")
        return "WHERE " + " AND ".join(conditions) if conditions else ""

    def get_financial_data_existence(self, symbols, start_date):
        try:
            conn = mysql.connector.connect(**self.db_config)
            where_stocks = Statement.build_where_clause(symbols, "listing_time", start_date)
            stocks_df = pd.read_sql(f"SELECT symbol, listing_time FROM saa_stocks {where_stocks}", conn)
            stocks_df['listing_time'] = Statement.clean_date_column(stocks_df['listing_time'])
            stocks_df = stocks_df.dropna(subset=['listing_time'])

            where_reports = Statement.build_where_clause(symbols, "date", start_date)
            query = f"""
            SELECT 'balance_sheet' AS table_type, symbol, date FROM saa_raw_balance_sheet {where_reports}
            UNION ALL
            SELECT 'cash_flow' AS table_type, symbol, date FROM saa_raw_cash_flow_statement {where_reports}
            UNION ALL
            SELECT 'income_statement' AS table_type, symbol, date FROM saa_raw_income_statement {where_reports}
            """
            records_df = pd.read_sql(query, conn)
            records_df['date'] = self.clean_date_column(records_df['date'])
            records_df = records_df.dropna(subset=['date'])

            existence_df = records_df.pivot_table(
                index=['symbol', 'date'],
                columns='table_type',
                aggfunc='size',
                fill_value=0
            ).reset_index()
            existence_df.columns = ['symbol', 'date', 'balance_sheet', 'cash_flow', 'income_statement']

            min_date = stocks_df['listing_time'].min()
            max_date = datetime.now().date()
            all_quarter_dates = Statement.generate_quarterly_dates(min_date, max_date)

            all_combinations = []
            for idx, stock in stocks_df.iterrows():
                symbol = stock['symbol']
                listing_time = stock['listing_time']

                for q_date in all_quarter_dates:
                    if q_date >= listing_time:
                        all_combinations.append({'symbol': symbol, 'date': q_date})

            all_combinations_df = pd.DataFrame(all_combinations)

            result_df = pd.merge(
                all_combinations_df,
                existence_df,
                on=['symbol', 'date'],
                how='left'
            ).fillna(0)

            result_df = result_df.rename(columns={
                'balance_sheet': 'balance_sheet_existing',
                'cash_flow': 'cash_flow_statement_existing',
                'income_statement': 'income_statement_existing'
            })
            result_df[['balance_sheet_existing', 'cash_flow_statement_existing', 'income_statement_existing']] = \
                result_df[['balance_sheet_existing', 'cash_flow_statement_existing', 'income_statement_existing']].astype(
                    int)

            result_df = result_df.sort_values(['symbol', 'date'])
            return result_df
        finally:
            if 'conn' in locals() and conn.is_connected():
                conn.close()
