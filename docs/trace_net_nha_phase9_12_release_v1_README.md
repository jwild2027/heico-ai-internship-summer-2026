# TRACE-Net NHA Phases N9–N12

This release closes the NHA implementation sequence:

- **N9:** promote the validated real N4 relationship artifacts into a checksum-verified, Git-trackable release directory;
- **N10:** run a live 20-question OpenAI-compatible endpoint gate;
- **N11:** launch and verify the server sidecar in no-override shadow mode;
- **N12:** switch to gated mode and run the final server release gate.

The promoted release contains only the N4 relationships, N4 answer key, N4 quality artifact, and a release manifest. N5 synthetic artifacts are neither loaded nor copied.

The N12 proxy adds routing headers, an authenticated `/v1/nha/decision` diagnostic endpoint, and a production-safe synthetic-identifier response. Reserved `990-xxxxx-xxx` identifiers are not forwarded to the upstream LLM.

The live-20 bank contains 18 real NHA route questions, one non-NHA passthrough control, and one synthetic safe-block control. Streaming and non-streaming requests are both exercised.
