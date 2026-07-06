# TRACE-Net H29 CLI Alias Repair v1

Fixes an H29 CLI wrapper mismatch where argparse emits `critic` / `answer_smoke`, but `build_crag_repair_manifest()` may expect a more explicit internal parameter name.

Safety contract: no LLM calls, no database writes, no vector/search writes, no source-truth mutation, no answer permission.
