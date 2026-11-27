# Repository rules

## What belongs in Git

Commit reusable image-processing code, input schemas, source-independent generation and review instructions, measurement definitions, and installation and test tooling. Keep guidance in English. Describe the operation, the evidence it needs and how to check the result.

Use placeholders to demonstrate data formats and procedurally defined geometry to demonstrate measurements. Give numeric constants a purpose in the algorithm or synthetic fixture. Derive runtime coordinates, candidate choices and scene descriptions from the supplied inputs. Apply checks for motion, contact, transparency or occlusion when the photograph supports them.

## What belongs in a run directory

Keep source photographs, supplied benchmarks, generated images, crops, masks, prompts filled with observations, captions, reviewer feedback, workflow records, reports and scores with their run outside the checkout. Keep a benchmark and its intended answer with the evaluator until selection is locked.

Apply the same boundary to comments, filenames, tests, examples, commit messages, pull requests, release notes and attachments. A paraphrase, translation, coordinate pattern, digest, encoded payload or external link can reveal a case as readily as its photograph.

## Reviewing a change

1. Inspect every staged path with `git diff --cached --name-status` and read the full staged diff. Inspect the content and provenance of new assets and fixtures.
2. Trace prompt and selection changes to their inputs. Check that the method works on unrelated subjects, including a static scene where the proposed relationship is absent. Keep case-specific values in the runtime brief.
3. Reproduce a software defect with the smallest synthetic input that exercises it. Check both the intended behavior and existing callers with `python -m unittest discover -s tests -v`.
4. Keep evidence from development runs separate from independent evaluations. Describe the tested capability and its scope in project documentation. Keep individual images, answers and verdicts in the evaluation record.
