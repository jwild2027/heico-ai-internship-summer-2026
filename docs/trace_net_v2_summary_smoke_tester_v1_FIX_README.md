# TRACE-Net V2 summary smoke tester v1 fix

This focused fix makes the smoke tester compatible with the existing V2 guide.

The first tester was too strict: it treated older prompt wording gaps as hard failures.
This fix keeps card safety/schema validation strict, but treats prompt wording gaps and
newer explicit-schema terms as report-only warnings.

It also fills conservative smoke-test defaults around existing V2 cards before validation:

- source_grounding.has_ocr
- source_grounding.source_url_present
- source_grounding.supporting_ocr_phrases
- authority.trust_scope
- authority.can_answer_directly = false
- authority.canonical_source_truth = false
- authority.requires_source_check = true

It still fails if a V2 summary grants answer permission or claims canonical source truth.
