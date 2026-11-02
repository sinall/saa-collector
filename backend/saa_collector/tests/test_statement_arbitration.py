from datetime import date
from itertools import permutations
from unittest import TestCase

from saa_collector.services.common.statement_arbitration import arbitrate_candidates


class StatementArbitrationTest(TestCase):
    def row(self, kind, comp, published=date(2020, 8, 31), **values):
        return dict(symbol='600816', report_date=date(2019, 6, 30),
                    disclosure_date=published, version_type=kind,
                    source_metadata={'comp_type': comp, 'update_flag': '1'}, **values)

    def test_matching_current_type_selects_whole_candidate(self):
        a,b=self.row('RESTATED','2',revenue=12),self.row('RESTATED','1',revenue=None)
        ref=self.row('LATEST','2',date(2019,8,31))
        for rows in permutations([a,b]):
            out, rule=arbitrate_candidates(list(rows),[ref])
            self.assertEqual(out,[a])
            self.assertEqual(rule,'match_current_report_comp_type_v1')

    def test_future_reference_cannot_select(self):
        rows=[self.row('RESTATED','2'),self.row('RESTATED','1')]
        self.assertEqual(arbitrate_candidates(rows,[self.row('LATEST','2',date(2021,1,1))]),(rows,None))

    def test_same_type_or_ambiguous_reference_stays_unresolved(self):
        rows=[self.row('RESTATED','1',revenue=12),self.row('RESTATED','1',revenue=-12)]
        self.assertEqual(arbitrate_candidates(rows,[self.row('LATEST','1')]),(rows,None))
        rows=[self.row('RESTATED','1'),self.row('RESTATED','2')]
        refs=[self.row('LATEST','1'),self.row('LATEST','2')]
        self.assertEqual(arbitrate_candidates(rows,refs),(rows,None))

    def test_reference_must_be_same_security_and_period(self):
        rows=[self.row('RESTATED','1'),self.row('RESTATED','2')]
        ref=dict(self.row('LATEST','1'),symbol='000001')
        self.assertEqual(arbitrate_candidates(rows,[ref]),(rows,None))
