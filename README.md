# imenlarge

A nod to MATLAB’s `imread`, `imshow` and `imresize`.

Give an image-capable agent a low-resolution image and ask for an enlargement. The agent records visible relationships, supplies a physical interpretation for unresolved detail and renders candidates. It inspects object boundaries, material and light at delivery size, then projects each candidate through the observation process to locate differences across scales. The delivery includes the selected enlargement, the visual reason for the choice and the measured agreement with the source.

[Use the skill](skills/imenlarge/SKILL.md) · [Repository rules](AGENTS.md)

## Compare frames

Install the local review tool with `python -m pip install .` (Python 3.10+). From the project checkout:

```sh
imenlarge review source.jpg candidate.png
```

Open the printed HTML path or the adjacent `review.pdf`. Each run also writes `metrics.json` with source-grid coordinates, measurements and derived findings. Compare the whole frame and automatically selected crops, then follow color and signed detail residuals from fine to coarse. Include additional candidates in the same command for a cross-round comparison. JPEG replay uses the source quantization tables and chroma sampling when available.

[Evaluation details and optional settings](skills/imenlarge/references/evaluation.md) · [MIT license](LICENSE)

An image-capable host can choose reference generation, a targeted revision or digital tone matching at each stage. Use `imenlarge match-tone source.jpg candidate.png matched.png` to match broad lighting and color. The [adaptive review workflow](skills/imenlarge/references/workflow.md) records branch choices, visual observations and source-aligned crops in the final report.

The reading PDF opens with the selection and visual evidence. Source-grid comparisons follow. The processing appendix identifies each version, its input, operation and outcome. Use `review --brief focus.json --workflow workflow.json --final` for delivery. The extended panels are available in `evidence.pdf`.

The files in `examples/` illustrate the record format with hypothetical geometry. Supply coordinates and observations from the current source.

Before generation the visual host records scene-defining relationships with `imenlarge focus SOURCE observations.json focus.json`. Pass that record to `review --brief focus.json` to track inspection coverage. Added-detail and lost-detail windows independently locate concentrated source-grid changes.
