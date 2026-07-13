# TRACE-Net Full-Gemma Validator and Follow-up Fix v1

Fixes five full-user benchmark failures caused by local draft validation, not network or Ollama errors.

- Accepts grounded figure references across `Figure 15, Sheet 1`, `Fig. 15`, and OCR `-igure 15` forms.
- Keeps rejecting genuinely unseen figure numbers.
- Preserves deterministic follow-up questions even when a Gemma draft is rejected and the fallback answer is used.
- Does not weaken part-number, ATA/manual-reference, page-id, citation, or safety validation.
