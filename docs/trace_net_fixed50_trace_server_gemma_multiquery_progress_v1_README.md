# TRACE-Net Fixed 50 TRACE Server + Gemma Multi-query Progress Runner v1

Runs the fixed 50 evaluation questions through TRACE-Net ask with bounded query variants, selects the response with the strongest citation/proof-context count, builds an Engram work-order prompt, then calls Gemma through Ollama.

Safety contract:
- Engram guidance is never proof.
- Source-trace-ready without citations is a failure.
- Engram/policy text used as source proof is a failure.
- No answer permission or source-truth mutation is granted.
- No database/search/vector writes are attempted by this runner.

Use when the first fixed-50 run shows weak retrieval for known buckets such as Figure 69, DF250040-501, or paper towel dispenser.
