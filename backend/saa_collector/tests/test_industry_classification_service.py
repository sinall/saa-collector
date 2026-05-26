import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from django.test import TestCase

from saa_collector.services.common.industry_classification_service import (
    CsrcIndustryClassificationService,
)
from saa_collector.services.common.valuation_service import ValuationServiceImpl


class CsrcIndustryClassificationServiceTest(TestCase):
    @patch('saa_collector.services.common.valuation_service.requests.get')
    @patch('saa_collector.services.common.valuation_service.get_trade_day_before_with_offset')
    def test_query_records_parses_csrc_classification_tree(self, trade_day_before_mock, get_mock):
        trade_day_before_mock.return_value = datetime(2026, 5, 22).date()
        payload = [
            {
                'id': 4,
                'plate': '深沪京市场',
                'sylItemVoList': [
                    {'tc': 'N', 'tl': '1', 'tn': '水利、环境和公共设施管理业'},
                    {'tc': 'N79', 'tl': '2', 'tn': '水利管理业'},
                    {'tc': 'S', 'tl': '1', 'tn': '综合'},
                    {'tc': 'S91', 'tl': '2', 'tn': '综合'},
                    {'tc': '', 'tl': '2', 'tn': '法律声明'},
                ],
            },
        ]
        response = MagicMock(
            url='https://www.cnindex.com.cn/syl/2026-05-22/crsc.json',
            status_code=200,
            content=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json;charset=UTF-8'},
        )
        response.json.return_value = payload
        get_mock.return_value = response

        valuation_service = ValuationServiceImpl.__new__(ValuationServiceImpl)
        valuation_service._logger = MagicMock()
        valuation_service.host = 'www.cnindex.com.cn'
        service = CsrcIndustryClassificationService.__new__(CsrcIndustryClassificationService)
        service.valuation_service = valuation_service
        records = service.query_records(datetime(2026, 5, 25))

        self.assertEqual(records, [
            {
                'id': 'N',
                'name': '水利、环境和公共设施管理业',
                'parent_id': None,
            },
            {
                'id': 'N79',
                'name': '水利管理业',
                'parent_id': 'N',
            },
        ])
