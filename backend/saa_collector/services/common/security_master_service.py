# -*- coding: utf-8 -*-
import logging

import mysql.connector

from saa_collector.services.common.config_service import ConfigService


class SecurityMasterRefreshService:
    """Refresh mfactor-compatible security master data from collector stock data."""

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self.db_config = ConfigService().get_db_config()

    def refresh_from_stocks(self, cnx=None):
        should_close = cnx is None
        if cnx is None:
            cnx = mysql.connector.connect(**self.db_config)

        cursor = cnx.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO saa_securities
                    (code, display_name, name, start_date, end_date, type)
                SELECT
                    s.symbol AS code,
                    s.name AS display_name,
                    s.symbol AS name,
                    s.listing_time AS start_date,
                    DATE('2200-01-01') AS end_date,
                    LOWER(s.type) AS type
                FROM saa_stocks s
                WHERE s.type = 'STOCK'
                  AND s.market = 'A'
                  AND s.symbol IS NOT NULL
                ON DUPLICATE KEY UPDATE
                    display_name = VALUES(display_name),
                    name = COALESCE(NULLIF(name, ''), VALUES(name)),
                    start_date = COALESCE(VALUES(start_date), start_date),
                    end_date = COALESCE(end_date, VALUES(end_date)),
                    type = VALUES(type)
                """
            )
            cnx.commit()
            self._logger.info(
                'Refreshed saa_securities from saa_stocks: affected_rows=%s',
                cursor.rowcount,
            )
            return cursor.rowcount
        finally:
            cursor.close()
            if should_close:
                cnx.close()
