# TRACE-Net Fast Chat Runner Image Route Syntax Fix v1

This focused patch repairs a malformed one-line `if` statement created during the image-route fast chat integration. It rewrites the `part_family` query check and the `image_or_diagram` query check into two normal Python `if` blocks, then validates the runner with `ast.parse`.

Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.
