"""Match broad RGB tone to the observed frame and anchor selected contact boundaries."""
import argparse
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter


def tone_metrics(source, projected):
    src = np.asarray(source, dtype=float)
    out = np.asarray(projected, dtype=float)
    weights = np.array([0.299, 0.587, 0.114])
    sy, oy = src @ weights, out @ weights
    return {"rgb_bias": (out-src).mean(axis=(0, 1)).tolist(),
            "source_endpoint_pct": float(100*np.mean((src == 0) | (src == 255))),
            "output_endpoint_pct": float(100*np.mean((out == 0) | (out == 255))),
            "luma_bias": float((oy-sy).mean()),
            "luma_mae": float(np.abs(oy-sy).mean()),
            "source_luma_quantiles": np.percentile(sy, [10, 50, 90]).tolist(),
            "output_luma_quantiles": np.percentile(oy, [10, 50, 90]).tolist()}


def match(source, candidate, regions=(), *, radius=None, strength=1.0):
    w, h = source.size
    if abs(candidate.width/w-candidate.height/h)*min(w,h) > 1.01:
        raise ValueError("Supply a candidate with the source aspect ratio.")
    if radius is not None and (not np.isfinite(radius) or radius <= 0):
        raise ValueError("Choose a positive finite smoothing radius in source pixels.")
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("Choose a correction strength between zero and one.")
    projected = candidate.resize(source.size, Image.Resampling.LANCZOS)
    residual = np.asarray(source, dtype=np.float32) - np.asarray(projected, dtype=np.float32)
    sigma = max(2.0, min(w, h)/96) if radius is None else radius
    field = gaussian_filter(residual, (sigma, sigma, 0))
    mask = np.zeros((h, w), dtype=np.float32)
    for x, y, r, b in regions:
        if not (0 <= x < r <= w and 0 <= y < b <= h):
            raise ValueError("Supply a half-open rectangle inside the source.")
        mask[y:b, x:r] = 1
    if regions:
        weight = gaussian_filter(mask, 2)[:, :, None]
        field += weight * (residual-field)
    field *= strength
    native = np.asarray(candidate, dtype=np.float32).copy()
    for ch in range(3):
        native[:, :, ch] += np.asarray(Image.fromarray(field[:, :, ch]).resize(
            candidate.size, Image.Resampling.BICUBIC))
    return Image.fromarray(np.uint8(np.clip(np.rint(native), 0, 255)))


def main(argv=None):
    if __package__:
        from .review import load
    else:
        from review import load
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("output", type=Path, help="Fresh PNG output path")
    p.add_argument("--anchor", type=int, nargs=4, action="append", default=[],
                   metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    p.add_argument("--radius", type=float, help="Tone-field smoothing radius in source pixels")
    p.add_argument("--strength", type=float, default=1.0, help="Fraction of the correction to apply (0 to 1)")
    args = p.parse_args(argv)
    try:
        if args.output.suffix.lower() != ".png":
            raise ValueError("Choose a PNG output path.")
        result = match(load(args.source), load(args.candidate), args.anchor, radius=args.radius, strength=args.strength)
        with NamedTemporaryFile(dir=args.output.parent, suffix=".png") as scratch:
            result.save(scratch.name)
            os.link(scratch.name, args.output)
        print(args.output)
    except (ValueError, OSError) as exc:
        p.exit(2, f"match-tone: {exc}\n")
