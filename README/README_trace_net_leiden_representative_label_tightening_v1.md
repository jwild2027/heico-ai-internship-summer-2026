# TRACE-Net Leiden Representative Label Tightening v1

Read-only refinement layer for hydrated Leiden communities.

It takes the Leiden Category Summary Hydrator output and converts noisy raw category counts into navigation-safe community profiles. Each profile receives a refined label, normalized macro category counts, representative pages, representative part numbers, a navigation intent, a navigation confidence, and review reasons when the community is mixed or lacks page membership.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

Community labels, category summaries, and Leiden memberships remain navigation/ranking helpers only. They cannot prove claims.
