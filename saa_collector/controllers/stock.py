import copy
import re
import time

import mysql.connector
from cement import Controller, ex
from cement.utils.version import get_version_banner

from ..core.version import get_version
from ..third_party.cninfo_api_client import CninfoApiClient, CninfoApiException

VERSION_BANNER = """
Collect stock basic data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Stock(Controller):
    class Meta:
        label = 'stock'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def _process_parsed_arguments(self):
        api_config = self.app.config.get('saa_collector', 'api')
        self.client = CninfoApiClient(api_config['client_id'], api_config['client_secret'])
        self.db_config = self.app.config.get('saa_collector', 'db')

    @ex(
        help='example sub collect-stocks',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
        ],
    )
    def collect_stocks(self):
        start_time = time.time()
        self.client.login()

        symbol_arg = self.app.pargs.symbol
        if symbol_arg is None:
            plate_response = self.client.get_plate_stock_list('137001')
            plate_stock_list = plate_response['records']
            symbols = [v['SECCODE'] for v in plate_stock_list]
        else:
            symbols = symbol_arg.split(',')

        symbol_chunks = [symbols[i:i + 50] for i in range(0, len(symbols), 50)]
        chunk_index = 0
        fail_round = 0
        db_conn = mysql.connector.connect(**self.db_config)
        while chunk_index < len(symbol_chunks):
            try:
                symbol_chunk = symbol_chunks[chunk_index]
                stock_info_list = self.get_stock_info_list(symbol_chunk)
                self.to_sql(stock_info_list, db_conn, 'saa_stocks', 'symbol')
                chunk_index += 1
                time.sleep(1)
            except CninfoApiException:
                if fail_round > len(symbol_chunks):
                    raise
                fail_round += 1
                self.client.login()

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')
        print("--- %s seconds ---" % int(time.time() - start_time))

    def get_stock_info_list(self, scode_list):
        exchange_dict = {
            '深交所': 'SZ',
            '上交所': 'SH'
        }
        board_dict = {
            '': 'MAIN_BOARD',
            '主板': 'MAIN_BOARD',
            '中小板': 'SMALL_AND_MEDIUM_ENTERPRISES',
            '创业板': 'CHINEXT',
            '科创板': 'STAR'
        }
        stock_response = self.client.get_stock_basic_info(scode_list)
        stock_records = stock_response['records']
        stock_info_dict = {}
        for record in stock_records:
            match = re.match(r'(.*所)(.*)', record['F005V'])
            stock_info = {
                'symbol': record['SECCODE'],
                'exchange': exchange_dict[match.group(1)],
                'board': board_dict[match.group(2)],
                'issue_quantity': record['F007N'],
                'listing_time': record['F006D'],
            }
            stock_info_dict[stock_info['symbol']] = stock_info

        company_response = self.client.get_company_basic_info(scode_list)
        company_records = company_response['records']
        company_info_dict = {}
        for record in company_records:
            stock_info = {
                'symbol': record['SECCODE'],
                'name': record['SECNAME'],
                'industry_classification_id': record['F031V'],
                'company_name': record['ORGNAME'],
                'english_name': record['F001V'],
                'registered_address': record['F004V'],
                'company_referred': record['SECNAME'],
                'legal_representative': record['F003V'],
                'secretary': record['F018V'],
                'registered_capital': record['F007N'],
                'zip_code': record['F006V'],
                'tel': record['F013V'],
                'fax': record['F014V'],
                'website': record['F011V'],
                'lead_underwriter': record['F047V'],
                'sponsor': record['F046V'],
            }
            company_info_dict[stock_info['symbol']] = stock_info

        for symbol, stock_info in stock_info_dict.items():
            stock_info.update(company_info_dict[symbol])
        return list(stock_info_dict.values())

    def to_sql(self, rows, con, table, primary_key):
        if len(rows) == 0:
            return
        fields = list(rows[0].keys())
        normal_fields = copy.deepcopy(fields)
        normal_fields.remove(primary_key)
        update_statements = []
        for field in normal_fields:
            update_statements.append("{} = VALUES({})".format(field, field))
        update_statement = ", ".join(update_statements)
        sql = "INSERT INTO {} ({}) VALUES ({}) ON DUPLICATE KEY UPDATE {}".format(
            table, ", ".join(fields), ", ".join(["%s"] * len(fields)), update_statement
        )
        cursor = con.cursor(prepared=True)
        for stock_info in rows:
            try:
                values = stock_info.values()
                values = [None if v is None else str(v) for v in values]
                cursor.execute(sql, tuple(values))
            except:
                print(stock_info)
                raise
        con.commit()
