import pandas as pd
from django.test import SimpleTestCase

from saa_collector.services.common.price_adjustment_service import (
    find_adjusted_price_discontinuities,
)


class PriceAdjustmentServiceTest(SimpleTestCase):
    def test_find_adjusted_price_discontinuities_flags_known_break_shape(self):
        frame = pd.DataFrame([
            {'code': '000001', 'date': '2025-02-28', 'price': 1602.33},
            {'code': '000001', 'date': '2025-03-31', 'price': 1564.80},
            {'code': '000001', 'date': '2025-04-30', 'price': 10.91},
            {'code': '000001', 'date': '2025-05-30', 'price': 11.56},
            {'code': '600000', 'date': '2025-03-31', 'price': 168.03},
            {'code': '600000', 'date': '2025-04-30', 'price': 10.96},
        ])

        result = find_adjusted_price_discontinuities(frame)

        self.assertEqual(result['code'].tolist(), ['000001', '600000'])
        self.assertEqual(result['date'].dt.strftime('%Y-%m-%d').tolist(), ['2025-04-30', '2025-04-30'])
        self.assertLess(result[result['code'] == '000001']['ratio'].iloc[0], 0.1)

    def test_find_adjusted_price_discontinuities_accepts_continuous_prices(self):
        frame = pd.DataFrame([
            {'code': '000001', 'date': '2025-02-28', 'price': 100.0},
            {'code': '000001', 'date': '2025-03-31', 'price': 110.0},
            {'code': '000001', 'date': '2025-04-30', 'price': 108.0},
        ])

        result = find_adjusted_price_discontinuities(frame)

        self.assertTrue(result.empty)
