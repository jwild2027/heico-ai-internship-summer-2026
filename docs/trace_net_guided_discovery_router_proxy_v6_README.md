# TRACE-Net Guided Discovery Router Proxy v6

Router/proxy v6 keeps the v5 behavior and fixes the remaining full 50-question discovery-smoke failures:

- answer-pressure / disambiguation questions now go to fast clarification mode instead of expensive candidate search
- standard-prefix + component questions such as `MS24693 ... correct screw ... ashtray` ask narrowing questions first
- broad family questions such as `Which 120-36833 part is the right one...` ask for dash variant, configuration, and source authority first
- procedural partial-answer questions ask for candidate-discovery/source-trace boundaries instead of timing out
- prefix parsing no longer captures helper words like `WITH` or `IT`
- page/figure numbers are filtered from digit-like part clues

Safety contract: read-only, no Postgres/Qdrant/OpenSearch writes, no source-truth mutation, no final-answer permission.
