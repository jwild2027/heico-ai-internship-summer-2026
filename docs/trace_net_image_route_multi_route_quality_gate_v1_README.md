# TRACE-Net Image Route Multi-Route Quality Gate v1

This quality gate validates `image_or_diagram` fast-chat adapter responses before WebUI use.

Rules:

- route type must be `image_or_diagram`
- adapter quality must be PASS
- WebUI answer readiness can be required
- citations and source-trace-ready citations can be thresholded
- part-number identity claims require linked source-traced citations
- LLaVA-only part identity claims fail
- unsupported replacement/effectivity/interchangeability/safety claims fail
- write attempts, answer permission, and source-truth mutation must remain zero
