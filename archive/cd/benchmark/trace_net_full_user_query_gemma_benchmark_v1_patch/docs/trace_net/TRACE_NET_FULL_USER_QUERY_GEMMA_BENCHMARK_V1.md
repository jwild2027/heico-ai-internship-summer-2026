# TRACE-Net Full User-Query Gemma Benchmark v1

This patch adds an isolated full-Gemma canary on port 8127.

Every one of the 180 questions is sent as a real OpenAI-compatible user message
to the existing unified canary. The wrapper then calls `gemma4:26b` exactly once
to write the final user-facing answer.

The upstream unified service still controls:

- query routing;
- source retrieval;
- citations;
- guided candidate discovery;
- follow-up questions;
- visual guidance;
- Self-RAG and CRAG;
- safety boundaries.

Gemma is only the final response writer. Its draft is rejected if it invents a
part number, ATA/manual reference, page, figure, or citation number.

The run is serial and does not artificially sleep. On the Tesla T4, 180 Gemma
calls can take hours. The live 0.0.0.0:8017 endpoint is not modified or stopped.
