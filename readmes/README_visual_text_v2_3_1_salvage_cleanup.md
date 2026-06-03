# Visual text v2.3.1 salvage cleanup

This patch changes the visual-text cleanup/scoring layer so repaired leakage is
not treated the same as residual leakage.

The v2.3 cleanup layer correctly detected many raw model-output issues, but it
also assigned hard-fail trust tier D to records even after the cleanup pass had
successfully removed prompt-template text or split inline section bleed.

v2.3.1 keeps both signals:

- `prompt_template_repaired_records`: raw model output had template text, and cleanup removed it.
- `prompt_template_leakage_records`: template text still remains after cleanup.
- `section_bleed_repaired_records`: raw model output had inline section bleed, and cleanup split it.
- `section_bleed_records`: section bleed still remains after cleanup.

Quality gates such as `--max-prompt-template-leakage-records 0` now check the
residual cleaned artifact, not the pre-cleanup raw model output.

Records are still downgraded to review tier C when they have hallucination risk,
missing table extraction, suspicious phrases, or other review signals. They are
not automatically tier D merely because the postprocessor repaired a formatting
problem.
