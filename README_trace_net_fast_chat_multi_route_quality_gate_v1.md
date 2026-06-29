# TRACE-Net Fast Chat Multi-Route Quality Gate v1

Validates `trace_net_fast_chat_runner_v1` outputs using route-specific rules.

## Supported route checks

- `exact_part_number`: requires fast chat ready, exact answer gate pass, and direct exact records.
- `figure_or_item`: requires figure/item composer readiness and cited figure/item records.
- `part_family`: requires family composer readiness, multiple family part numbers, and no substitute/equivalence wording.
- planned routes such as `image_or_diagram` and `plain_text`: may pass as safe placeholders but are not WebUI-answer-ready.

## Safety contract

Dry-run only. No Postgres, Qdrant, or OpenSearch writes. No source-truth mutation. No answer permission.
