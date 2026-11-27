"""Prepare a generation or revision prompt from a photographic brief."""
import argparse
import hashlib
import json
from pathlib import Path


def field(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected a nonempty string for {key}")
    return value.strip()


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(brief, source, parent=None, metrics=None, feedback=None):
    if not isinstance(brief, dict):
        raise ValueError("Expected a brief object")
    if "source_sha256" in brief and brief["source_sha256"] != fingerprint(source):
        raise ValueError("Select the focus record for this source.")
    goal = field(brief, "goal") if "goal" in brief else "Enlarge the supplied photograph."
    lines = [goal,
             "Generate one complete high-resolution frame in the medium of reference 1. Reference 1 is the original frame.",
             "Anchor subject positions, scale, silhouettes, broad color and lighting to reference 1.",
             "Keep relative focus and edge contrast consistent across foreground and background. Recover native optical clarity appropriate to each focus plane. Use the inferred material to generate fine structure below the source resolution.",
             "Maintain the perspective, structure and illumination supported by the source. Show the natural surface finish, subtle ambient reflections and irregularities of an ordinary photograph at that distance. Keep silhouettes and material boundaries consistent with the observed geometry. Preserve depth order where features overlap."]
    if "action" in brief:
        lines.insert(1, f"Depicted action: {field(brief, 'action')}")
    for key, label in [("hard_constraints", "Required"), ("preferences", "Prefer"),
                       ("uncertain", "Unresolved in the source")]:
        items = brief.get(key, [])
        if not isinstance(items, list) or any(not isinstance(v, str) or not v.strip() for v in items):
            raise ValueError(f"Expected a list of nonempty strings for {key}")
        lines.extend(f"{label}: {v}" for v in items)
    anchors = brief.get("visual_anchors", {})
    if not isinstance(anchors, dict):
        raise ValueError("Supply visual_anchors as named observations.")
    for name in anchors:
        if name != "full" and name not in brief.get("regions", {}):
            raise ValueError(f"Give {name} a source-grid region.")
        lines.append(f"Source evidence ({name}): {field(anchors, name)}")
    interpretation = brief.get("interpretation", {})
    if not isinstance(interpretation, dict):
        raise ValueError("Supply inferred scene details by measured region.")
    for region in interpretation:
        if region not in anchors:
            raise ValueError("Anchor each interpretation to a named source observation.")
        lines.append(f"Render this interpretation ({region}): {field(interpretation, region)}")
    lines.append("For unresolved pixels, generate the detail implied by the scene, material and lighting. "
                 "Preserve the physical relationship through the entire contour. Treat sampling blur, block edges and ringing as features of the recorded input. Reconstruct the scene before those encoding effects.")
    if any(v is not None for v in (parent, metrics, feedback)):
        if parent is None or not isinstance(metrics, dict) or not isinstance(feedback, dict):
            raise ValueError("Supply the parent image, its review metrics and its visual feedback")
        if metrics.get("sha256") != fingerprint(source) or metrics.get("brief") != brief:
            raise ValueError("Select the review generated from this source and brief")
        digest = fingerprint(parent)
        candidates = metrics.get("candidates")
        if not isinstance(candidates, list) or any(not isinstance(r, dict) for r in candidates):
            raise ValueError("Select metrics.json from a completed review")
        rows = [r for r in candidates if r.get("sha256") == digest]
        if not rows or field(feedback, "parent_sha256") != digest:
            raise ValueError("Select the review and feedback for this parent image")
        region = field(feedback, "region")
        bands = rows[0].get("wavelet")
        if not isinstance(bands, dict) or region not in bands:
            raise ValueError("Select a measured region or full")
        lines.extend(["Reference 2 is the selected parent. Revise it as a complete frame.",
                      f"Observed defect in {region}: {field(feedback, 'observed')}",
                      f"Change: {field(feedback, 'change')}",
                      f"Preserve: {field(feedback, 'preserve')}"])
        retained = feedback.get("retained", [])
        if not isinstance(retained, list) or any(not isinstance(v, str) or not v.strip() for v in retained):
            raise ValueError("Supply retained observations as a list of strings.")
        lines.extend(f"Retain from prior rounds: {v}" for v in retained)
        remaining = feedback.get("remaining", [])
        if not isinstance(remaining, list) or any(not isinstance(item, dict) for item in remaining):
            raise ValueError("Supply the remaining repairs as a list of regional actions.")
        for repair in remaining:
            lines.append(f"Recheck {field(repair, 'region')}: {field(repair, 'change')}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--brief", type=Path, required=True)
    for name in ("parent", "metrics", "feedback"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args(argv)
    def read(path):
        return json.loads(path.read_text(encoding="utf-8")) if path else None
    try:
        if not args.source.is_file():
            raise ValueError("Supply the original source image")
        print(build(read(args.brief), args.source, args.parent, read(args.metrics), read(args.feedback)))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"imenlarge prompt: {exc}\n")


if __name__ == "__main__":
    main()
