import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from PIL import Image

from imenlarge.decision import decide
from imenlarge.review import digest, report
from imenlarge.tone import match, tone_metrics


class WorkflowTests(unittest.TestCase):
    def test_tone_and_anchor(self):
        base = Image.new("RGB", (32, 32), (100, 130, 80))
        shifted = Image.new("RGB", (64, 64), (115, 120, 95))
        restored = match(base, shifted)
        np.testing.assert_array_equal(np.asarray(restored)[0, 0], [100, 130, 80])
        self.assertEqual(tone_metrics(base, restored.resize(base.size))["luma_mae"], 0)
        partial = match(base, shifted, radius=8, strength=0.5)
        np.testing.assert_array_equal(np.asarray(partial)[0, 0], [108, 125, 88])
        for bad in [dict(radius=0), dict(radius=float("nan")), dict(strength=1.5)]:
            with self.assertRaises(ValueError):
                match(base, shifted, **bad)
        texture = np.indices((32, 32)).sum(axis=0) % 2 * 80 + 70
        target = Image.fromarray(texture.astype("uint8")).convert("RGB")
        flat = Image.new("RGB", (32, 32), (110, 110, 110))
        anchored = match(target, flat, [[8, 8, 24, 24]])
        self.assertLess(abs(np.asarray(anchored)[16,16,0].item()-70), 2)
        self.assertLess(abs(np.asarray(anchored)[0,0,0].item()-110), 5)

    def test_workflow_uses_actual_parent_and_selection(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = []
            for color in ("gray", "red", "blue", "green"):
                path = root / f"{color}.png"
                Image.new("RGB", (32, 32), color).save(path)
                files.append(path)
            source, *frames = files
            stages = []
            for i, frame in enumerate(frames):
                stage = {"candidate_sha256": digest(frame), "tool": "Generation", "reason": "Check tone.",
                         "checks": [{"region": "full", "source_evidence": "Gray field.",
                                     "candidate_evidence": "Color shift.", "next_action": "Compare tone.",
                                     "status": "aligned" if i == 1 else "revise"}]}
                if i:
                    stage["parent_sha256"] = digest(frames[0])
                stages.append(stage)
            wf = {"source_sha256": digest(source), "stages": stages,
                  "selected_sha256": digest(frames[1]), "selection_reason": "Closest observed frame."}
            report(source, frames, {}, root/"review", workflow=wf)
            result = json.loads((root/"review/metrics.json").read_text())
            trace = result["workflow"]
            self.assertEqual(trace["selected_stage"], 2)
            self.assertEqual(trace["stages"][-1]["parent_stage"], 1)
            self.assertEqual(trace["stages"][0]["action"], "revise")
            self.assertIn("a1_mae_delta", trace["stages"][2]["checks"][0])
            with self.assertRaises(ValueError):
                decide(dict(stages[-1], source_sha256="stale"), digest(source), result["candidates"])

    def test_final_selection_and_revision_handoff(self):
        from imenlarge.prompt import build
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, first, second = [root / name for name in ("source.png", "one.png", "two.png")]
            for path, size, color in [(src, 32, "gray"), (first, 64, "green"), (second, 64, "blue")]:
                Image.new("RGB", (size, size), color).save(path)
            focus = {"source_sha256": digest(src), "regions": {"seam": [2, 2, 12, 12]},
                     "visual_anchors": {"seam": "The narrow line crosses the seam."}}
            full = dict(region="full", source_evidence="Centered.", candidate_evidence="Outline aligned.",
                        residual_evidence="Color bias across the field.", next_action="Keep the outline.", status="aligned")
            seam = dict(full, region="seam")
            defect = dict(seam, status="revise", candidate_evidence="The line shifts right.", next_action="Align the line.")
            stages = [dict(name="Trial", tool="Render", reason="Resolve line.", candidate_sha256=digest(first),
                           checks=[full, defect]),
                      dict(name="Repair", tool="Revision", reason="Align seam.", candidate_sha256=digest(second),
                           parent_sha256=digest(first), checks=[full, seam])]
            workflow = dict(source_sha256=digest(src), stages=stages, selected_sha256=digest(second),
                            comparison_sha256=digest(first), selection_reason="Continuous line.")
            dest = root / "delivery"
            for checks, message in [([seam], "Revise full"), ([full], "Revise seam"),
                                    ([full, defect], "Align the line"), ([full, dict(seam, residual_evidence="")], "residual_evidence")]:
                stages[1]["checks"] = checks
                with self.assertRaisesRegex(ValueError, message):
                    report(src, [first, second], focus, dest, workflow=workflow, final=True)
                self.assertFalse(dest.exists())
            stages[1]["checks"] = [full, seam]
            with self.assertRaisesRegex(ValueError, "native_review"):
                report(src, [first, second], focus, dest, workflow=workflow, final=True)
            stages[1]["native_review"] = dict(status="aligned", region="seam",
                                              detail_gain="Distinct line at full scale.", continuity="Single edge.")
            native_repair = dict(stages[1]["native_review"], status="revise", next_action="Restore texture.")
            stages[0]["native_review"] = native_repair
            later_inspection = dict(stages[1], source_sha256=digest(src), checks=[full, defect])
            with self.assertRaisesRegex(ValueError, "open inspection"):
                report(src, [first, second], focus, dest, inspection=later_inspection, workflow=workflow, final=True)
            self.assertFalse(dest.exists())
            report(src, [first, second], focus, dest, workflow=workflow, final=True)
            primary_focus = dict(focus, primary_region="seam")
            extra_region = "secondary"
            primary_focus["regions"] = dict(focus["regions"], secondary=[10, 10, 20, 20])
            primary_focus["visual_anchors"] = dict(focus["visual_anchors"], secondary="A broad plane.")
            stages[1]["checks"].append(dict(full, region=extra_region))
            stages[1]["native_review"]["region"] = extra_region
            with self.assertRaisesRegex(ValueError, "Inspect the primary region seam"):
                report(src, [first, second], primary_focus, root / "primary", workflow=workflow, final=True)
            stages[1]["native_review"]["region"] = "seam"
            report(src, [first, second], primary_focus, root / "primary", workflow=workflow, final=True)
            stages[1]["checks"].pop()
            inferred = dict(focus, interpretation={"seam": "The near edge casts a narrow shadow."})
            self.assertIn(inferred["interpretation"]["seam"], build(inferred, src))
            with self.assertRaisesRegex(ValueError, "Inspect the native crop"):
                report(src, [first, second], inferred, root / "semantic", workflow=workflow, final=True)
            seam["semantic_evidence"] = "The near surface occludes the line and casts a shadow along it."
            report(src, [first, second], inferred, root / "semantic", workflow=workflow, final=True)
            data = json.loads((dest / "metrics.json").read_text())
            trace = data["workflow"]
            self.assertTrue(trace["final"])
            self.assertEqual(data["status"], "final")
            self.assertIn("<h1>Final review</h1>", (dest / "review.html").read_text())
            self.assertEqual([s["name"] for s in trace["stages"]], ["Trial", "Repair"])
            self.assertEqual(trace["comparison_stage"], 1)
            feedback = json.loads((dest / "feedback-01.json").read_text())
            prompt = build(focus, src, first, data, feedback)
            self.assertEqual(trace["stages"][0]["native_review"], native_repair)
            self.assertIn(native_repair["next_action"], prompt)
            self.assertIn(defect["next_action"], prompt)
            self.assertIn(full["candidate_evidence"], prompt)
