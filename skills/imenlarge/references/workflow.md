# Recording an adaptive review

The image-capable host inspects the recorded source features at native size. The evaluator measures source-grid agreement and derives a decision from the recorded visual observations. An aligned set of checks yields `retain`. A region marked `revise` or `uncertain` yields `revise` and carries its next action forward.

For unresolved geometry or texture, `interpretation` maps a source region to its intended physical reading. The generation prompt includes that reading. During inspection, `semantic_evidence` describes the cues a viewer sees in that region. Mark contradictory cues for revision even when the projection closely matches the source. Use the source residual to investigate a specific visible discrepancy.

Use `imenlarge review source.jpg first.png revised.png --brief brief.json --inspection inspection.json` during a run. Supply source and candidate SHA-256 digests, an optional earlier parent digest, and a list of checks. Each check names a measured region and records `status`, `source_evidence`, `candidate_evidence` and `next_action`. The resulting decision includes signed A1 and A4 MAE changes for shared coordinates. Open the corresponding `feedback-NN.json` for the first repair, the observations to preserve and the remaining regional actions. Pass this file to `imenlarge prompt` with the same focus brief, parent image and metrics to build the revision request.

For the final review, pass `--workflow workflow.json --final` with the source-bound focus brief. List each distinct generated or processed frame in the same order as the candidate arguments. Point each stage at its actual parent. A stage rooted in the original uses the source directly. The example uses a hypothetical overlap and shadow to illustrate the record format. Substitute observations, coordinates and file hashes from the current run.

~~~json
{
  "source_sha256": "<source digest>",
  "stages": [
    {
      "candidate_sha256": "<first digest>",
      "name": "First reconstruction",
      "parameters": {"reference": "original", "aspect": "source"},
      "tool": "Reference-image generation",
      "reason": "Resolve surface texture while preserving the overlap.",
      "checks": [
        {"region": "overlap", "status": "revise", "source_evidence": "A narrow edge crosses the upper surface.", "candidate_evidence": "A highlight continues across the boundary.", "next_action": "Trace the contact edge from the original."}
      ]
    },
    {
      "candidate_sha256": "<second digest>",
      "parent_sha256": "<first digest>",
      "name": "Contact revision",
      "native_review": {
        "status": "aligned",
        "region": "overlap",
        "detail_gain": "Fine parallel ridges remain distinct through the curve at output scale.",
        "continuity": "The ridges turn with the near surface and end at its edge. The far highlight resumes beyond it."
      },
      "tool": "Reference-image revision",
      "reason": "Restore the boundary and the interrupted highlight.",
      "checks": [
        {"region": "full", "status": "aligned", "source_evidence": "The subject fills the frame.", "candidate_evidence": "The silhouette and surrounding light remain continuous.", "residual_evidence": "The source-grid blend preserves the outline. Fine texture differs across the textured surface.", "next_action": "Retain the framing."},
        {"region": "overlap", "status": "aligned", "semantic_evidence": "The ridges curve together and end at the near silhouette. The far highlight resumes beyond the edge.", "residual_evidence": "The boundary coincides in the blend. Residual speckles remain on the surface.", "source_evidence": "The near edge covers the far surface.", "candidate_evidence": "The near edge interrupts the highlight at the same height.", "next_action": "Retain the junction."},
        {"region": "shadow", "status": "aligned", "source_evidence": "The shadow broadens toward the right.", "candidate_evidence": "The falloff widens along the same edge.", "residual_evidence": "The blend preserves the shadow boundary, with a small brightness shift inside.", "next_action": "Retain the falloff."}
      ]
    }
  ],
  "comparison_sha256": "<first digest>",
  "selected_sha256": "<second digest>",
  "selection_reason": "The revised contact matches the visible overlap."
}
~~~

For a masked working review, pass `--blind` with the candidate files and focus brief. The PDF groups up to three shuffled samples with the same original. Record the visual preference before opening the identity key.

Set the optional `comparison_sha256` to the closest alternative for a side-by-side selection. Stage names appear in the report and default to the image filenames.

The reading PDF opens with the selection and marked crop, compares source-grid and native evidence, then traces the processing routes. The HTML and evidence PDF provide the full processing record. Open native-crops.png at 100% to inspect unscaled pixels; large areas use a centered window. JSON preserves hashes, stage links, numeric evidence and selection. A source-only review still provides measurements and automatic inspection tiles.

## Matching tone

The optional `match-tone` command compares encoded RGB on the source grid, smooths each channel's signed residual with a Gaussian and upsamples the correction into the native frame. Set `--radius` in source pixels to control the spatial scale and `--strength` from 0 to 1 to control the amplitude. Compare the native parent with the result at a boundary and in a textured interior. A named contact can be anchored through an optional rectangle, blending the source-grid residual into the broad correction with a feathered mask. The output uses an 8-bit RGB PNG. A follow-up review quantifies clipping and local changes through the luma distribution, residuals and crop panels.
