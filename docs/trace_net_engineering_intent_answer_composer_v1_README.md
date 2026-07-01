# TRACE-Net Engineering Intent Answer Composer v1

This module is H9 in the engineering-brain chain. It consumes an existing H5
engineering answer runner manifest and its H3 engineering answer context pack,
then rewrites the answer only when the question intent needs a more specific
answer shape.

It is designed to improve semantic answer quality for questions like:

- Why was nomenclature missing from the visual route evidence?
- What can TRACE-Net not prove about part number X?
- Is part A interchangeable with part B?
- Does figure N prove installation safety?
- Compare figure A and figure B.

The module does not change retrieval, evidence selection, route planning,
LLaVA output, endpoint/OpenWebUI behavior, or source-truth artifacts.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
- v2 summaries are guidance only and not proof

The module writes only its own JSON/CSV outputs under the requested output
folder.
