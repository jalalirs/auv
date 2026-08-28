from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import yaml

from coral_catalog import ManifestError, build_catalog, catalog_record, load_manifest, validate_manifest


ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "projects/002_red_sea_digital_twin/assets/sources/reefs4d/zenodo-14616671/C22019.yaml"


class CatalogTests(unittest.TestCase):
    def test_real_manifest_is_valid_but_scientifically_blocked(self) -> None:
        record = catalog_record(MANIFEST, ROOT)
        self.assertEqual(record["asset_id"], "reefs4d.c2.2019")
        self.assertEqual(record["readiness"], "blocked")
        self.assertIn("vertical datum is unknown", record["readiness_blockers"])
        self.assertIn("anchor is not survey-grade", record["readiness_blockers"])

    def test_catalog_build_is_deterministic(self) -> None:
        first = build_catalog([MANIFEST], ROOT)
        second = build_catalog([MANIFEST], ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first["record_count"], 1)

    def test_invalid_coordinate_is_rejected(self) -> None:
        document = copy.deepcopy(load_manifest(MANIFEST))
        document["site"]["wgs84_anchor"]["latitude_deg"] = 120
        with self.assertRaisesRegex(ManifestError, "outside WGS84 range"):
            validate_manifest(document)

    def test_duplicate_asset_identifier_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            duplicate = Path(directory) / "duplicate.yaml"
            duplicate.write_text(yaml.safe_dump(load_manifest(MANIFEST), sort_keys=False))
            with self.assertRaisesRegex(ManifestError, "duplicate asset_id"):
                build_catalog([MANIFEST, duplicate], ROOT)


if __name__ == "__main__":
    unittest.main()
