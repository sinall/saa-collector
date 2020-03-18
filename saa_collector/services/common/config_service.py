import os
from pathlib import Path

import pandas as pd
import yaml

from saa_collector.definitions import ROOT_DIR


class ConfigService:
    def __init__(self):
        self.load_config()
        self.db_config = self.config.get('saa_collector').get('db')
        self.xls_file = pd.ExcelFile(os.path.join(ROOT_DIR, 'config', 'table-config.xls'))

    def get_config(self):
        return self.config

    def get_db_config(self):
        return self.db_config

    def get_table_config(self, table):
        return self.xls_file.parse(table)

    def get_xls_file(self):
        return self.xls_file

    def load_config(self):
        file_path = os.path.join('{home_dir}', '.{label}', 'config', '{label}{suffix}')
        file_path = file_path.format(
            label='saa_collector',
            suffix='.yml',
            home_dir=Path.home(),
        )
        with open(file_path, 'r') as f:
            content = f.read()
            if content is not None and len(content) > 0:
                self.config = yaml.load(content, Loader=yaml.SafeLoader)
