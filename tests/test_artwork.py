"""Индивидуальные иллюстрации входят в проект и не дублируют друг друга."""

import hashlib
import unittest

from frontiers.catalog import CATALOG, LEADERS
from frontiers.app import STATIC


class ArtworkTests(unittest.TestCase):
    def test_every_unit_and_leader_has_a_distinct_local_png(self):
        keys = [card.key for card in CATALOG.values() if card.kind == "unit"]
        keys += [f"leader_{key}" for key in LEADERS]
        fingerprints = {}
        for key in keys:
            with self.subTest(card=key):
                path = STATIC / f"{key}.png"
                self.assertTrue(path.is_file(), str(path))
                data = path.read_bytes()
                self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"), key)
                digest = hashlib.sha256(data).hexdigest()
                self.assertNotIn(digest, fingerprints, f"{key} duplicates {fingerprints.get(digest)}")
                fingerprints[digest] = key


if __name__ == "__main__":
    unittest.main()
