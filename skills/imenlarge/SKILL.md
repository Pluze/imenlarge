---
name: imenlarge
description: Enlarge one source image through autonomous visual inspection, reference-image generation, digital image processing and iterative source-grid comparison. Deliver the selected high-resolution frame and its illustrated decision report.
---

# Enlarge this image

## Read the photograph

Inspect the complete source. Identify the subjects, composition and features that carry meaning. When the photograph depicts an action, describe its participants and spatial relationship in the optional `action` field. Incorporate any user-specified action as a constraint. Record English observations in `observations.json`. For each `visual_anchors` entry, give a matching rectangle in source pixels under `regions`. Set `primary_region` to the feature or relationship that most affects fidelity. Include its neighboring contours. Record the visible endpoints, width, depth order and lighting. Use separate anchors for nearby surfaces and significant background geometry. Incorporate the user's observations.

Resolve an uncertain identity from the full scene as well as the crop. Name an ordinary object that explains the action, silhouette and scale; render that object with its characteristic shape and surface. When two identities remain credible, render each in its own candidate. Record the uncertainty in the inspection record. Use `interpretation` for plausible details below the source resolution. Identify a concrete object, material and action. Specify which side of each boundary owns the visible edge and how the object relates to its surroundings. Preserve the relative size and spacing supported by the source. Run `imenlarge focus SOURCE observations.json focus.json`.

## Render independent interpretations

1. Give the image generator the complete original and a short request for a faithful high-resolution photograph. Keep its native frame.
2. Generate another complete frame from the original and the output of `imenlarge prompt SOURCE --brief focus.json`. For a small ambiguous contact, include a source crop as a positional guide. Choose interpretations consistent with the brief and source. Where boundaries overlap, identify the depth cues and test the unresolved ordering across candidates. Inspect the actual renders to see which arrangements the generator produced.
3. Keep a single workflow for all generated and processed images with their names, hashes, parents, operations, settings, purposes and outcomes.

## Inspect before selection

Run `imenlarge review SOURCE CANDIDATES --brief focus.json --blind`. Open `visual-comparison.pdf`. Read each frame by itself before consulting its identity. Open `native-crops.png` at 100%. For each candidate:

- Trace each visible boundary at the primary junction. Start outside the interaction and follow it through to its endpoint. Describe where each contour disappears and resumes. If multiple edges belong to one object, trace each separately. Look for the far edge showing through an opaque nearer surface. Inspect the complete adjacent form, internal boundaries, perspective, gravity and light.
- Compare the material, edge definition and native detail to the clearest independent render. Check a textured interior and a quiet surface on the same focus plane. Give a concrete example of fine structure in the selected image. Retain the generator's native dimensions unless the user specifies an output size.
- Inspect the projected source-grid blend and signed residual. For JPEG compare direct resize and recompression. Compare four wavelet levels in the whole frame and the primary region. Use known acquisition settings where available and label other hypotheses as assumed. Check fine bands for ringing, blocks and color bleed. Identify a visible displaced contour or color bias before choosing to correct it.

Record the preferred sample, visible reasons and any shared defect. Open `visual-key.json` to resolve names. In each workflow stage record `aligned`, `revise` or `uncertain` for the full frame and every named anchor. Record visible interpretation cues in `semantic_evidence`.

## Repair and verify

For a shared or unresolved defect, execute a targeted edit within the current run. Use the strongest intact native frame and a crop with both ends of the affected contours. If masking is supported, cover the complete problem and enough adjacent material to reconstruct it. Give the editor a positive physical description of the desired arrangement. Check the junction at native size and the whole scene afterward. When lines cross ambiguously, repair their ordering while preserving the action and the destination of the moving part. Inspect the revised photograph by describing the action a viewer can actually see.

Use `--inspection` or `--workflow` in a working review to build regional revision feedback. Carry the affected edge, next action, user feedback and features to preserve into the revision prompt. If a sound geometric edit loses clarity, use that native image as the base for a detail restoration edit, with the clearest candidate as an optical and material reference. For visible broad color bias, compare a separate `match-tone` copy at multiple strengths or radii. Recheck the primary relationship, other aligned areas and native texture after every intervention.

Select on physical credibility, native clarity and agreement with visible source features. Record the strongest alternative in `comparison_sha256`, remaining uncertainty, and the decisive visual difference. Continue while a concrete repair remains.

## Deliver

Run `imenlarge review SOURCE CANDIDATES --brief focus.json --workflow workflow.json --final` with every distinct output in generation order. The selection needs aligned checks for the whole frame and every source anchor. Record native observations in `candidate_evidence`, measured source-grid observations in `residual_evidence`, and the region, detail gain over interpolation and boundary continuity in `native_review`. Follow each outstanding repair action. If further work requires an unavailable input or tool, report the limitation with the working assessment.

Open the selected image, verify its hash against the selection, render the report and check its viewing path. Deliver the native image and illustrated report.

[Measurement guide](references/evaluation.md) · [Inspection and workflow records](references/workflow.md)
