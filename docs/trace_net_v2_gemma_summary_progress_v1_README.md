# TRACE-Net V2 Gemma summary progress v1

Adds live progress output to the V2 Gemma summary runner.

New CLI flags:

```bash
--progress
--progress-every 1
```

Example output:

```text
[trace-net-v2-gemma] starting requested=509 candidates=509 model=gemma4:26b
[trace-net-v2-gemma] start candidate=1/509 completed=0/509 page_id=t_p_120_1176_p000001
[trace-net-v2-gemma] done 1/509 candidate=1/509 page_id=t_p_120_1176_p000001 status=GEMMA_JSON_SUMMARY_SUCCEEDED
[trace-net-v2-gemma] done 2/509 candidate=2/509 page_id=t_p_120_1176_p000002 status=GEMMA_JSON_SUMMARY_SUCCEEDED
...
[trace-net-v2-gemma] finished completed=509/509 attempted=509 errors=0
```

Safety is unchanged:
- no answer permission
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch writes
