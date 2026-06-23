from __future__ import annotations

import json
import unittest
from pathlib import Path


class DataArtifactTests(unittest.TestCase):
    def test_sample_manifest_marks_all_committed_sample_artifacts_as_synthetic(self) -> None:
        sample_dir = Path("data/sample")
        manifest = json.loads((sample_dir / "MANIFEST.json").read_text(encoding="utf-8"))
        artifact_paths = sorted(
            str(path.relative_to(sample_dir))
            for path in sample_dir.rglob("*")
            if path.is_file() and path.name != "MANIFEST.json"
        )

        self.assertEqual(manifest["source"], "synthetic")
        self.assertEqual(manifest["data_rights"], "software fixture only; no venue market data")
        self.assertEqual(sorted(manifest["artifacts"]), artifact_paths)


if __name__ == "__main__":
    unittest.main()
