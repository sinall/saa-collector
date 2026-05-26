# -*- coding: utf-8 -*-
import logging
from datetime import datetime

import mysql.connector

from saa_collector.services.common.config_service import ConfigService
from saa_collector.services.common.valuation_service import ValuationServiceImpl
from saa_collector.utils.db import DB


class CsrcIndustryClassificationService:
    def __init__(self):
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.db_config = self.config_service.get_db_config()
        self.valuation_service = ValuationServiceImpl()

    def collect(self, date=None):
        if date is None:
            date = datetime.today()
        table = 'saa_industry_classifications'
        records = self.query_records(date)
        self.save_records(records, table, 'id')
        self._logger.info('Saved %s records to %s', len(records), table)

    def query_records(self, date):
        payload = self.valuation_service._download_cnindex_crsc_payload(
            date,
            payload_description='cnindex csrc industry classifications',
        )
        records_by_id = {}
        for block in payload:
            for item in block.get('sylItemVoList', []):
                industry_id = self.valuation_service._normalize_cnindex_value(item.get('tc'))
                name = self.valuation_service._normalize_cnindex_value(item.get('tn'))
                if not industry_id or not name:
                    continue
                if '法律声明' in str(name):
                    continue

                industry_id = str(industry_id).strip()
                if industry_id in {'S', 'S91'}:
                    continue

                parent_id = self._derive_parent_id(industry_id, item.get('tl'))
                records_by_id[industry_id] = {
                    'id': industry_id,
                    'name': str(name).strip(),
                    'parent_id': parent_id,
                }

        return sorted(records_by_id.values(), key=lambda record: (record['parent_id'] is not None, record['id']))

    def save_records(self, records, table, primary_keys):
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, table, primary_keys)

    @staticmethod
    def _derive_parent_id(industry_id, level):
        level = str(level).strip() if level is not None else ''
        if level == '1' or len(industry_id) == 1:
            return None
        return industry_id[0]
