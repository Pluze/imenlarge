from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image
import json

from imenlarge.prompt import build, fingerprint
from imenlarge.review import report


class RevisionTests(unittest.TestCase):
    def test_feedback_belongs_to_measured_frame(self):
        action = "Synthetic action field"
        self.assertIn(f"Depicted action: {action}", build({"action": action}, Path("source.jpg")))
        self.assertNotIn("Depicted action:", build({}, Path("source.jpg")))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, parent = root / "source.png", root / "parent.png"
            Image.new("RGB", (32, 32), "white").save(src)
            Image.new("RGB", (128, 128), "gray").save(parent)
            brief = {"goal": "Restore this photograph.", "regions": {"tip": [3, 4, 8, 10]}}
            report(src, [parent], brief, root / "review")
            measured = json.loads((root / "review/metrics.json").read_text())
            feedback = json.loads((root / "review/feedback-01.json").read_text())
            self.assertEqual(feedback["parent_sha256"], fingerprint(parent))
            feedback.update(region="tip", observed="A gap.",
                            change="Close the visible gap.", preserve="Hold the upper edge fixed.")
            feedback["retained"] = ["The lower attachment is continuous."]
            prompt = build(brief, src, parent, measured, feedback)
            self.assertIn(feedback["retained"][0], prompt)
            for key in ("observed", "change", "preserve"):
                self.assertIn(feedback[key], prompt)
            for changed in (dict(feedback, region="other"), dict(feedback, parent_sha256="stale")):
                with self.assertRaises(ValueError):
                    build(brief, src, parent, measured, changed)
            with self.assertRaises(ValueError):
                build(dict(brief, goal="Changed framing."), src, parent, measured, feedback)
            with self.assertRaises(ValueError):
                build(brief, parent, parent, measured, feedback)
