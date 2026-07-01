# TRACE-Net Engineering Eval Short Run Dirs Fix v1

## Purpose

H6 eval-set runs used full question slugs in nested run directories, for example:

```text
q04_find_part_number_120_50645_005_and_cite_the_source
```

On Windows with `LongPathsEnabled=0`, nested files such as
`trace_net_engineering_answer_context_pack_v1_quality_check.json` can exceed the
260-character `MAX_PATH` limit even when all stage `_write_json` helpers create
parent directories correctly.

This fix shortens H6 per-question run directories to stable, hash-backed names,
while keeping the full question inside the JSON records.

## Safety

This patch does not modify retrieval, proof selection, answer wording, source
artifacts, database writes, OpenSearch/Qdrant/Postgres behavior, or answer
permission logic.

## Expected effect

After applying the fixer, H6 eval run folders should look like:

```text
q01_fig_<hash>
q04_part_<hash>
q05_debug_<hash>
```

This keeps nested stage output paths safely below Windows MAX_PATH.
