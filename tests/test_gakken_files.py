import tempfile
import unittest
from pathlib import Path
from inventory.gakken_files import validate_pair,decode_tsv,encode_tsv,INDEX_HEADER
from scripts.gakken_test_package import build

class GakkenFilesTests(unittest.TestCase):
    def test_synthetic_package_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'new';archive=build(folder)
            self.assertTrue(archive.exists());self.assertEqual(validate_pair((folder/'INDEX.TXT').read_bytes(),(folder/'KENPIN.TXT').read_bytes())['kenpin_records'],4)
            self.assertFalse((folder/'KENPIN.TXT').read_bytes().endswith(b'\n'))
            with self.assertRaises(FileExistsError):build(folder)
    def test_invalid_pairs_and_fields(self):
        with self.assertRaises(ValueError):encode_tsv(INDEX_HEADER,[['key\tbad','key','1','2']])
        with self.assertRaises(ValueError):decode_tsv(b'wrong',INDEX_HEADER)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'new';build(folder)
            a=(folder/'INDEX.TXT').read_bytes();b=(folder/'KENPIN.TXT').read_bytes()
            with self.assertRaises(ValueError):validate_pair(a,b.replace(b'99001',b'88001'))
