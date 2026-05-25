# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
import mysql.connector
import pandas as pd
import requests
import xlrd
from xlrd.biffh import XLRDError

from saa_collector.date_expressions import get_trade_day_before_with_offset
from saa_collector.services.abstract.valuation_service import ValuationService
from saa_collector.services.common.config_service import ConfigService
from saa_collector.utils.db import DB


CNINDEX_DEBUG_DIR = Path('/tmp/saa_collector/cnindex')


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

    def _download_cnindex_workbook(self, date):
        check_date = get_trade_day_before_with_offset(date.date(), 1)
        if check_date is None:
            raise ValueError(f'No trade day found before {date.date()}')

        url = 'https://{}/sylExcelDowload'.format(self.host)
        payload = {
            'checkDate': check_date.strftime('%Y-%m-%d'),
            'category': 'crsc_ch',
        }
        request_body = urlencode(payload)
        response = requests.post(url, data=payload)
        response_dump_path = self._dump_cnindex_response(response, check_date)
        self._logger.info(
            'Downloaded {} successfully:\n{}\nrequest_body={}\nresponse_dump_path={}'.format(
                response.url,
                self._format_response_headers(response),
                request_body,
                response_dump_path,
            )
        )
        try:
            book = xlrd.open_workbook(file_contents=response.content, encoding_override="GB2312")
        except XLRDError as exc:
            response_text = response.content.decode('utf-8', errors='replace')
            raise ValueError(
                'Failed to parse cnindex board valuation response: '
                'url={} status_code={} response_headers=\n{}\ncontent_type={} request_body={} response_length={} response_body={!r} response_dump_path={}'.format(
                    response.url,
                    response.status_code,
                    self._format_response_headers(response),
                    response.headers.get('Content-Type'),
                    request_body,
                    len(response.content),
                    response_text,
                    response_dump_path,
                )
            ) from exc
        xls_file = pd.ExcelFile(BytesIO(response.content))
        return response, response_dump_path, request_body, book, xls_file

    def query_board_records(self, date):
        response, response_dump_path, request_body, book, xls_file = self._download_cnindex_workbook(date)
        records = []
        for sheet_name in book.sheet_names():
            sheet_title = self._extract_cnindex_sheet_title(book.sheet_by_name(sheet_name).cell_value(2, 0))
            sheet = xls_file.parse(sheet_name, header=[3, 4])
            summary_rows = sheet[sheet[('行业编码', '门类')] == 'S']
            self._logger.info(
                'cnindex board sheet snapshot: sheet_name={} rows={} columns={} summary_rows={} first_codes={}'.format(
                    sheet_name,
                    sheet.shape[0],
                    sheet.shape[1],
                    len(summary_rows),
                    self._extract_sheet_code_sample(sheet),
                )
            )
            if summary_rows.empty:
                raise ValueError(
                    'cnindex board valuation sheet missing summary row: '
                    'url={} status_code={} response_headers=\n{}\ncontent_type={} request_body={} '
                    'sheet_name={} columns={} response_dump_path={}'.format(
                        response.url,
                        response.status_code,
                        self._format_response_headers(response),
                        response.headers.get('Content-Type'),
                        request_body,
                        sheet_name,
                        list(sheet.columns),
                        response_dump_path,
                    )
                )
            summary_row = summary_rows.iloc[0]
            records.append(self._build_board_summary_record(sheet_title, summary_row, date))
        return records

    def query_industry_records(self, date):
        check_date = get_trade_day_before_with_offset(date.date(), 1)
        if check_date is None:
            raise ValueError(f'No trade day found before {date.date()}')

        date_str = check_date.strftime('%Y-%m-%d')
        url = 'https://{}/syl/{}/crsc.json'.format(self.host, date_str)
        response = requests.get(url)
        response_dump_path = self._dump_cnindex_response(
            response,
            check_date,
            default_filename=f'cnindex_industry_{date_str}.json',
        )
        self._logger.info(
            'Downloaded {} successfully:\n{}\nresponse_dump_path={}'.format(
                response.url,
                self._format_response_headers(response),
                response_dump_path,
            )
        )
        try:
            payload = response.json()
        except ValueError as exc:
            response_text = response.content.decode('utf-8', errors='replace')
            raise ValueError(
                'Failed to parse cnindex industry valuation response: '
                'url={} status_code={} response_headers=\n{}\ncontent_type={} response_length={} response_body={!r} response_dump_path={}'.format(
                    response.url,
                    response.status_code,
                    self._format_response_headers(response),
                    response.headers.get('Content-Type'),
                    len(response.content),
                    response_text,
                    response_dump_path,
                )
            ) from exc

        plate = None
        for block in payload:
            if block.get('id') == 4 or block.get('plate') == '深沪京市场':
                plate = block
                break
        if plate is None:
            raise ValueError(
                'cnindex industry valuation payload missing plate 4: '
                'url={} status_code={} response_headers=\n{}\ncontent_type={} response_dump_path={}'.format(
                    response.url,
                    response.status_code,
                    self._format_response_headers(response),
                    response.headers.get('Content-Type'),
                    response_dump_path,
                )
            )

        records = []
        for item in plate.get('sylItemVoList', []):
            industry_classification_id = self._normalize_cnindex_value(item.get('tc'))
            if not industry_classification_id:
                continue
            industry_name = self._normalize_cnindex_value(item.get('tn'))
            if industry_name and '法律声明' in str(industry_name):
                continue
            if industry_classification_id == 'S' or industry_classification_id == 'S91':
                continue

            industry_classification_id = str(industry_classification_id).strip()
            records.append({
                'industry_classification_id': industry_classification_id,
                'pe': self._normalize_cnindex_value(item.get('swer')),
                'pe_ttm': self._normalize_cnindex_value(item.get('dwer')),
                'pb': None,
                'dividend_rate': None,
                'total': self._normalize_cnindex_value(item.get('ca')),
                'total_of_loss': None,
                'total_of_negative_equity': None,
                'total_of_no_dividend': None,
                'report_date': date.strftime('%Y-%m-%d'),
            })
        return records

    def save_records(self, records, table, primary_keys):
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, table, primary_keys)

    def _format_response_headers(self, response):
        lines = [f'HTTP/1.1 {response.status_code} {response.status_code}']
        for key, value in response.headers.items():
            lines.append(f'{key}: {value}')
        return '\n'.join(lines)

    def _dump_cnindex_response(self, response, check_date, default_filename=None):
        response_filename = self._extract_response_filename(response)
        if not response_filename:
            response_filename = default_filename or f'cnindex_board_{check_date}.xls'
        dump_dir = CNINDEX_DEBUG_DIR
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump_path = dump_dir / response_filename
        dump_path.write_bytes(response.content)
        return str(dump_path)

    def _extract_response_filename(self, response):
        disposition = response.headers.get('Content-disposition') or response.headers.get('Content-Disposition')
        if not disposition:
            return None
        match = re.search(r'filename="?([^";]+)"?', disposition, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _extract_cnindex_sheet_title(self, raw_title):
        if not raw_title:
            return ''

        text = str(raw_title).strip()
        patterns = [
            r'统计板块：(.+?)\s+更新日期：',
            r'指数：(.+?)\s+更新日期：',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return text

    def _build_board_summary_record(self, board_name, summary_row, date):
        return {
            'board': board_name,
            'pe': self._get_cnindex_metric(summary_row, '静态市盈率', '加权平均'),
            'pe_ttm': self._get_cnindex_metric(summary_row, '滚动市盈率', '加权平均'),
            'pb': None,
            'dividend_rate': None,
            'total': self._get_cnindex_metric(summary_row, '公司数量'),
            'total_of_loss': None,
            'total_of_negative_equity': None,
            'total_of_no_dividend': None,
            'report_date': date.strftime('%Y-%m-%d'),
        }

    def _extract_sheet_code_sample(self, sheet):
        codes = []
        for column in [('行业编码', '门类'), ('行业编码', '大类')]:
            if column not in sheet.columns:
                continue
            for value in sheet[column].head(3).tolist():
                normalized = self._normalize_cnindex_value(value)
                if normalized:
                    codes.append(str(normalized).strip())
        return codes[:3]

    def _build_industry_records_from_sheet(self, board_name, sheet, date):
        records = []
        name_column = ('行业名称', 'Unnamed: 2_level_1') if ('行业名称', 'Unnamed: 2_level_1') in sheet.columns else ('行业名称', sheet.columns[2][1])

        for _, row in sheet.iterrows():
            top_code = self._normalize_cnindex_value(row[('行业编码', '门类')])
            sub_code = self._normalize_cnindex_value(row[('行业编码', '大类')])
            industry_name = self._normalize_cnindex_value(row[name_column])

            if not top_code and not sub_code:
                continue
            if industry_name and '法律声明' in str(industry_name):
                continue
            if top_code == 'S' or sub_code == 'S91':
                continue

            industry_classification_id = sub_code or top_code
            if not industry_classification_id:
                continue

            records.append({
                'industry_classification_id': str(industry_classification_id).strip(),
                'pe': self._get_cnindex_metric(row, '静态市盈率', '加权平均'),
                'pe_ttm': self._get_cnindex_metric(row, '滚动市盈率', '加权平均'),
                'pb': None,
                'dividend_rate': None,
                'total': self._get_cnindex_metric(row, '公司数量'),
                'total_of_loss': None,
                'total_of_negative_equity': None,
                'total_of_no_dividend': None,
                'report_date': date.strftime('%Y-%m-%d'),
            })
        return records

    def _get_cnindex_metric(self, row, top_key, sub_key=None):
        value = row[top_key]
        if isinstance(value, pd.Series):
            if sub_key and sub_key in value.index:
                value = value[sub_key]
            else:
                non_null_values = [item for item in value.tolist() if not pd.isna(item)]
                value = non_null_values[0] if non_null_values else None
        return self._normalize_cnindex_value(value)

    def _normalize_cnindex_value(self, value):
        if pd.isna(value):
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if value.upper() in {'NA', 'N/A', 'NULL', 'NONE', 'NAN'}:
                return None
            if re.fullmatch(r'-?\d+', value):
                return int(value)
            if re.fullmatch(r'-?\d+\.\d+', value):
                number = float(value)
                return int(number) if number.is_integer() else number
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value


if __name__ == '__main__':
    valuation_service = ValuationServiceImpl()
    valuation_service.collect_industry(datetime.strptime('2020-04-17', '%Y-%m-%d'))
