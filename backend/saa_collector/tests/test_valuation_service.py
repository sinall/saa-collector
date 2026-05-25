import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pandas as pd
from django.test import TestCase
from xlrd.biffh import XLRDError

from saa_collector.services.common.valuation_service import ValuationServiceImpl


class ValuationServiceRequestTest(TestCase):
    @patch('saa_collector.services.common.valuation_service.requests.post')
    @patch('saa_collector.services.common.valuation_service.get_trade_day_before_with_offset')
    def test_query_board_records_uses_https_form_post(
        self, trade_day_before_mock, post_mock
    ):
        service = ValuationServiceImpl.__new__(ValuationServiceImpl)
        service._logger = MagicMock()
        service.host = 'www.cnindex.com.cn'
        trade_day_before_mock.return_value = datetime(2026, 5, 22).date()
        fixture_path = Path(__file__).resolve().parent / 'fixtures' / 'cnindex' / 'crsc_ch_2026-05-22.xls'

        response = MagicMock(
            url='https://www.cnindex.com.cn/sylExcelDowload',
            status_code=200,
            content=fixture_path.read_bytes(),
            headers={
                'Date': 'Mon, 25 May 2026 12:17:08 GMT',
                'Content-Type': 'application/vnd.ms-excel;charset=UTF-8',
                'Transfer-Encoding': 'chunked',
                'Connection': 'keep-alive',
                'Server': 'openresty',
                'X-Frame-Options': 'SAMEORIGIN',
                'Set-Cookie': 'ctx=',
                'Content-disposition': 'attachment;filename=crsc_ch_2026-05-22.xls',
                'X-CCDN-Origin-Time': '62',
                'via': 'CHN-ZJwenzhou-AREACT1-CACHE66[117],CHN-ZJwenzhou-AREACT1-CACHE4[80,TCP_MISS,115],CHN-JSwuxi-GLOBAL2-CACHE103[66],CHN-JSwuxi-GLOBAL2-CACHE4[62,TCP_MISS,64]',
                'x-hcs-proxy-type': '0',
                'X-CCDN-CacheTTL': '0',
                'X-CCDN-REQ-ID-46B1': '61b0b5983a9ed0c7202e2c79172cced7',
                'Cache-Control': 'max-age=60',
            },
        )
        post_mock.return_value = response

        with TemporaryDirectory() as tmpdir:
            with patch('saa_collector.services.common.valuation_service.CNINDEX_DEBUG_DIR', Path(tmpdir)):
                records = service.query_board_records(datetime(2026, 5, 25))

                post_mock.assert_called_once_with(
                    'https://www.cnindex.com.cn/sylExcelDowload',
                    data={
                        'checkDate': '2026-05-22',
                        'category': 'crsc_ch',
                    },
                )
                service._logger.info.assert_any_call(
                    "Downloaded https://www.cnindex.com.cn/sylExcelDowload successfully:\n"
                    "HTTP/1.1 200 200\n"
                    "Date: Mon, 25 May 2026 12:17:08 GMT\n"
                    "Content-Type: application/vnd.ms-excel;charset=UTF-8\n"
                    "Transfer-Encoding: chunked\n"
                    "Connection: keep-alive\n"
                    "Server: openresty\n"
                    "X-Frame-Options: SAMEORIGIN\n"
                    "Set-Cookie: ctx=\n"
                    "Content-disposition: attachment;filename=crsc_ch_2026-05-22.xls\n"
                    "X-CCDN-Origin-Time: 62\n"
                    "via: CHN-ZJwenzhou-AREACT1-CACHE66[117],CHN-ZJwenzhou-AREACT1-CACHE4[80,TCP_MISS,115],CHN-JSwuxi-GLOBAL2-CACHE103[66],CHN-JSwuxi-GLOBAL2-CACHE4[62,TCP_MISS,64]\n"
                    "x-hcs-proxy-type: 0\n"
                    "X-CCDN-CacheTTL: 0\n"
                    "X-CCDN-REQ-ID-46B1: 61b0b5983a9ed0c7202e2c79172cced7\n"
                    "Cache-Control: max-age=60\n"
                    "request_body=checkDate=2026-05-22&category=crsc_ch\n"
                    f"response_dump_path={tmpdir}/crsc_ch_2026-05-22.xls"
                )
                self.assertEqual(Path(tmpdir, 'crsc_ch_2026-05-22.xls').read_bytes(), fixture_path.read_bytes())
                self.assertEqual([record['board'] for record in records], [
                    '深圳市场',
                    '深圳主板',
                    '创业板',
                    '深沪京市场',
                    '国证1000',
                    '国证2000',
                ])
                self.assertEqual(records[0]['pe'], 39.38)
                self.assertEqual(records[0]['pe_ttm'], 36.21)
                self.assertIsNone(records[0]['pb'])
                self.assertEqual(records[0]['total'], 3)
                self.assertIsNone(records[2]['pe'])
                self.assertEqual(records[-1]['pe'], 43.55)
                self.assertEqual(records[-1]['pe_ttm'], 40.86)
                self.assertEqual(records[-1]['total'], 3)

    @patch('saa_collector.services.common.valuation_service.requests.get')
    @patch('saa_collector.services.common.valuation_service.get_trade_day_before_with_offset')
    def test_query_industry_records_uses_crsc_json(
        self, trade_day_before_mock, get_mock
    ):
        service = ValuationServiceImpl.__new__(ValuationServiceImpl)
        service._logger = MagicMock()
        service.host = 'www.cnindex.com.cn'
        trade_day_before_mock.return_value = datetime(2026, 5, 22).date()

        payload = [
            {
                'id': 4,
                'plate': '深沪京市场',
                'sylItemVoList': [
                    {
                        'tc': 'A',
                        'tl': '1',
                        'tt': '008001',
                        'tn': '农、林、牧、渔业',
                        'ca': '46',
                        'swer': '19.29',
                        'dwer': '27.91',
                        'smer': '49.46',
                        'dmer': '46.18',
                        'date': '2026-05-22',
                        'enPlate': 'SZ&SH&BJ Market',
                        'enTn': 'Agriculture',
                    },
                    {
                        'tc': 'A01',
                        'tl': '2',
                        'tt': '008001',
                        'tn': '农业',
                        'ca': '9',
                        'swer': '28.02',
                        'dwer': '22.5',
                        'smer': '31.44',
                        'dmer': '21.74',
                        'date': '2026-05-22',
                        'enPlate': 'SZ&SH&BJ Market',
                        'enTn': 'Agriculture',
                    },
                    {
                        'tc': 'S',
                        'tl': '1',
                        'tt': '008001',
                        'tn': '综合',
                        'ca': '7',
                        'swer': 'NaN',
                        'dwer': 'NaN',
                        'smer': 'NaN',
                        'dmer': 'NaN',
                        'date': '2026-05-22',
                        'enPlate': 'SZ&SH&BJ Market',
                        'enTn': 'Composite',
                    },
                    {
                        'tc': 'S91',
                        'tl': '2',
                        'tt': '008001',
                        'tn': '综合',
                        'ca': '7',
                        'swer': 'NaN',
                        'dwer': 'NaN',
                        'smer': 'NaN',
                        'dmer': 'NaN',
                        'date': '2026-05-22',
                        'enPlate': 'SZ&SH&BJ Market',
                        'enTn': 'Composite',
                    },
                ],
            },
        ]
        response = MagicMock(
            url='https://www.cnindex.com.cn/syl/2026-05-22/crsc.json',
            status_code=200,
            content=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={
                'Content-Type': 'application/json;charset=UTF-8',
            },
        )
        response.json.return_value = payload
        get_mock.return_value = response

        with TemporaryDirectory() as tmpdir:
            with patch('saa_collector.services.common.valuation_service.CNINDEX_DEBUG_DIR', Path(tmpdir)):
                records = service.query_industry_records(datetime(2026, 5, 25))

                get_mock.assert_called_once_with('https://www.cnindex.com.cn/syl/2026-05-22/crsc.json')
                self.assertEqual(Path(tmpdir, 'cnindex_industry_2026-05-22.json').read_bytes(), response.content)
                self.assertEqual(records, [
                    {
                        'industry_classification_id': 'A',
                        'pe': 19.29,
                        'pe_ttm': 27.91,
                        'pb': None,
                        'dividend_rate': None,
                        'total': 46,
                        'total_of_loss': None,
                        'total_of_negative_equity': None,
                        'total_of_no_dividend': None,
                        'report_date': '2026-05-25',
                    },
                    {
                        'industry_classification_id': 'A01',
                        'pe': 28.02,
                        'pe_ttm': 22.5,
                        'pb': None,
                        'dividend_rate': None,
                        'total': 9,
                        'total_of_loss': None,
                        'total_of_negative_equity': None,
                        'total_of_no_dividend': None,
                        'report_date': '2026-05-25',
                    },
                ])

    @patch('saa_collector.services.common.valuation_service.requests.get')
    @patch('saa_collector.services.common.valuation_service.get_trade_day_before_with_offset')
    def test_query_industry_records_keeps_cnindex_industry_ids_without_classification_upsert(
        self, trade_day_before_mock, get_mock
    ):
        service = ValuationServiceImpl.__new__(ValuationServiceImpl)
        service._logger = MagicMock()
        service.host = 'www.cnindex.com.cn'
        trade_day_before_mock.return_value = datetime(2026, 5, 25).date()

        payload = [
            {
                'id': 4,
                'plate': '深沪京市场',
                'sylItemVoList': [
                    {
                        'tc': 'N',
                        'tl': '1',
                        'tn': '水利、环境和公共设施管理业',
                        'ca': '18',
                        'swer': 'NaN',
                        'dwer': 'NaN',
                    },
                    {
                        'tc': 'N79',
                        'tl': '2',
                        'tn': '公共设施管理业',
                        'ca': '0',
                        'swer': 'NaN',
                        'dwer': 'NaN',
                    },
                ],
            },
        ]
        response = MagicMock(
            url='https://www.cnindex.com.cn/syl/2026-05-25/crsc.json',
            status_code=200,
            content=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json;charset=UTF-8'},
        )
        response.json.return_value = payload
        get_mock.return_value = response

        with TemporaryDirectory() as tmpdir:
            with patch('saa_collector.services.common.valuation_service.CNINDEX_DEBUG_DIR', Path(tmpdir)):
                records = service.query_industry_records(datetime(2026, 5, 26))

        self.assertEqual(records, [
            {
                'industry_classification_id': 'N',
                'pe': None,
                'pe_ttm': None,
                'pb': None,
                'dividend_rate': None,
                'total': 18,
                'total_of_loss': None,
                'total_of_negative_equity': None,
                'total_of_no_dividend': None,
                'report_date': '2026-05-26',
            },
            {
                'industry_classification_id': 'N79',
                'pe': None,
                'pe_ttm': None,
                'pb': None,
                'dividend_rate': None,
                'total': 0,
                'total_of_loss': None,
                'total_of_negative_equity': None,
                'total_of_no_dividend': None,
                'report_date': '2026-05-26',
            },
        ])

    def test_collect_industry_saves_only_valuation_records(self):
        service = ValuationServiceImpl.__new__(ValuationServiceImpl)
        service._logger = MagicMock()
        service.query_industry_records = MagicMock(return_value=
            [
                {
                    'industry_classification_id': 'N79',
                    'pe': None,
                    'pe_ttm': None,
                    'pb': None,
                    'dividend_rate': None,
                    'total': 0,
                    'total_of_loss': None,
                    'total_of_negative_equity': None,
                    'total_of_no_dividend': None,
                    'report_date': '2026-05-26',
                },
            ]
        )
        service.save_records = MagicMock()

        service.collect_industry(datetime(2026, 5, 26))

        service.save_records.assert_called_once()
        self.assertEqual(service.save_records.call_args.args[1:], (
            'saa_industry_valuation_levels',
            ['industry_classification_id', 'report_date'],
        ))

    @patch('saa_collector.services.common.valuation_service.requests.post')
    @patch('saa_collector.services.common.valuation_service.xlrd.open_workbook', side_effect=XLRDError('Expected BOF record; found b\'{"code":\''))
    @patch('saa_collector.services.common.valuation_service.get_trade_day_before_with_offset')
    def test_query_board_records_raises_contextual_error_when_response_is_json(
        self, trade_day_before_mock, open_workbook_mock, post_mock
    ):
        service = ValuationServiceImpl.__new__(ValuationServiceImpl)
        service._logger = MagicMock()
        service.host = 'www.cnindex.com.cn'
        trade_day_before_mock.return_value = datetime(2026, 5, 22).date()

        response = MagicMock(
            url='https://www.cnindex.com.cn/sylExcelDowload',
            status_code=200,
            content=b'{"code":400,"message":"bad request"}',
            headers={
                'Content-Type': 'application/json',
                'Content-disposition': 'attachment;filename=bad_request.json',
            },
        )
        post_mock.return_value = response

        with TemporaryDirectory() as tmpdir:
            with patch('saa_collector.services.common.valuation_service.CNINDEX_DEBUG_DIR', Path(tmpdir)):
                with self.assertRaisesRegex(
                    ValueError,
                    r"Failed to parse cnindex board valuation response: url=https://www\.cnindex\.com\.cn/sylExcelDowload status_code=200 response_headers=\nHTTP/1\.1 200 200\nContent-Type: application/json\nContent-disposition: attachment;filename=bad_request\.json\ncontent_type=application/json request_body=checkDate=2026-05-22&category=crsc_ch response_length=36 response_body='.*\{\"code\":400,\"message\":\"bad request\"\}' response_dump_path=.*/bad_request\.json",
                ):
                    service.query_board_records(datetime(2026, 5, 25))

                service._logger.info.assert_any_call(
                    "Downloaded https://www.cnindex.com.cn/sylExcelDowload successfully:\n"
                    "HTTP/1.1 200 200\n"
                    "Content-Type: application/json\n"
                    "Content-disposition: attachment;filename=bad_request.json\n"
                    "request_body=checkDate=2026-05-22&category=crsc_ch\n"
                    f"response_dump_path={tmpdir}/bad_request.json"
                )
                open_workbook_mock.assert_called_once()
                self.assertEqual(Path(tmpdir, 'bad_request.json').read_bytes(), b'{"code":400,"message":"bad request"}')

    @patch('saa_collector.services.common.valuation_service.requests.post')
    @patch('saa_collector.services.common.valuation_service.xlrd.open_workbook')
    @patch('saa_collector.services.common.valuation_service.pd.ExcelFile')
    @patch('saa_collector.services.common.valuation_service.get_trade_day_before_with_offset')
    def test_query_board_records_logs_sheet_snapshot_when_summary_row_is_missing(
        self, trade_day_before_mock, excel_file_mock, open_workbook_mock, post_mock
    ):
        service = ValuationServiceImpl.__new__(ValuationServiceImpl)
        service._logger = MagicMock()
        service.host = 'www.cnindex.com.cn'
        trade_day_before_mock.return_value = datetime(2026, 5, 22).date()

        response = MagicMock(
            url='https://www.cnindex.com.cn/sylExcelDowload',
            status_code=200,
            content=b'fake-xls-bytes',
            headers={
                'Date': 'Mon, 25 May 2026 12:17:08 GMT',
                'Content-Type': 'application/vnd.ms-excel;charset=UTF-8',
                'Content-disposition': 'attachment;filename=crsc_ch_2026-05-22.xls',
            },
        )
        post_mock.return_value = response

        columns = pd.MultiIndex.from_tuples([
            ('行业编码', '门类'),
            ('行业编码', '大类'),
            ('行业名称', 'Unnamed: 2_level_1'),
            ('公司数量', 'Unnamed: 3_level_1'),
            ('静态市盈率', '加权平均'),
            ('静态市盈率', '中位数'),
            ('滚动市盈率', '加权平均'),
            ('滚动市盈率', '中位数'),
        ])
        sheet = pd.DataFrame([
            ['A', None, ' 农、林、牧、渔业', 1, 1.0, 1.0, 1.0, 1.0],
        ], columns=columns)
        book = MagicMock()
        book.sheet_names.return_value = ['sheet1']
        book.sheet_by_name.return_value.cell_value.return_value = '分类标准：中上协行业分类                统计板块：测试板块                    更新日期：'
        excel_file_mock.return_value.sheet_names = ['sheet1']
        excel_file_mock.return_value.parse.return_value = sheet
        open_workbook_mock.return_value = book

        with TemporaryDirectory() as tmpdir:
            with patch('saa_collector.services.common.valuation_service.CNINDEX_DEBUG_DIR', Path(tmpdir)):
                with self.assertRaisesRegex(
                    ValueError,
                    r"cnindex board valuation sheet missing summary row: url=https://www\.cnindex\.com\.cn/sylExcelDowload status_code=200 response_headers=\nHTTP/1\.1 200 200\nDate: Mon, 25 May 2026 12:17:08 GMT\nContent-Type: application/vnd\.ms-excel;charset=UTF-8\nContent-disposition: attachment;filename=crsc_ch_2026-05-22\.xls\ncontent_type=application/vnd\.ms-excel;charset=UTF-8 request_body=checkDate=2026-05-22&category=crsc_ch sheet_name=sheet1 columns=\[.*\] response_dump_path=.*/crsc_ch_2026-05-22\.xls",
                ):
                    service.query_board_records(datetime(2026, 5, 25))

                service._logger.info.assert_any_call(
                    "cnindex board sheet snapshot: sheet_name=sheet1 rows=1 columns=8 summary_rows=0 first_codes=['A']"
                )
                self.assertEqual(Path(tmpdir, 'crsc_ch_2026-05-22.xls').read_bytes(), b'fake-xls-bytes')
