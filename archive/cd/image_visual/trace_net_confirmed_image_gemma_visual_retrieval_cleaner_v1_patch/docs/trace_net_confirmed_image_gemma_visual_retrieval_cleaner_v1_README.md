# TRACE-Net Confirmed Image Gemma Visual Retrieval Cleaner v1

Deterministic post-cleaner for completed Gemma visual cards.

It removes prompt leakage and unrelated keywords from retrieval text, normalizes
figure refs, removes generic callouts, forces retrieval-only/not-final-proof
wording, and keeps safety flags false.

No model calls are made.
