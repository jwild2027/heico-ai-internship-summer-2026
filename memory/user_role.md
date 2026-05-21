---
name: user-role
description: User is jwild@heico.com, doing an AI internship at HEICO summer 2026, building this RAG project solo. Frame suggestions accordingly.
metadata:
  type: user
---

User: Justin Wild, jwild@heico.com. Repo is `heico-ai-internship-summer-2026` — solo internship project. Currently iterating actively (recent branches: rag-part1, rag-part2, copali-part1, benchmarks-and-latency, tesseract).

**Working style observed:**
- Wants short, copy-pasteable commands rather than long explanations.
- Reports symptoms rather than digging through code first — verify the actual DB/file state before accepting their framing (e.g., the "rag.db is being overwritten" report turned out to be a real but different bug: re-ingestion accumulating page rows).
- Prefers the safeguard approach: add UNIQUE constraints, logging, and sanity checks rather than just trust-the-code.

**How to apply:** Lead with the answer or the command. Show diagnostic queries before making code changes when the reported symptom is ambiguous. When suggesting fixes, offer 2-3 concrete options with tradeoffs rather than picking one silently.
