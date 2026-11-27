"""Build source-grid evidence shared by the browser and print reports."""
import numpy as np
from PIL import Image, ImageDraw, ImageOps


def native_box(image, source_size, bounds):
    w, h = source_size
    x, y, r, b = bounds
    return (x*image.width//w, y*image.height//h,
            (r*image.width+w-1)//w, (b*image.height+h-1)//h)


def magnitude(values):
    gray = Image.fromarray(np.uint8(np.clip(values / 40, 0, 1) * 255))
    return ImageOps.colorize(gray, "#122942", "#ffd36f")


def signed(values):
    gray = Image.fromarray(np.uint8(np.clip(128 + values * 127 / 32, 0, 255)))
    return ImageOps.colorize(gray, "#245392", "#b34820", mid="#f7f6ed")


def inspect_regions(reference, candidate, size, requested):
    """Rank source-grid tiles by mean absolute detail and low-pass error."""
    w, h = size
    texture = np.abs(reference[0][1])
    error = np.abs(reference[0][0] - candidate[0][0]).mean(axis=2)
    boxes = [(x*w//4, y*h//4, (x+1)*w//4, (y+1)*h//4)
             for y in range(4) for x in range(4)]

    def strongest(field):
        def mean(box):
            x, y, r, b = box
            return field[y:b, x:r].mean()
        return max(boxes, key=mean)

    result = dict(requested)
    for label, field in [("Source texture", texture), ("Peak tile residual", error)]:
        box = strongest(field)
        if box not in map(tuple, result.values()):
            name = label
            while name in result:
                name += " (auto)"
            result[name] = box
    # Inspect concentrated band changes as well as broad color error. The
    # absolute band magnitudes distinguish added contours from lost ones.
    change = np.abs(candidate[0][1]) - texture
    for label, field in [("Added detail", change), ("Lost detail", -change)]:
        if field.max() < 1:
            continue
        side = max(4, min(w, h)//8)
        positive = np.maximum(field, 0)
        integral = np.pad(positive, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        sums = integral[side:, side:] - integral[:-side, side:] - integral[side:, :-side] + integral[:-side, :-side]
        y, x = map(int, np.unravel_index(sums.argmax(), sums.shape))
        box = (x, y, x+side, y+side)
        if box not in map(tuple, result.values()):
            name = label
            while name in result:
                name += " (auto)"
            result[name] = box
    return result


def fmt(value):
    return "constant band" if value is None else f"{value:.3f}"


def scale_page(label, source, candidate, scores):
    rows = []
    for index, ((a, w), (b, v)) in enumerate(zip(source, candidate), 1):
        rows.append([index, signed(w), signed(v), signed(v-w), magnitude(np.abs(a-b).mean(axis=2))])
    return {
        "title": label,
        "note": "Rows run from fine to coarse. Signed luminance uses blue at -32, ivory at zero and rust at +32. "
                "Absolute RGB error uses navy at zero and yellow at 40. Colors saturate at the endpoints.",
        "columns": ["Scale", "Source detail", "Output detail", "Output - source", "Low RGB error"],
        "rows": rows,
        "scores": scores,
    }


def overview(original, down, row, reference_name):
    scores = row["wavelet"]["full"]
    ranked = [(s["detail_luma_r"], i) for i, s in enumerate(scores, 1) if s["detail_luma_r"] is not None]
    if ranked:
        r, level = min(ranked)
        detail = f"The minimum measured detail correlation is {r:.3f} at W{level}."
    else:
        detail = "Each scale contains a constant detail band in at least one frame."
    lines = [f"From fine to coarse, low RGB MAE changes from {scores[0]['low_rgb_mae']:.2f} "
             f"at A1 to {scores[-1]['low_rgb_mae']:.2f} at A4. {detail}"]
    tone = row["tone"]
    bias = ", ".join(f"{v:+.1f}" for v in tone["rgb_bias"])
    lines.append(f"Output minus source: mean luma {tone['luma_bias']:+.1f}, RGB biases ({bias}). "
                 f"Mean absolute luma difference is {tone['luma_mae']:.2f} in 8-bit units.")
    quantiles = lambda values: " / ".join(f"{v:.1f}" for v in values)
    lines.append(f"Luma percentiles (10th / median / 90th): source {quantiles(tone['source_luma_quantiles'])}; "
                 f"output {quantiles(tone['output_luma_quantiles'])}.")
    lines.append(f"Channel samples at 0 or 255: source {tone['source_endpoint_pct']:.2f}%, "
                 f"output {tone['output_endpoint_pct']:.2f}%.")
    if "replay_wavelet" in row:
        replay = row["replay_wavelet"]["full"]
        lines.append(f"Replay through {reference_name} changes A1 MAE from "
                     f"{scores[0]['low_rgb_mae']:.2f} to {replay[0]['low_rgb_mae']:.2f}.")
    if "native_rgb" in row:
        native = row["native_rgb"]
        psnr = "infinite" if native["psnr_db"] is None else f"{native['psnr_db']:.2f} dB"
        lines.append(f"Paired native reference: RGB RMSE {native['rmse']:.2f}, PSNR {psnr}.")
    areas = row["inspection_regions"]
    peak = max(areas, key=lambda name: row["wavelet"][name][0]["low_rgb_mae"])
    peak_value = row["wavelet"][peak][0]["low_rgb_mae"]
    lines.append(f"Among the inspected regions, {peak} has a maximum A1 MAE of {peak_value:.2f} "
                 f"at source bounds {list(areas[peak])}.")
    row["findings"] = lines
    return {"title": "Whole-frame agreement", "note": "Compare framing, silhouette and tone on the source grid. "
            "Double edges in the blend can reveal displacement.",
            "columns": ["Source", "Output on source grid", "Equal-weight blend"],
            "rows": [[original, down, Image.blend(original, down, 0.5)]], "lines": lines}


def local_page(name, box, source, native, projected, reference, layers, scores):
    w, h = source.size
    x, y, r, b = box
    native_box = (x*native.width//w, y*native.height//h,
                  (r*native.width+w-1)//w, (b*native.height+h-1)//h)
    locator = source.copy()
    draw = ImageDraw.Draw(locator)
    draw.rectangle((x, y, r-1, b-1), outline="black", width=max(2, min(w,h)//80))
    draw.rectangle((x, y, r-1, b-1), outline="#ffdf53", width=max(1, min(w,h)//160))
    def residual(i):
        a, v = reference[i][0][y:b, x:r], layers[i][0][y:b, x:r]
        return magnitude(np.abs(a-v).mean(axis=2))
    return {"title": f"Local evidence / {name}",
            "note": f"Source rectangle [{x}, {y}, {r}, {b}), in pixels from the upper left. "
                    "The native crop shows reconstructed texture at the same field of view.",
            "columns": ["Source locator", "Source crop", "Native output crop"],
            "rows": [[locator, source.crop(box), native.crop(native_box)]],
            "extra_columns": ["Projected crop", "A1 RGB error", "A4 RGB error"],
            "extra_rows": [[projected.crop(box), residual(0), residual(3)]],
            "scores": scores}
