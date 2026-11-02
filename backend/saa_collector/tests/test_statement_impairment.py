from decimal import Decimal
from unittest import TestCase
import json
from pathlib import Path
import pandas as pd

from saa_collector.services.common.statement_impairment import (
    EVIDENCE_FIELDS, normalize_impairment, UnresolvedImpairment,
)


class ImpairmentContractTest(TestCase):
    def sample(self, **overrides):
        row = dict.fromkeys(EVIDENCE_FIELDS, None)
        row.update(comp_type='1', total_revenue=1000, total_opcost=600,
                   total_cogs=620, operate_profit=380, assets_impair_loss=20)
        row.update(overrides)
        return row

    def test_cost_magnitude_and_signed_loss_have_same_effect(self):
        for value in (20, -20):
            raw = self.sample(assets_impair_loss=value)
            effect, evidence = normalize_impairment(raw)
            self.assertEqual(effect, Decimal('-20.00'))
            self.assertEqual(raw['assets_impair_loss'], value)
            self.assertEqual(evidence['impairment_cost_basis'], 'included')

    def test_reversal_remains_positive(self):
        for value in (20, -20):
            effect, _ = normalize_impairment(self.sample(
                assets_impair_loss=value, operate_profit=420, total_cogs=580))
            self.assertEqual(effect, Decimal('20.00'))

    def test_credit_is_separate_and_must_reconcile(self):
        effect, evidence = normalize_impairment(self.sample(
            credit_impa_loss=30, total_cogs=650, operate_profit=350))
        self.assertEqual(effect, Decimal('-20.00'))
        self.assertEqual(evidence['impairment_credit_effect'], '-30.00')

    def test_equal_opposite_credit_and_asset_are_ambiguous(self):
        with self.assertRaises(UnresolvedImpairment):
            normalize_impairment(self.sample(credit_impa_loss=20,
                total_cogs=600, operate_profit=400))

    def test_missing_evidence_or_bad_reconciliation_rejects(self):
        for raw in (self.sample(total_opcost=None), self.sample(operate_profit=381)):
            with self.assertRaises(UnresolvedImpairment):
                normalize_impairment(raw)

    def test_null_and_zero_are_distinct(self):
        self.assertIsNone(normalize_impairment(self.sample(assets_impair_loss=None))[0])
        self.assertEqual(normalize_impairment(self.sample(assets_impair_loss=0))[0], 0)
        self.assertIsNone(normalize_impairment(self.sample(
            assets_impair_loss=None, oth_impair_loss_assets=20))[0])

    def test_legacy_cost_components_can_independently_prove_loss(self):
        raw = self.sample(operate_profit=381, oper_cost=500, biz_tax_surchg=10,
                          sell_exp=20, admin_exp=40, fin_exp=30, rd_exp=None)
        effect, evidence = normalize_impairment(raw)
        self.assertEqual(effect, -20)
        self.assertEqual(evidence['normalization_rule'], 'impairment_signed_v1_cost_components')

    def test_financial_net_revenue_requires_expense_and_profit_bridges(self):
        raw = self.sample(comp_type='2', total_opcost=None,
                          admin_exp=590, biz_tax_surchg=10, invest_income=80)
        self.assertEqual(normalize_impairment(raw)[0], -20)
        raw['operate_profit'] = 381
        with self.assertRaises(UnresolvedImpairment):
            normalize_impairment(raw)

    def test_financial_other_business_cost_can_prove_reversal(self):
        raw = self.sample(comp_type='2', total_revenue='12867427.21',
            total_cogs='12326249.79', total_opcost=None,
            operate_profit='541177.42', assets_impair_loss='-52462.50',
            admin_exp='9515167.58', biz_tax_surchg='968598.43',
            other_bus_cost='1894946.28', invest_income='-3425459.54')
        self.assertEqual(normalize_impairment(raw)[0], Decimal('52462.50'))

    def test_other_asset_impairment_is_a_distinct_concept(self):
        effect, _ = normalize_impairment(self.sample(oth_impair_loss_assets=30))
        self.assertEqual(effect, -20)

    def test_cost_excluded_does_not_change_profit_or_cost(self):
        raw = self.sample(total_cogs=600)
        effect, evidence = normalize_impairment(raw)
        self.assertEqual(effect, -20)
        self.assertEqual(evidence['impairment_cost_basis'], 'excluded')
        self.assertEqual(raw['total_cogs'], 600)

    def test_net_revenue_presentation_requires_exact_profit_identity(self):
        raw = self.sample(total_revenue=1000, total_opcost=600,
                          total_cogs=650, credit_impa_loss=30, operate_profit=350,
                          invest_income=100)
        effect, evidence = normalize_impairment(raw)
        self.assertEqual(effect, -20)
        self.assertIn('net_revenue', evidence['normalization_rule'])

    def test_income_components_cannot_be_silently_missing(self):
        raw = self.sample()
        del raw['invest_income']
        with self.assertRaises(UnresolvedImpairment):
            normalize_impairment(raw)

    def test_real_candidates_normalize_before_conflict_and_hash(self):
        from saa_collector.services.common.statement_source_adapter import tushare_snapshots
        from saa_collector.services.common.statement_version_writer import prepare_version
        fixture = Path(__file__).parent / 'fixtures/tushare_impairment_600284.json'
        rows = json.loads(fixture.read_text())
        mapping = pd.read_excel(Path(__file__).parents[1] / 'config/table-config.xls',
                                sheet_name='saa_raw_income_statement')
        forward = tushare_snapshots('saa_raw_income_statement', rows, mapping, normalize_signs=True)
        backward = tushare_snapshots('saa_raw_income_statement', list(reversed(rows)), mapping,
                                     normalize_signs=True)
        self.assertEqual(forward, backward)
        for row in forward:
            self.assertEqual(row['asset_impairment_loss'], Decimal('-11574269.74'))
            self.assertEqual(row['total_operating_cost'], Decimal('3353200548.27'))
            prepare_version('saa_raw_income_statement', row)
        revised = next(row for row in forward if row['version_type'] == 'RESTATED')
        self.assertIn('11574269.74', revised['source_metadata']['normalization_candidates'])
        self.assertIn('-11574269.74', revised['source_metadata']['normalization_candidates'])

    def test_unresolved_issue_survives_task_result_contract(self):
        from saa_collector.services.common.statement_source_adapter import tushare_snapshots
        from saa_collector.services.collect_job_result import merge_issue
        fixture = Path(__file__).parent / 'fixtures/tushare_impairment_600284.json'
        rows = json.loads(fixture.read_text())[:1]
        rows[0]['total_opcost'] = None
        mapping = pd.read_excel(Path(__file__).parents[1] / 'config/table-config.xls',
                                sheet_name='saa_raw_income_statement')
        with self.assertRaises(UnresolvedImpairment) as caught:
            tushare_snapshots('saa_raw_income_statement', rows, mapping, normalize_signs=True)
        result = merge_issue({}, caught.exception.issue, '2026-11-02')
        self.assertEqual(result['issue_count'], 1)
        self.assertEqual(result['issues'][0]['code'], 'STATEMENT_SIGN_UNRESOLVED')

    def test_real_financial_arbitration_and_unresolved_history(self):
        from saa_collector.services.common.statement_source_adapter import tushare_snapshots
        fixture = Path(__file__).parent / 'fixtures/tushare_impairment_financial.json'
        raw = json.loads(fixture.read_text())
        mapping = pd.read_excel(Path(__file__).parents[1] / 'config/table-config.xls',
                                sheet_name='saa_raw_income_statement')
        for symbol, period, expected in [('600155.SH', '20201231', '1'),
                                          ('600816.SH', '20190630', '2')]:
            source = [r for r in raw if r['ts_code'] == symbol and r['end_date'] == period]
            rows = tushare_snapshots('saa_raw_income_statement', source, mapping, normalize_signs=True)
            self.assertEqual(rows, tushare_snapshots('saa_raw_income_statement',
                list(reversed(source)), mapping, normalize_signs=True))
            arbitrated = [r for r in rows if r['source_metadata'].get('arbitration_rule')]
            self.assertTrue(arbitrated)
            self.assertTrue(all(r['source_metadata']['comp_type'] == expected for r in arbitrated))
        missing = [r for r in raw if r['end_date'] == '20060630']
        with self.assertRaises(UnresolvedImpairment):
            tushare_snapshots('saa_raw_income_statement', missing, mapping, normalize_signs=True)
