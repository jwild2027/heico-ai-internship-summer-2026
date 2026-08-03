# TRACE-Net Router, Follow-up, and Retrieval Benchmark v1

## Purpose

This patch broadens guided clarification beyond partial part-number prefixes.

Example:

> I would like a part that is a hinge.

TRACE-Net now routes this to descriptive part discovery and asks for:

- possible part-number characters, prefix, suffix, or dash number;
- manufacturer or company;
- ATA/system/manual context;
- more specific physical or functional details;
- figure, table, page, or nearby-text context.

## Follow-up policy

Follow-ups are deterministic and based on query atoms. An LLM is not allowed to
invent routes, source fields, or evidence. Exact part-number lookups proceed
without forced clarification. Broad visual, table, procedure, and safety
questions receive contextual follow-up suggestions, especially when retrieval
does not produce direct evidence.

## Benchmark

The bank contains 180 questions across:

- partial part prefixes and contains clues;
- descriptive nomenclature and function clues;
- manufacturer and ATA clues;
- exact part and manual references;
- figures and visuals;
- tables and IPL text;
- procedures, warnings, and cautions;
- safety, approval, fit, effectivity, and interchangeability;
- vague clarification and general source-truth questions.

The runner can execute router/follow-up checks alone or add read-only v27
retrieval checks with `--manifest`.

## Safety contract

- no source-truth mutation;
- no Postgres, Qdrant, or OpenSearch writes;
- no final-answer permission from the router or follow-up planner;
- approval and interchangeability questions require explicit source authority.
