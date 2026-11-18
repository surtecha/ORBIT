import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.tle.parser import parse_tle_file


# A historic Vanguard 1 element pair from the SGP4 verification data.
LINE1 = '1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753'
LINE2 = '2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667'


class ElementImportTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'elements.tle')
            path.write_text(text, encoding='utf-8')
            return parse_tle_file(path)

    def test_rejects_bad_checksum(self):
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.parse(LINE1[:-1] + '0\n' + LINE2)

    def test_duplicate_pairs_stay_aligned_with_epochs(self):
        pair = LINE1 + '\n' + LINE2 + '\n'
        record = self.parse(pair * 2)
        self.assertEqual(len(record['dataframe']), 1)
        self.assertEqual(len(record['tle_lines']), 1)
        self.assertEqual(record['dataframe']['time'][0].utcoffset(), timedelta(0))


class TrajectoryTests(unittest.TestCase):
    def test_time_grid_limits(self):
        from backend.propagator.sgp4_propagator import make_time_grid
        start = datetime(2000, 6, 27, tzinfo=timezone.utc)
        self.assertEqual(make_time_grid(start, start), [start])
        with self.assertRaises(ValueError):
            make_time_grid(start, start - timedelta(seconds=1))
        with self.assertRaises(ValueError):
            make_time_grid(start, start + timedelta(days=100), 1)
