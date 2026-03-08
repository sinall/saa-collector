# -*- coding: utf-8 -*-
import logging
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

import mysql.connector
import pandas as pd
import requests
import xlrd

from saa_collector.services.abstract.valuation_service import ValuationService
from saa_collector.services.common.config_service import ConfigService
from saa_collector.utils.db import DB


class ValuationServiceImpl(ValuationService):
    def __init__(self):
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.config = self.config_service.get_config()
        self.db_config = self.config_service.get_db_config()
        self.host = self.config.get('saa_collector').get('cnindex')['host']

    def collect(self, date=None):
        self.collect_board(date)
        self.collect_industry(date)

    def collect_board(self, date=None):
        table = 'saa_board_valuation_levels'
        records = self.query_board_records(date)
        self.save_records(records, table, ['board', 'report_date'])
        self._logger.info('Saved {} records to {}'.format(len(records), table))

    def collect_industry(self, date=None):
        table = 'saa_industry_valuation_levels'
        records = self.query_industry_records(date)
        self.save_records(records, table, ['industry_classification_id', 'report_date'])
        self._logger.info('Saved {} records to {}'.format(len(records), table))

    def query_board_records(self, date):
        date_str = date.strftime('%Y-%m-10')
        url = 'http://{}/sylExcelDowload?checkDate={}&category=crsc_ch'.format(self.host, date_str)
        response = requests.post(url)
        self._logger.info('Downloaded {} successfully'.format(url))
        # zip_file = ZipFile(BytesIO(response.content))
        # entry = zip_file.namelist()[0]
        # file_contents = zip_file.read(entry)
        book = xlrd.open_workbook(file_contents=response.content, encoding_override="GB2312")
        xls_file = pd.ExcelFile(book)
        name_sheets = xls_file.parse(None)
        sheets = name_sheets.values()
        for sheet in sheets:
            sheet.set_index('板块名称', inplace=True)
        df = pd.concat(sheets, axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
        name_map = {
            "板块名称": "board",
            "最新静态\n市盈率": "pe",
            "最新滚动\n市盈率": "pe_ttm",
            "最新市净率": "pb",
            "最近一年\n平均股息率": "dividend_rate",
            "股票家数": "total",
            "其中\n亏损家数": "total_of_loss",
            "其中\n负资产家数": "total_of_negative_equity",
            "其中\n未分红家数": "total_of_no_dividend",
        }
        df.reset_index(inplace=True)
        df.rename(columns=name_map, inplace=True)
        df = df[df['board'] != '-']
        df = df[name_map.values()]
        df['report_date'] = date.strftime('%Y-%m-%d')
        records = df.to_dict('records')
        return records

    def query_industry_records(self, date):
        date_str = date.strftime('%Y%m%d')
        url = 'http://{}/syl/{}.zip'.format(self.host, date_str)
        self._logger.info('Downloaded {} successfully'.format(url))
        response = requests.get(url)
        zip_file = ZipFile(BytesIO(response.content))
        entry = zip_file.namelist()[0]
        file_contents = zip_file.read(entry)
        book = xlrd.open_workbook(file_contents=file_contents, encoding_override="GB2312")
        xls_file = pd.ExcelFile(book)
        name_sheets = xls_file.parse(None)
        name_sheets.pop('个股数据', None)
        for sheet in name_sheets.values():
            sheet.set_index('行业代码', inplace=True)
        df = None
        for name, sheet in name_sheets.items():
            try:
                df = pd.concat([df, sheet], axis=1, sort=False)
            except Exception as e:
                self._logger.warning('Failed to merge sheet {}'.format(name))
        df = df.loc[:, ~df.columns.duplicated()]
        name_map = {
            "行业代码": "industry_classification_id",
            "最新静态\n市盈率": "pe",
            "最新滚动\n市盈率": "pe_ttm",
            "最新市净率": "pb",
            "最近一年\n平均股息率": "dividend_rate",
            "股票家数": "total",
            "其中\n亏损家数": "total_of_loss",
            "其中\n负资产家数": "total_of_negative_equity",
            "其中\n未分红家数": "total_of_no_dividend",
        }
        df.reset_index(inplace=True)
        df.rename(columns=name_map, inplace=True)
        df.drop(df.columns.difference(name_map.values()), axis=1, inplace=True)
        df['report_date'] = date.strftime('%Y-%m-%d')
        l1_id = ''
        for index, row in df.iterrows():
            id = row['industry_classification_id']
            if str.isalpha(id):
                l1_id = id
            else:
                df.at[index, 'industry_classification_id'] = l1_id + id
        records = df.to_dict('records')
        return records

    def save_records(self, records, table, primary_keys):
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, table, primary_keys)


if __name__ == '__main__':
    valuation_service = ValuationServiceImpl()
    valuation_service.collect_industry(datetime.strptime('2020-04-17', '%Y-%m-%d'))
