import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image
from imenlarge.review import report


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.image = self.root / "flat.png"
        Image.new("RGB", (32, 32), (51, 12, 208)).save(self.image)

    def test_identical_flat_pair(self):
        dest = self.root / "review"
        report(self.image, [self.image], {}, dest, self.image)
        row = json.loads((dest / "metrics.json").read_text())["candidates"][0]
        self.assertEqual(row["native_rgb"], {"rmse": 0, "psnr_db": None})
        self.assertEqual(row["wavelet"]["full"], [{"low_rgb_mae": 0, "detail_luma_mae": 0, "detail_luma_r": None}] * 4)
        with self.assertRaises(ValueError):
            report(self.image, [self.image], {}, dest)

    def test_local_change_and_round_report(self):
        from PIL import ImageDraw
        candidate = self.root / "patch.png"
        with Image.open(self.image) as changed:
            ImageDraw.Draw(changed).rectangle((24, 24, 31, 31), fill="white")
            changed.save(candidate)
        dest = self.root / "review"
        report(self.image, [self.image, candidate], None, dest, blind=True)
        identities = json.loads((dest / "visual-key.json").read_text())
        self.assertEqual(set(identities), {"Sample 1", "Sample 2"})
        self.assertEqual({v["name"] for v in identities.values()}, {self.image.name, candidate.name})
        self.assertTrue((dest / "visual-comparison.pdf").read_bytes().startswith(b"%PDF"))
        self.assertTrue((dest / "review.pdf").read_bytes().startswith(b"%PDF-"))
        html = (dest / "review.html").read_text()
        self.assertIn('href="visual-comparison.pdf"', html)
        self.assertIn('href="visual-key.json"', html)
        self.assertIn("<h1>Working review</h1>", html)
        self.assertIn("Comparison across frames", html)
        self.assertIn("Output - source", html)
        self.assertTrue((dest / "evidence.pdf").is_file())
        self.assertTrue((dest / "native-crops.png").is_file())
        self.assertIn("native-crops.png", html)
        data = json.loads((dest / "metrics.json").read_text())["candidates"][1]
        self.assertEqual(data["inspection_regions"]["Peak tile residual"], [24, 24, 32, 32])
        self.assertGreater(data["wavelet"]["full"][0]["detail_luma_mae"], 0)
        for finding in data["findings"]:
            self.assertIn(finding, html)

    def test_bad_roi(self):
        with self.assertRaises(ValueError):
            report(self.image, [], {"regions": {"subject": [-1, 3, 12, 20]}}, self.root / "out")

    def test_held_out_reference_scored_on_same_grid(self):
        dest = self.root / "with-reference"
        brief = {"regions": {"center": [2, 2, 12, 12]}}
        report(self.image, [self.image], brief, dest, truth=self.image)
        data = json.loads((dest / "metrics.json").read_text())
        larger = self.root / "larger.png"
        with Image.open(self.image) as image:
            image.resize((image.width*2, image.height*2)).save(larger)
        other = self.root / "comparison"
        report(self.image, [self.image], brief, other, comparison_reference=larger)
        measured = json.loads((other / "metrics.json").read_text())
        self.assertIn("Supplied reference comparison", (other / "review.html").read_text())
        self.assertEqual(measured["native_reference"]["role"], "supplied comparison")
        self.assertNotIn("native_rgb", measured["candidates"][0])
        for name in ("full", "center"):
            self.assertEqual(data["native_reference"]["wavelet"][name],
                             data["candidates"][0]["wavelet"][name])

    def test_wrong_reference_dimensions(self):
        truth = self.root / "truth.png"
        Image.new("RGB", (24, 32)).save(truth)
        with self.assertRaises(ValueError):
            report(self.image, [self.image], {}, self.root / "out", truth)
        self.assertFalse((self.root / "out").exists())

    def test_replay_matches_observed_input(self):
        import numpy as np
        from PIL import ImageFilter

        truth = Image.fromarray(np.random.default_rng(56).integers(0, 256, (128, 128, 3), dtype=np.uint8))
        truth.save(self.image)
        down = truth.resize((32, 32), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(0.5))
        values = np.asarray(down, dtype=float) + np.random.default_rng(8).normal(0, 3, (32, 32, 3))
        obs = self.root / "observed.jpg"
        Image.fromarray(np.uint8(np.clip(np.rint(values), 0, 255))).save(obs, quality=60, subsampling=2)
        cfg = {"projection": {"status": "known", "blur_radius": .5, "noise_sigma": 3,
                              "seed": 8, "jpeg_quality": 60}, "regions": {"tip": [4, 4, 16, 16]}}
        dest = self.root / "review"
        report(obs, [self.image], cfg, dest)
        row = json.loads((dest / "metrics.json").read_text())["candidates"][0]
        for region in ("full", "tip"):
            self.assertGreater(row["wavelet"][region][1]["low_rgb_mae"], 0)
            for layer in row["replay_wavelet"][region]:
                self.assertEqual(layer["low_rgb_mae"], 0)
                self.assertAlmostEqual(layer["detail_luma_r"], 1)

    def test_focus_review_replays_oriented_source_jpeg_for_both_enlargements(self):
        import numpy as np
        native = Image.fromarray(np.random.default_rng(42).integers(0, 256, (68, 100, 3), dtype=np.uint8))
        native.save(self.image)
        raw = native.resize((25, 17), Image.Resampling.LANCZOS).transpose(Image.Transpose.ROTATE_90)
        exif = Image.Exif()
        exif[274] = 6
        source = self.root / "oriented.jpg"
        raw.save(source, quality=38, subsampling=2, exif=exif)
        dest = self.root / "review"
        report(source, [self.image], {"regions": {"area": [2, 2, 14, 14]}}, dest, comparison_reference=self.image)
        result = json.loads((dest / "metrics.json").read_text())
        for entry in (result["candidates"][0], result["native_reference"]):
            self.assertGreater(entry["wavelet"]["full"][0]["low_rgb_mae"], 0)
            for band in entry["replay_wavelet"]["area"]:
                self.assertEqual(band["low_rgb_mae"], 0)

    def test_noise_replay_needs_recorded_seed(self):
        with self.assertRaises(ValueError):
            report(self.image, [self.image], {"projection": {"status": "known", "noise_sigma": 2}},
                   self.root / "review")

    def test_image_only_review_repeated_jpeg(self):
        from imenlarge.review import main
        from contextlib import redirect_stdout
        from io import StringIO

        source = self.root / "observed.jpg"
        Image.new("RGB", (32, 32), "navy").save(source, quality=55)
        paths = []
        for _ in range(2):
            output = StringIO()
            with redirect_stdout(output):
                main([str(source), str(self.image)])
            page = Path(output.getvalue().strip())
            self.assertTrue(page.is_file())
            metrics = json.loads((page.parent / "metrics.json").read_text())
            self.assertIn("replay_wavelet", metrics["candidates"][0])
            self.assertFalse(list(page.parent.glob("feedback-*.json")))
            paths.append(page)
        self.assertNotEqual(*paths)
