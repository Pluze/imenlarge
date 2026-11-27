"""Compare photographic reconstructions at four scales on the original pixel grid."""
import argparse
import base64
import hashlib
import html
import io
import json
import os
import random
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageOps, JpegImagePlugin
from scipy.ndimage import convolve1d

if __package__:
    from .summary import write_summary
    from .focus import validate_focus
    from .tone import tone_metrics
    from .decision import decide, decision_page, revision_feedback, workflow_pages
    from .projection import project, validate
    from .evidence import inspect_regions, local_page, native_box, overview, scale_page
    from .publishing import browser_panel, publish_pdf
else:
    from summary import write_summary
    from focus import validate_focus
    from tone import tone_metrics
    from decision import decide, decision_page, revision_feedback, workflow_pages
    from projection import project, validate
    from evidence import inspect_regions, local_page, native_box, overview, scale_page
    from publishing import browser_panel, publish_pdf

LUMA = np.array([0.299, 0.587, 0.114])
LANCZOS = Image.Resampling.LANCZOS


def load(path):
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) > 1:
            raise ValueError("Select one frame before evaluating animated images.")
        image = ImageOps.exif_transpose(image).convert("RGBA")
        return Image.alpha_composite(Image.new("RGBA", image.size, "white"), image).convert("RGB")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wavelet(image):
    current = np.asarray(image, dtype=np.float64)
    layers = []
    for spacing in [1, 2, 4, 8]:
        kernel = np.zeros(4 * spacing + 1)
        kernel[::spacing] = np.array([1, 4, 6, 4, 1]) / 16
        low = convolve1d(convolve1d(current, kernel, axis=0, mode="reflect"),
                         kernel, axis=1, mode="reflect")
        layers.append((low, (current - low) @ LUMA))
        current = low
    return layers


def compare(reference, candidate, bounds):
    x0, y0, x1, y1 = bounds
    region = np.s_[y0:y1, x0:x1]
    results = []
    for (a, w), (b, v) in zip(reference, candidate):
        x, y = w[region].ravel(), v[region].ravel()
        corr = None
        if x.std() > 1e-8 and y.std() > 1e-8:
            corr = float(np.corrcoef(x, y)[0, 1])
        results.append({"low_rgb_mae": float(np.abs(a[region] - b[region]).mean()),
                        "detail_luma_mae": float(np.abs(x-y).mean()), "detail_luma_r": corr})
    return results


def png(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def figure(image, label, native=False):
    if not native:
        image = image.copy()
        image.thumbnail((600, 600), LANCZOS)
    return ('<figure><img src="' + png(image) + '"><figcaption>' +
            html.escape(label) + '</figcaption></figure>')


def report(src, candidates, cfg, output, truth=None, inspection=None, workflow=None, final=False, comparison_reference=None, blind=False):
    if not candidates:
        raise ValueError("Supply at least one candidate image.")
    original = load(src)
    width, height = original.size
    if min(width, height) < 16:
        raise ValueError("Use a source measuring at least 16 pixels on each axis.")
    simple = cfg is None
    if simple:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError("Supply the brief as a JSON object.")
    source_hash = digest(src)
    if final and (workflow is None or "source_sha256" not in cfg):
        raise ValueError("Supply a source-bound focus brief and a workflow for final review.")
    if "source_sha256" in cfg:
        validate_focus(cfg, source_hash, original.size)
    regions = cfg.get("regions", {})
    if not isinstance(regions, dict) or "full" in regions:
        raise ValueError("Supply named rectangles in the regions object. The whole frame is included as full.")
    for name, rect in regions.items():
        if not (isinstance(rect, list) and len(rect) == 4 and all(type(v) is int for v in rect)
                and 0 <= rect[0] < rect[2] <= width and 0 <= rect[1] < rect[3] <= height):
            raise ValueError(f"Invalid half-open source rectangle for {name}: {rect}")
    profile = cfg.get("projection")
    if profile is not None:
        validate(profile)
    jpeg_options = {}
    jpeg_mode = "RGB"
    orientation = 1
    if profile is None:
        with Image.open(src) as encoded:
            if encoded.format == "JPEG" and encoded.mode in ("L", "RGB") and encoded.quantization:
                sampling = JpegImagePlugin.get_sampling(encoded)
                if encoded.mode == "L" or sampling in (0, 1, 2):
                    orientation = encoded.getexif().get(274, 1)
                    jpeg_mode = encoded.mode
                    jpeg_options = {"qtables": encoded.quantization, "subsampling": max(0, sampling)}
    def observe(grid):
        if profile is not None:
            return project(grid, profile)
        # The encoder's block lattice uses stored raster coordinates.
        inverse = {6: 8, 8: 6}.get(orientation, orientation)
        transpose = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
                     4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                     6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
                     8: Image.Transpose.ROTATE_90}
        raster = grid.transpose(transpose[inverse]) if inverse in transpose else grid
        buf = io.BytesIO()
        raster.convert(jpeg_mode).save(buf, "JPEG", **jpeg_options)
        buf.seek(0)
        with Image.open(buf) as compressed:
            decoded = compressed.convert("RGB")
        return decoded.transpose(transpose[orientation]) if orientation in transpose else decoded

    comparisons = {name: [figure(original.crop(rect), "Source")] for name, rect in regions.items()}
    if truth and comparison_reference:
        raise ValueError("Choose one native reference for this evaluation.")
    reference_path = truth or comparison_reference
    native_reference = load(reference_path) if reference_path else None
    if native_reference is not None and abs(native_reference.width/width - native_reference.height/height)*min(width, height) > 1.01:
        raise ValueError("Choose a reference with the source aspect ratio.")
    reference = wavelet(original)
    results = {"source": src.name, "sha256": source_hash, "size": original.size,
               "brief": cfg, "candidates": [], "status": "final" if final else "working"}
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Restoration review</title>'
             '<style>body{font:16px system-ui;max-width:1200px;margin:30px auto;padding:0 18px;color:#21313a}'
             '.row{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0 0 12px}img{width:235px;max-width:100%}'
             'figcaption{font-size:13px}td,th{padding:5px 12px;text-align:left;border-bottom:1px solid #ddd}'
             'details img{width:auto;max-width:none}details,.panel{overflow:auto}.panel img{max-width:180px;width:100%}.panel td{min-width:60px}pre{white-space:pre-wrap}</style>'
             '<h1>Restoration review</h1><p>Wavelet measurements use the original pixel grid. Open each native crop and inspect '
             'the full output at 100% before making a decision.</p><pre>' +
             html.escape(json.dumps(cfg, ensure_ascii=False, indent=2)) + '</pre>']
    heading = "Final review" if final else "Working review"
    parts[0] = parts[0].replace("<h1>Restoration review</h1>", f"<h1>{heading}</h1>")
    if jpeg_options:
        results["recompression"] = "Source JPEG quantization tables and chroma sampling"
    if reference_path:
        reference_grid = native_reference.resize(original.size, LANCZOS)
        reference_layers = wavelet(reference_grid)
        reference_bounds = {"full": (0, 0, width, height), **regions}
        results["native_reference"] = {
            "name": reference_path.name, "sha256": digest(reference_path), "size": native_reference.size,
            "role": "known native reference" if truth else "supplied comparison",
            "wavelet": {name: compare(reference, reference_layers, box) for name, box in reference_bounds.items()}
        }
        if profile is not None or jpeg_options:
            replay_layers = wavelet(observe(reference_grid))
            results["native_reference"]["replay_wavelet"] = {
                name: compare(reference, replay_layers, box) for name, box in reference_bounds.items()
            }
    sections = []
    workflow_images = []
    direct_maps = []
    parts.append('<p><a href="review.pdf">Read the illustrated summary</a> &middot; <a href="evidence.pdf">Full evidence PDF</a> &middot; <a href="native-crops.png">Native pixel crops</a></p>')
    if blind:
        parts.append('<p><a href="visual-comparison.pdf">Masked visual comparison</a> &middot; '
                     '<a href="visual-key.json">Sample identities</a></p>')
    for index, path in enumerate(candidates, 1):
        im = load(path)
        if abs(im.width / width - im.height / height) * min(width, height) > 1.01:
            raise ValueError(f"{path.name}: supply a candidate with the source aspect ratio.")
        workflow_images.append(im)
        down = im.resize(original.size, LANCZOS)
        layers = wavelet(down)
        inspected = inspect_regions(reference, layers, original.size, regions)
        bounds = {"full": (0, 0, width, height), **inspected}
        metrics = {name: compare(reference, layers, rect) for name, rect in bounds.items()}
        results["candidates"].append({"name": path.name, "size": im.size, "sha256": digest(path),
                                      "wavelet": metrics, "visual_review": "pending"})
        if truth:
            if im.size != native_reference.size:
                raise ValueError("Choose a native reference with the same dimensions as the candidate.")
            diff = np.asarray(im, dtype=float) - np.asarray(native_reference, dtype=float)
            rmse = float(np.sqrt(np.mean(diff ** 2)))
            psnr = float(20 * np.log10(255 / rmse)) if rmse else None
            results["candidates"][-1]["native_rgb"] = {"rmse": rmse, "psnr_db": psnr}
            label = f"{psnr:.2f} dB" if psnr is not None else "infinite"
            parts.append(f"<p>{html.escape(path.name)} · known-reference RGB PSNR {label}</p>")
        row = results["candidates"][-1]
        row["inspection_regions"] = inspected
        if "source_sha256" in cfg:
            row["source_relationships"] = cfg["visual_anchors"]
            if "primary_region" in cfg:
                row["primary_region"] = cfg["primary_region"]
            row["interpretation"] = cfg.get("interpretation", {})
        row["tone"] = tone_metrics(original, down)
        label = "direct projection"
        pages = [scale_page("Four scales / direct projection", reference, layers, metrics["full"])]
        direct_maps.append([band[-1] for band in pages[0]["rows"]])
        parts.append("<h2>" + html.escape(path.name) + "</h2>")
        if not simple:
            parts.append(f"<p>Revision feedback: feedback-{index:02d}.json</p>")
        if profile is not None or jpeg_options:
            replay = observe(down)
            label = profile["status"] + " process" if profile is not None else "source JPEG encoding"
            replay_layers = wavelet(replay)
            replay_metrics = {name: compare(reference, replay_layers, rect) for name, rect in bounds.items()}
            results["candidates"][-1]["replay_wavelet"] = replay_metrics
            pages.append(scale_page("Four scales / " + label, reference, replay_layers, replay_metrics["full"]))
        frame = overview(original, down, row, label)
        if "replay_wavelet" in row:
            frame["extra_columns"] = ["Source", "Encoding replay", "Replay blend"]
            frame["extra_rows"] = [[original, replay, Image.blend(original, replay, 0.5)]]
        pages.insert(0, frame)
        for name, rect in inspected.items():
            page = local_page(name, rect, original, im, down, reference, layers, metrics[name])
            local = metrics[name][0]["low_rgb_mae"]
            global_mae = metrics["full"][0]["low_rgb_mae"]
            page["lines"] = [f"A1 mean absolute error is {local:.2f} in this region and "
                             f"{global_mae:.2f} across the frame. The maps share the 0 to 40 RGB scale."]
            if "replay_wavelet" in row:
                page["replay_scores"] = row["replay_wavelet"][name]
            pages.append(page)
        context = (f"{path.name}  /  {width} x {height} to "
                   f"{im.width} x {im.height} px  /  SHA-256 {row['sha256'][:12]}")
        for page in pages:
            sections.append((context, page))
            parts.append(browser_panel(page, figure))
        for name, rect in regions.items():
            native_rect = native_box(im, original.size, rect)
            comparisons[name].append(figure(im.crop(native_rect), path.name))
            parts.append('<details open><summary>' + html.escape(name) + ' · native candidate crop</summary>' +
                         figure(im.crop(native_rect), f"Source box {rect} · native pixels", native=True) + '</details>')
    if comparisons:
        parts.insert(1, '<h2>Compare the same region across rounds</h2>' + ''.join(
            '<h3>' + html.escape(name) + '</h3><div class="row">' + ''.join(items) + '</div>'
            for name, items in comparisons.items()))
    if len(candidates) > 1:
        rows = []
        for i, candidate in enumerate(results["candidates"], 1):
            fine, *_, coarse = candidate["wavelet"]["full"]
            rows.append([candidate["name"], candidate["sha256"][:12], f"{fine['low_rgb_mae']:.2f}",
                         f"{coarse['low_rgb_mae']:.2f}"])
        summary = {"title": "Comparison across frames", "note": "Each candidate uses the same source and color scale. "
                   "Smaller mean absolute errors indicate closer agreement on the source grid.",
                   "columns": ["Candidate", "SHA-256 prefix", "A1 RGB MAE", "A4 RGB MAE"], "rows": rows}
        sections.insert(0, ("Round comparison", summary))
        parts.insert(1, browser_panel(summary, figure))
    assessments = {}
    if inspection is not None:
        decision = decide(inspection, results["sha256"], results["candidates"])
        assessments[decision["candidate_sha256"]] = decision
        results["decision"] = decision
        results["candidates"][-1]["visual_review"] = decision["action"]
        panel = decision_page(decision)
        sections.insert(0, ("Final candidate", panel))
        parts.insert(1, browser_panel(panel, figure))
    if workflow is not None:
        trace, panels = workflow_pages(workflow, results["sha256"], results["candidates"], workflow_images, original, final=final)
        latest_inspection = results.get("decision")
        if (final and latest_inspection and latest_inspection["candidate_sha256"] == trace["selected_sha256"]
                and latest_inspection["action"] == "revise"):
            raise ValueError("Resolve the selected candidate's open inspection and update its workflow checks.")
        assessments.update((s["candidate_sha256"], s) for s in trace["stages"])
        results["workflow"] = trace
        sections[:0] = [("Processing record", panel) for panel in panels]
        parts.extend(browser_panel(panel, figure) for panel in panels)
        chosen = trace["stages"][trace["selected_stage"]-1]
        intro = ("<h2>" + html.escape(chosen["name"]) + "</h2><p>" +
                 html.escape(trace["selection_reason"]) + "</p>")
        display = [trace["selected_stage"]]
        if trace["comparison_stage"]:
            display.append(trace["comparison_stage"])
        intro += '<div class="row">' + ''.join(
            figure(workflow_images[i-1], trace["stages"][i-1]["name"]) for i in display) + '</div>'
        parts[0] = parts[0].replace(f"<h1>{heading}</h1>", f"<h1>{heading}</h1>" + intro)
    if native_reference is not None:
        chosen = results.get("workflow", {}).get("selected_stage", len(candidates)) - 1
        label = results["candidates"][chosen]["name"]
        if workflow is not None:
            label = trace["stages"][chosen]["name"]
        output_frame = workflow_images[chosen]
        images = [original, output_frame, native_reference]
        panel = {"title": "Supplied reference comparison",
                 "note": "Both enlargements use the original framing and source-grid measurements.",
                 "columns": ["Source", label, "Supplied reference"], "rows": [images], "lines": []}
        for name, rect in regions.items():
            crops = [im.crop(native_box(im, original.size, rect)) for im in images]
            selected_score = results["candidates"][chosen]["wavelet"][name][0]["low_rgb_mae"]
            supplied_score = results["native_reference"]["wavelet"][name][0]["low_rgb_mae"]
            panel["rows"].append(crops)
            panel["lines"].append(f"{name} / A1 RGB MAE: {label} {selected_score:.2f}, "
                                  f"supplied reference {supplied_score:.2f}.")
        sections.insert(0, ("Held-out evaluation", panel))
        parts.insert(1, browser_panel(panel, figure))
    parts.append('</html>')
    parent = output.parent if output is not None else candidates[-1].parent
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=parent) as scratch:
        stage = Path(scratch) / "report"
        stage.mkdir()
        if not simple:
            for index, row in enumerate(results["candidates"], 1):
                feedback = revision_feedback(row, assessments.get(row["sha256"], {}))
                (stage / f"feedback-{index:02d}.json").write_text(
                    json.dumps(feedback, indent=2) + "\n", encoding="utf-8")
        if blind:
            order = list(range(len(candidates)))
            random.SystemRandom().shuffle(order)
            key = {}
            panels = []
            for start in range(0, len(order), 3):
                batch = order[start:start+3]
                columns = ["Source"]
                batch_images = [original]
                for position, index in enumerate(batch, start+1):
                    code = f"Sample {position}"
                    columns.append(code)
                    key[code] = {"name": candidates[index].name, "sha256": results["candidates"][index]["sha256"]}
                    batch_images.append(workflow_images[index])
                panels.append(("Visual comparison", {"title": "Scene at viewing size",
                               "note": "Describe the visible interaction and the surfaces that establish it.",
                               "columns": columns[1:], "rows": [batch_images[1:]]}))
                panels.append(("Visual comparison", {"title": "Whole image", "note": "Inspect geometry, light and texture.",
                               "columns": columns, "rows": [batch_images]}))
                for region, rect in regions.items():
                    crops = [im.crop(native_box(im, original.size, rect)) for im in batch_images]
                    panels.append(("Visual comparison", {"title": region, "note": "Compare the matching source area.",
                                   "columns": columns, "rows": [crops]}))
            publish_pdf(stage / "visual-comparison.pdf", panels)
            (stage / "visual-key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
        publish_pdf(stage / "evidence.pdf", sections)
        write_summary(stage / "review.pdf", original, workflow_images, results, direct_maps, wavelet, native_reference)
        (stage / 'review.html').write_text(''.join(parts), encoding='utf-8')
        (stage / 'metrics.json').write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        if output is None:
            output = parent / f"{candidates[-1].stem}-review-{Path(scratch).name}"
        if output.exists():
            raise ValueError("Use a new output directory for each review.")
        os.rename(stage, output)
    return output / "review.html"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("candidates", type=Path, nargs="+")
    p.add_argument("--brief", type=Path, help="Optional regions and observation settings")
    p.add_argument("--out", type=Path, help="New report directory (default: beside the candidate)")
    reference_group = p.add_mutually_exclusive_group()
    reference_group.add_argument("--reference", type=Path, help="Held-out enlargement for visual and source-grid comparison")
    reference_group.add_argument("--truth", type=Path, help="Known native reference for a controlled degradation experiment")
    p.add_argument("--inspection", type=Path, help="Visual host observations for the final frame")
    p.add_argument("--workflow", type=Path, help="Stage lineage, tool choices, visual checks and selection")
    p.add_argument("--blind", action="store_true", help="Write shuffled visual comparisons and a separate identity key")
    p.add_argument("--final", action="store_true", help="Validate the selected enlargement for delivery")
    args = p.parse_args(argv)
    try:
        brief = json.loads(args.brief.read_text(encoding="utf-8")) if args.brief else None
        inspection = json.loads(args.inspection.read_text(encoding="utf-8")) if args.inspection else None
        workflow = json.loads(args.workflow.read_text(encoding="utf-8")) if args.workflow else None
        print(report(args.source, args.candidates, brief, args.out, args.truth, inspection, workflow, args.final, args.reference, args.blind))
    except (OSError, ValueError) as exc:
        p.exit(2, f"review: {exc}\n")


if __name__ == "__main__":
    main()
