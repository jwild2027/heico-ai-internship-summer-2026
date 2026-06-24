# TRACE-Net E2E Image Visual Observer Route v34.3

## Purpose

v34.3 adds technical drawing mode to the image visual route. It is intended for uploaded engineering/mechanical diagrams, not marketing graphics or generic infographics.

## Contract

- LLaVA/image observations are guidance only.
- OCR text candidates are guidance only.
- OpenCV layout and geometry cards are guidance only.
- Technical drawing dimensions, hole counts, centerlines, hatching, circles, and CAD-like reconstruction are not proof authority.
- Source-truth or human review is required before using extracted geometry in technical documentation.
- This stage does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch.

## New v34.3 outputs

- `technical_geometry_cards`
- `technical_drawing_feature_cards`
- `technical_drawing_candidate_count`
- `technical_drawing_feature_count`
- `dimension_text_candidate_count`
- `circle_candidate_count`
- `line_candidate_count`
- technical diagram draft cards with `technical_drawing_json`

## Intended behavior

For an uploaded engineering drawing, the endpoint should identify the image as a `technical_drawing_candidate`, extract geometry guidance, and return a technical diagram draft. The draft should include possible views and geometry features such as:

- side/section view
- front/flange view
- central bore
- bolt-hole pattern
- dimension lines
- section hatching
- centerlines
- circle/arc geometry

All of these remain guidance-only until confirmed.
