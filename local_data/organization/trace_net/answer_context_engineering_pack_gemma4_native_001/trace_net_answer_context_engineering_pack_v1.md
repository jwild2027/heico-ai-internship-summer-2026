# TRACE-Net Answer Context Engineering Pack v1

Quality status: **PASS**

## Summary

- Question intent: `part_number_with_nearby_similarity`
- Retrieval evidence records: `8`
- Direct evidence records: `1`
- Nearby/similar evidence records: `7`
- Citation count: `8`
- Prompt chars: `3501`
- Violations: `0`

## Prompt Preview

```text
You are TRACE-Net's final answer drafter for scanned technical manuals.
Use only the provided evidence. Do not invent part numbers, pages, effectivity, quantities, or applicability.
Every factual claim must cite one or more citation labels like [E1].
If direct evidence does not prove the requested part, say that the result is a candidate and explain the limitation.
Keep the answer short and operational: direct finding, nearby/similar evidence, citations, and safety note.

QUESTION: Find part number 120-29073-001 and nearby similar parts. Use TRACE-Net evidence and cite pages.
QUESTION_INTENT: part_number_with_nearby_similarity
QUERY_PART_NUMBERS: 120-29073-001

DIRECT EVIDENCE:
E1: page=5, page_id=t_p_120_1176_p000005, route=table, targets=opensearch,postgres_graph,qdrant, score=100.0. Excerpt: No text excerpt available in payload; use citation metadata only.

NEARBY / SIMILAR EVIDENCE:
E2: page=45, page_id=t_p_120_1176_p000045, route=table, targets=opensearch,postgres_graph,qdrant, score=100.0. Excerpt: No text excerpt available in payload; use citation metadata only.
E3: page=55, page_id=t_p_120_1176_p000055, route=table, targets=opensearch,postgres_graph,qdrant, score=100.0. Excerpt: No text excerpt available in payload; use citation metadata only.
E4: page=65, page_id=t_p_120_1176_p000065, route=table, targets=opensearch,postgres_graph,qdrant, score=100.0. Excerpt: No text excerpt available in payload; use citation metadata only.
E5: page=75, page_id=t_p_120_1176_p000075, route=table, targets=opensearch,postgres_graph,qdrant, score=100.0. Excerpt: No text excerpt available in payload; use citation metadata only.
E6: page=85, page_id=t_p_120_1176_p000085, route=table, targets=opensearch,postgres_graph,qdrant, score=100.0. Excerpt: No text excerpt available in payload; use citation metadata only.
E7: page=95, page_id=t_p_120_1176_p000095, route=table, targets=opensearch,postgres_graph,qdrant, score=100.0. Excerpt: No text excerpt available in payload; use citation metadata only.
E8: page=105, page_id=t_p_120_1176_p000105, route=table, targets=opensearch,postgres_graph,qdrant, score=100.0. Excerpt: No text excerpt available in payload; use citation metadata only.

OTHER SUPPORTING EVIDENCE:
None.

CITATION MAP:
E1 => page_id=t_p_120_1176_p000005, page=5, source_member=00000005.tif, sha256=8980a6e91d7cc2f40a8510315d8610595243d7033621c00bdaec782a41aa1e7b
E2 => page_id=t_p_120_1176_p000045, page=45, source_member=00000045.tif, sha256=53cdcd406800ffd8f8c7f062ababe097a6126caa647f8522e563a824f52d46ef
E3 => page_id=t_p_120_1176_p000055, page=55, source_member=00000055.tif, sha256=be1a6d7a948bf87c345c9f3bc171ce7de6ac33be440ab0bebe8005f081b6e5ef
E4 => page_id=t_p_120_1176_p000065, page=65, source_member=00000065.tif, sha256=9e653b24af5bea3cdab6210cb3985630680286d970799032d5dd8f6cebfadbf8
E5 => page_id=t_p_120_1176_p000075, page=75, source_member=00000075.tif, sha256=6cee623c93733cfafb8f8096590ce5ee89535c43db33fcfb57d88fc5eed7e300
E6 => page_id=t_p_120_1176_p000085, page=85, source_member=00000085.tif, sha256=107a00213b8870401e892812265b591de047ab379fd694679f3f04a2115e0b40
E7 => page_id=t_p_120_1176_p000095, page=95, source_member=00000095.tif, sha256=54b2346051107a572f935aa3f05eab3c311fc239faf077a2e00119753ee5cc7d
E8 => page_id=t_p_120_1176_p000105, page=105, source_member=00000105.tif, sha256=d6b387f0d300288ce3109a81d79d8719d4620d2b300525643b57bc4e7a4095af

SAFETY: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.
```