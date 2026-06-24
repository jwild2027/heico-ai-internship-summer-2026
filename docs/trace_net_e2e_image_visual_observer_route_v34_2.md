# TRACE-Net E2E Image Visual Observer + OCR/OpenCV Fusion Route v34.2

This stage strengthens the image visual route by adding OCR/OpenCV grounding before final answers and diagram drafts are returned.

## Purpose

- Accept OpenAI-style image payloads from WebUI/message content.
- Build image quality cards.
- Build OCR text candidate cards.
- Build OpenCV/PIL layout region cards.
- Build LLaVA visual observer cards.
- Suppress or downgrade LLaVA visible-text claims that OCR does not confirm.
- Build Mermaid/JSON diagram draft cards from OCR/OpenCV-fused guidance.
- Keep every visual/diagram observation guidance-only, not proof authority.

## Model endpoint

- Model ID: `trace-net-e2e-image-ocr-opencv-fusion-llava-v34-2`
- Windows base URL: `http://127.0.0.1:8031/v1`
- Open WebUI Docker base URL: `http://host.docker.internal:8031/v1`

## Safety contract

- No source-truth mutation.
- No answer permission.
- No writes to Postgres, Qdrant, or OpenSearch.
- LLaVA observations are guidance only.
- OCR text candidates are guidance only.
- OpenCV/PIL layout regions are guidance only.
- Source-truth or human confirmation is required before factual part/manual claims.

## Key telemetry

- `ocr_text_card_count`
- `ocr_text_candidate_count`
- `opencv_layout_card_count`
- `opencv_layout_region_count`
- `grounded_visual_package_count`
- `unconfirmed_llava_text_claim_count`
- `hallucinated_text_suppression_count`
- `diagram_draft_card_count`
- `diagram_draft_guidance_only_count`

## WebUI test prompts

- `Inspect this image and describe visible structure.`
- `Turn this image into a diagram draft.`
- `Does this image contain callouts?`

## Expected behavior

For diagram requests, the endpoint should return a Mermaid diagram draft plus text explaining that the draft is guidance only and not a verified technical drawing. The answer should prefer OCR-confirmed visible text over raw LLaVA text guesses.
