# Evaluating a reconstruction

## Read the frame at two sizes

On the original pixel grid, use the overlay to compare the framing, area occupied by the subject and position of major contours. A doubled edge often reveals displacement. Next, open the native candidate at 100%. Follow a contour through a contact point, inspect which surface overlaps the other and check how the shadow meets the object. Native texture should follow the material and lighting around it.

## Interpret the scales

The evaluator applies EXIF orientation, composites transparency on white and reads 8-bit RGB values. Convert inputs with different color profiles to a common sRGB space before review. Use corresponding still frames with matching aspect ratios and source dimensions of at least 16 pixels per axis. A Lanczos resize projects the candidate onto the source grid.

A separable cubic B-spline filter with taps [1, 4, 6, 4, 1]/16 smooths each successive approximation. The four stages use tap spacings of 1, 2, 4 and 8 source pixels and reflected borders. A1 through A4 show progressively broader structure. Each detail band W is the difference between successive approximations, projected onto encoded luma using 0.299 R + 0.587 G + 0.114 B.

| Reading | Interpretation |
|---|---|
| Low RGB MAE | Mean absolute channel difference between corresponding approximations, in 8-bit RGB units. Lower values indicate closer agreement at that scale. |
| Detail correlation | Pearson correlation of the two detail bands. Values near one indicate similarly located and oriented variations. A constant band gives an undefined correlation. |
| Residual maps | Navy indicates zero error. Yellow indicates 40 units or more. A common color scale supports comparison across rounds. |
| Regional scores | Each region samples the full-frame transform. At coarser scales, neighboring pixels contribute to the region's reading. |
| Known-reference PSNR | When supplied with a same-size native reference via `--truth`, the report also measures native RGB error. Identical frames have zero RMSE and infinite PSNR, represented by a null PSNR in JSON. |

## Write a useful edit

Give the generator a spatially identifiable change. Identify the measured region, describe the visible discrepancy, and specify the geometric or tonal change and the adjacent features to preserve.

After rendering, revisit the named region and inspect the rest of the frame for movement. Weigh source-grid scores alongside the native appearance. For example, a sharp contour at the wrong position can look convincing in isolation and still produce a doubled edge in the overlay. Record which evidence determined the selection.

## Replay a known observation process

The standard projection downsamples each intact candidate to the oriented source dimensions. Add a `projection` object to the brief for a second projection through blur, noise and JPEG. Both projections use the same source, regions, overlay and scale definitions. The report stores the original measurements under `wavelet` and the second measurements under `replay_wavelet`.

```json
{"projection": {"status": "known", "blur_radius": 0.25, "noise_sigma": 2, "seed": 442, "jpeg_quality": 52, "subsampling": 2}}
```

Blur uses Pillow GaussianBlur in low-resolution pixels. Independent Gaussian noise uses 8-bit RGB units, NumPy default_rng, rounding and clipping. JPEG subsampling 2 denotes 4:2:0. Omitted stages are skipped. For controlled degradation, confirm that projecting the held-out reference reproduces the input with the recorded settings. For an existing photograph with unknown acquisition history, use the standard projection or label a plausible recompression profile `assumed`. Evaluate broad structure and corresponding detail bands alongside native appearance. Check fine-scale differences for block boundaries, ringing, chroma bleed and blur. Use edges supported across scales to locate geometric drift. Interpret differences that persist under plausible degradation in light of the depicted scene; a real narrow feature can also appear in a single band. Record the visible reason for each repair.

## Optional controls

`imenlarge review source.jpg parent.png revised.png` creates a fresh report beside the last candidate. The default JPEG check reuses available quantization tables and chroma sampling from ordinary grayscale and RGB JPEGs. This measures sensitivity to the file encoding; the original camera processing remains unknown.

Use `--brief brief.json` for named source-pixel regions and an optional explicit projection, `--out DIRECTORY` for a chosen report location, or `--truth FILE` for a paired native reference. Every review uses available source JPEG tables and sampling unless the brief declares a projection. A supplied reference goes through the same observation process as each candidate. For recorded experiments the `imenlarge prompt` helper accepts a brief, or a parent, its metrics and feedback for a revision.

## Evaluate with a held-out enlargement

Give the generating host the project and low-resolution source. Keep the supplied comparison image with the evaluator until the host delivers its selection. Preserve the selected hash and run a separate review with `--reference REFERENCE`. The two enlargements can have different output dimensions at the source aspect ratio. Use `--truth` for a known, pixel-aligned native image in a controlled experiment. The reading PDF places the source, candidate and supplied reference side by side at the same field of view. It includes source-grid measurements for both enlargements. Inspect visual plausibility, native detail and fidelity to visible source relationships before recording the outcome. For a later project revision, start a fresh run from the low-resolution source.

## Read the illustrated report

Each review publishes three files together. Open `review.pdf` for the paginated evidence, `review.html` for the embedded images and named native crops, and `metrics.json` for full-precision measurements, image hashes, inspection coordinates and derived findings. Candidate names identify the inputs. The workflow records their hashes and parent links.

1. Compare the source, projected output and equal-weight blend. The overview lists fine and coarse color error, the minimum measurable detail correlation, and the largest local A1 error among the inspected regions. These measurements describe agreement at the observed resolution. Fine native texture remains a visual interpretation unless a paired native reference is supplied.
2. Read each scale row from left to right. The source and output detail maps encode signed luminance. Their signed difference uses output minus source, so rust marks a positive change and blue a negative change. The common display endpoints are -32 and +32 in 8-bit units. The final column measures absolute low-pass RGB error on a separate 0 to 40 scale. Tables include unclipped mean absolute detail error and Pearson correlation. A constant band has an undefined correlation.
3. Follow a marked region from the source to the native output crop, then compare its projection and fine/coarse residual maps. The automatic selector divides the source into a 4 by 4 grid. It selects the tile with the greatest mean absolute W1 source detail and the tile with the greatest mean A1 RGB error. Ties follow reading order, and coincident boxes share a panel. The texture tile stays comparable across rounds; the peak residual tile follows each candidate. Named brief regions complement the automatic tiles with subject-specific contact points, silhouettes or boundaries.
4. For JPEG replay or a declared observation profile, compare the second set of maps and regional scores to the direct projection. A batch begins with a cross-frame summary of A1 and A4 error. Use the native crops and signed maps to interpret trade-offs across candidates.
