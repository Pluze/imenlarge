"""Bind a host's source-only observations to the image before rendering."""
import argparse
import json
from pathlib import Path


def validate_focus(cfg, sha256, size):
    if cfg.get("source_sha256") != sha256:
        raise ValueError("Choose the source used for the focus record.")
    regions = cfg.get("regions")
    anchors = cfg.get("visual_anchors")
    if not isinstance(regions, dict) or not regions or not isinstance(anchors, dict) or set(regions) != set(anchors):
        raise ValueError("Describe one observable relationship for each named source rectangle.")
    interpretation = cfg.get("interpretation", {})
    if not isinstance(interpretation, dict) or any(
        key not in regions or not isinstance(value, str) or not value.strip()
        for key, value in interpretation.items()
    ):
        raise ValueError("Describe each inferred detail in a named source region.")
    if "primary_region" in cfg and (not isinstance(cfg["primary_region"], str) or cfg["primary_region"] not in regions):
        raise ValueError("Select a named source region for primary_region.")
    w, h = size
    for name, rect in regions.items():
        if (name == "full" or not name.strip() or not isinstance(rect, list) or len(rect) != 4
                or any(type(v) is not int for v in rect)
                or not (0 <= rect[0] < rect[2] <= w and 0 <= rect[1] < rect[3] <= h)
                or not isinstance(anchors[name], str) or not anchors[name].strip()):
            raise ValueError(f"Provide source coordinates and visible evidence for {name}.")


def main(argv=None):
    from .review import digest, load
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("observations", type=Path, help="Source relationships recorded by the visual host")
    p.add_argument("output", type=Path, help="New source-bound brief")
    args = p.parse_args(argv)
    try:
        cfg = json.loads(args.observations.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("Supply a source observation object.")
        sha = digest(args.source)
        cfg.setdefault("source_sha256", sha)
        pixels = load(args.source)
        if all(low == high for low, high in pixels.getextrema()):
            raise ValueError("The decoded frame is uniform. Verify the source pixels before recording visible relationships.")
        validate_focus(cfg, sha, pixels.size)
        with args.output.open("x", encoding="utf-8") as out:
            out.write(json.dumps(cfg, indent=2) + "\n")
        print(args.output)
    except (ValueError, OSError) as exc:
        p.exit(2, f"focus: {exc}\n")
