import tempfile
import unittest
from pathlib import Path
from canteen.core import Portion, analyze
from canteen.storage import Repository

class AnalysisTests(unittest.TestCase):
    def test_mass_and_nutrients(self):
        r = analyze([Portion('rice', 200, 50)])
        self.assertEqual(r['consumed_g'], 150)
        self.assertEqual(r['waste_rate'], .25)
        self.assertAlmostEqual(r['nutrients']['kcal'], 174)

    def test_invalid_measurements(self):
        for portions in [[], [Portion('rice', 0, 0)], [Portion('rice', 10, 20)], [Portion('rice', float('nan'), 0)], [Portion('unknown', 10, 0)]]:
            with self.assertRaises(ValueError):
                analyze(portions)

    def test_storage_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repository(Path(tmp) / 'test.db')
            r = analyze([Portion('tofu', 100, 0)])
            repo.save('第一食堂', '午餐', '演示', r)
            rows = repo.records()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['mode'], '演示')
            self.assertEqual(rows[0]['nutrients'], r['nutrients'])

if __name__ == '__main__':
    unittest.main()
