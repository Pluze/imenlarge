import json
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

from imenlarge.decision import decide
from imenlarge.evidence import inspect_regions
from imenlarge.focus import main
from imenlarge.review import report, wavelet


class SourceFocusTests(unittest.TestCase):
    def test_source_only_plan_and_missing_inspection(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            source = p/"source.png"
            frame = Image.new("RGB", (32, 32), "gray")
            frame.putpixel((12, 10), (220, 220, 220))
            frame.save(source)
            observations = {"regions": {"patch": [6, 8, 19, 21]},
                            "visual_anchors": {"patch": "A light pixel lies inside the gray patch."}}
            (p/"notes.json").write_text(json.dumps(observations))
            main([str(source), str(p/"notes.json"), str(p/"brief.json")])
            brief = json.loads((p/"brief.json").read_text())
            report(source, [source], brief, p/"result")
            rows = json.loads((p/"result/metrics.json").read_text())["candidates"]
            check = {"region": "full", "source_evidence": "Gray field.",
                     "candidate_evidence": "Same tone.", "status": "aligned", "next_action": "Check the patch."}
            inspection = {"source_sha256": brief["source_sha256"], "candidate_sha256": rows[0]["sha256"],
                          "checks": [check]}
            decision = decide(inspection, brief["source_sha256"], rows)
            self.assertEqual(decision["action"], "revise")
            self.assertEqual(decision["checks"][-1]["region"], "patch")
            self.assertEqual(decision["checks"][-1]["status"], "uncertain")
            Image.new("RGB", (32, 32), "white").save(source)
            with self.assertRaises(ValueError):
                report(source, [source], brief, p/"mismatched")

    def test_added_and_missing_structure_without_regions(self):
        rng = np.random.default_rng(6347)
        for _ in range(12):
            x, y = map(int, rng.integers(16, 80, size=2))
            source = np.full((96, 96, 3), 110, dtype=np.uint8)
            # Repeated detail elsewhere attracts a source-only texture ranking.
            source[0:12:2, :, :] = 220
            altered = np.uint8(source + 10)
            altered[y:y+8, x:x+8] = 225
            a, b = wavelet(Image.fromarray(source)), wavelet(Image.fromarray(altered))
            for first, second, name in [(a, b, "Added detail"), (b, a, "Lost detail")]:
                bounds = inspect_regions(first, second, (96, 96), {})
                l, t, r, bottom = bounds[name]
                self.assertTrue(l <= x+4 < r and t <= y+4 < bottom)
