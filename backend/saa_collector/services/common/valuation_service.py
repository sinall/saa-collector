# -*- coding: utf-8 -*-
import hashlib
import json
import logging
import re
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode
import mysql.connector
import pandas as pd
import requests
import xlrd
from xlrd.biffh import XLRDError

from saa_collector.date_expressions import get_trade_day_before_with_offset
from saa_collector.services.collect_execution_context import get_collect_execution_context
from saa_collector.services.abstract.valuation_service import ValuationService
from saa_collector.services.common.config_service import ConfigService
from saa_collector.third_party.api_cache import DjangoExternalApiCacheStore
from saa_collector.utils.db import DB


CNINDEX_CACHE_PROVIDER = 'cnindex'
CNINDEX_CACHE_SCHEMA_VERSION = 'cnindex-raw-v1'
CNINDEX_CACHE_DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60


class CachedRequestsResponse:
    def __init__(self, *, url, status_code, content, headers):
        self.url = url
        self.status_code = status_code
        self.content = content
        self.headers = headers

    def json(self):
        content_type = self.headers.get('Content-Type') or self.headers.get('content-type') or ''
        encoding = 'utf-8'
        match = re.search(r'charset=([^;]+)', content_type, re.IGNORECASE)
        if match:
            encoding = match.group(1).strip()
        return json.loads(self.content.decode(encoding, errors='replace'))


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
        response, cache_context = self._request_cnindex(
            api_name='sylExcelDowload',
            method='POST',
            url=url,
            params=payload,
            request_body=request_body,
            request_func=lambda: requests.post(url, data=payload),
        )
        self._logger.info(
            'Downloaded {} successfully:\n{}\nrequest_body={} cache_key={}'.format(
                response.url,
                self._format_response_headers(response),
                request_body,
                cache_context.get('cache_key'),
            )
        )
        try:
            book = xlrd.open_workbook(file_contents=response.content, encoding_override="GB2312")
        except XLRDError as exc:
            response_text = response.content.decode('utf-8', errors='replace')
            raise ValueError(
                'Failed to parse cnindex board valuation response: '
                'url={} status_code={} response_headers=\n{}\ncontent_type={} request_body={} response_length={} response_body={!r} cache_key={}'.format(
                    response.url,
                    response.status_code,
                    self._format_response_headers(response),
                    response.headers.get('Content-Type'),
                    request_body,
                    len(response.content),
                    response_text,
                    cache_context.get('cache_key'),
                )
            ) from exc
        xls_file = pd.ExcelFile(BytesIO(response.content))
        return response, cache_context, request_body, book, xls_file

    def query_board_records(self, date):
        response, cache_context, request_body, book, xls_file = self._download_cnindex_workbook(date)
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
                    'sheet_name={} columns={} cache_key={}'.format(
                        response.url,
                        response.status_code,
                        self._format_response_headers(response),
                        response.headers.get('Content-Type'),
                        request_body,
                        sheet_name,
                        list(sheet.columns),
                        cache_context.get('cache_key'),
                    )
                )
            summary_row = summary_rows.iloc[0]
            records.append(self._build_board_summary_record(sheet_title, summary_row, date))
        return records

    def _download_cnindex_crsc_payload(self, date, payload_description='cnindex industry valuation'):
        check_date = get_trade_day_before_with_offset(date.date(), 1)
        if check_date is None:
            raise ValueError(f'No trade day found before {date.date()}')

        date_str = check_date.strftime('%Y-%m-%d')
        url = 'https://{}/syl/{}/crsc.json'.format(self.host, date_str)
        response, cache_context = self._request_cnindex(
            api_name='crsc.json',
            method='GET',
            url=url,
            params={'date': date_str},
            request_func=lambda: requests.get(url),
        )
        self._logger.info(
            'Downloaded {} successfully:\n{}\ncache_key={}'.format(
                response.url,
                self._format_response_headers(response),
                cache_context.get('cache_key'),
            )
        )
        try:
            return response.json()
        except ValueError as exc:
            response_text = response.content.decode('utf-8', errors='replace')
            raise ValueError(
                'Failed to parse {} response: '
                'url={} status_code={} response_headers=\n{}\ncontent_type={} response_length={} response_body={!r} cache_key={}'.format(
                    payload_description,
                    response.url,
                    response.status_code,
                    self._format_response_headers(response),
                    response.headers.get('Content-Type'),
                    len(response.content),
                    response_text,
                    cache_context.get('cache_key'),
                )
            ) from exc

    def query_industry_records(self, date):
        payload = self._download_cnindex_crsc_payload(date)

        plate = None
        for block in payload:
            if block.get('id') == 4 or block.get('plate') == '深沪京市场':
                plate = block
                break
        if plate is None:
            raise ValueError(
                'cnindex industry valuation payload missing plate 4: '
                'url={} status_code={} response_headers=\n{}\ncontent_type={} cache_key={}'.format(
                    response.url,
                    response.status_code,
                    self._format_response_headers(response),
                    response.headers.get('Content-Type'),
                    cache_context.get('cache_key'),
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

    def _request_cnindex(self, *, api_name, method, url, params, request_func, request_body=''):
        cache_context = self._build_cnindex_cache_context(
            api_name=api_name,
            method=method,
            url=url,
            params=params,
            request_body=request_body,
        )
        cached_response = self._get_cached_cnindex_response(cache_context)
        if cached_response is not None:
            return cached_response, cache_context

        response = request_func()
        self._store_cnindex_response(cache_context, response)
        return response, cache_context

    def _build_cnindex_cache_context(self, *, api_name, method, url, params, request_body=''):
        try:
            execution_context = get_collect_execution_context()
        except Exception:
            execution_context = {}

        enabled = bool(execution_context.get('api_cache_enabled'))
        bypass = bool(execution_context.get('api_cache_bypass', False))
        ttl_seconds = execution_context.get('api_cache_ttl_seconds')

        if not enabled:
            return {'enabled': False}
        if bypass:
            self._logger.info('External API cache bypassed: provider=cnindex api=%s', api_name)
            return {'enabled': False}
        if ttl_seconds is None:
            ttl_seconds = CNINDEX_CACHE_DEFAULT_TTL_SECONDS
        try:
            ttl_seconds = int(ttl_seconds)
        except (TypeError, ValueError):
            self._logger.warning('Invalid cnindex API cache ttl override: api=%s ttl=%r', api_name, ttl_seconds)
            return {'enabled': False}
        if ttl_seconds <= 0:
            return {'enabled': False}

        canonical_call = {
            'provider': CNINDEX_CACHE_PROVIDER,
            'api': api_name,
            'method': method,
            'url': url,
            'params': self._normalize_cache_params(params),
            'version': CNINDEX_CACHE_SCHEMA_VERSION,
        }
        canonical_json = json.dumps(
            canonical_call, sort_keys=True, separators=(',', ':'), ensure_ascii=True
        )
        return {
            'enabled': True,
            'provider': CNINDEX_CACHE_PROVIDER,
            'api_name': api_name,
            'cache_key': hashlib.sha256(canonical_json.encode('utf-8')).hexdigest(),
            'canonical_call': canonical_call,
            'params': canonical_call['params'],
            'method': method,
            'url': url,
            'request_body': request_body,
            'schema_version': CNINDEX_CACHE_SCHEMA_VERSION,
            'ttl_seconds': ttl_seconds,
        }

    def _normalize_cache_params(self, params):
        return {
            key: self._normalize_cache_value(value)
            for key, value in sorted((params or {}).items())
        }

    def _normalize_cache_value(self, value):
        if hasattr(value, 'strftime'):
            return value.strftime('%Y-%m-%d')
        return value

    def _get_cached_cnindex_response(self, cache_context):
        if not cache_context.get('enabled'):
            return None
        try:
            cached = DjangoExternalApiCacheStore().get_response(
                provider=cache_context['provider'],
                api_name=cache_context['api_name'],
                cache_key=cache_context['cache_key'],
            )
        except Exception as exc:
            self._logger.warning('External API cache read failed: provider=cnindex api=%s error=%s', cache_context['api_name'], exc)
            return None
        if cached is None:
            return None
        headers = dict(cached.headers or {})
        if cached.content_type and 'Content-Type' not in headers:
            headers['Content-Type'] = cached.content_type
        if cached.filename and 'Content-disposition' not in headers and 'Content-Disposition' not in headers:
            headers['Content-disposition'] = f'attachment;filename={cached.filename}'
        return CachedRequestsResponse(
            url=cache_context['url'],
            status_code=cached.status_code or 200,
            content=cached.body,
            headers=headers,
        )

    def _store_cnindex_response(self, cache_context, response):
        if not cache_context.get('enabled'):
            return
        try:
            DjangoExternalApiCacheStore().set_response(
                provider=cache_context['provider'],
                api_name=cache_context['api_name'],
                cache_key=cache_context['cache_key'],
                canonical_call=cache_context['canonical_call'],
                params=cache_context['params'],
                body=response.content,
                content_type=response.headers.get('Content-Type', ''),
                filename=self._extract_response_filename(response) or '',
                status_code=response.status_code,
                headers=dict(response.headers),
                schema_version=cache_context['schema_version'],
                ttl_seconds=cache_context['ttl_seconds'],
                request_method=cache_context['method'],
                request_url=cache_context['url'],
                request_body=cache_context['request_body'],
            )
        except Exception as exc:
            self._logger.warning('External API cache write failed: provider=cnindex api=%s error=%s', cache_context['api_name'], exc)

    def _format_response_headers(self, response):
        lines = [f'HTTP/1.1 {response.status_code} {response.status_code}']
        for key, value in response.headers.items():
            lines.append(f'{key}: {value}')
        return '\n'.join(lines)

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
