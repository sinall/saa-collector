import os
from pathlib import Path

import pandas as pd
import yaml

from saa_collector.definitions import ROOT_DIR


class ConfigService:
    def __init__(self):
        self.load_config()
        self.db_config = self.config.get('saa_collector').get('db')
        xls_file = pd.ExcelFile(os.path.join(ROOT_DIR, 'config', 'table-config.xls'))
        self.table_configs = xls_file.parse(None)

    def get_config(self):
        return self.config

    def get_db_config(self):
        return self.db_config

    def get_table_config(self, table):
        return self.table_configs[table]

    def load_config(self):
        with open('/etc/saa/collector/saa_collector.yml', 'r') as f:
            content = f.read()
            if content is not None and len(content) > 0:
                self.config = yaml.load(content, Loader=yaml.SafeLoader)
