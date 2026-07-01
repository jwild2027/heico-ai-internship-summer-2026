# TRACE-Net Engineering Context Draft Packet v1

Packages only Self-RAG-approved engineering context packs into Gemma-ready draft packets.

This is not the final answer API. It prepares a constrained prompt/context packet for Gemma:
- source-truth evidence
- candidate evidence
- missing evidence
- forbidden claims
- answer format contract
- Self-RAG summary
- strict draft-only rules

It does not call an LLM, execute retrieval, answer the user, write DBs, mutate source truth, or grant final answer permission.
