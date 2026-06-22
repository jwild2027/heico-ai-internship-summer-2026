# TRACE-Net E2E Local Endpoint Citation Value Hotfix v2

This hotfix keeps the local endpoint contract unchanged while cleaning WebUI-facing output.

It fills blank structured citation `normalized_value` fields from field/value fragments already present in the final-gate smoke draft text, such as `covered_part_number=120-36833-001 on t_p_120_1176_p000003`.

It also fixes a small display typo where `on` could be concatenated with a TRACE-Net page id, for example `ont_p_...` becomes `on t_p_...`.

Safety contract remains unchanged: responses are local endpoint smoke drafts, not production final answers. The endpoint does not mutate source truth or write to Postgres, Qdrant, OpenSearch, or upload anything.
