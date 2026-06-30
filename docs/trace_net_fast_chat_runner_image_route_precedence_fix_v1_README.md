# TRACE-Net Fast Chat Runner Image Route Precedence Fix v1

Fixes figure-only visual questions that were misrouted as `figure_or_item`.

Example:

- `What does figure 69 show?` should route to `image_or_diagram` when `--image-visual-evidence-pack` is supplied.
- `Show figure 85 item 1` should remain `figure_or_item` because it contains an item/callout.

Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, no answer permission.
