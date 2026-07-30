# TRACE-Net NHA N17 real-situation Gemma gate

N17 changes the live acceptance policy. Deterministic unit tests remain local,
but every non-synthetic live request must prove a real model-backed answer path.

## Live policy

- Recognized NHA questions: exactly one constrained `gemma4:26b` writer call.
- Non-NHA passthrough control: exactly one upstream cognitive-model call.
- Synthetic benchmark/security probes: zero model calls and zero synthetic access.
- A passthrough response cannot pass merely because HTTP 200 was returned.

The proxy exposes overall call telemetry separately from the NHA-writer count:

- `X-Trace-Net-Model-Calls`
- `X-Trace-Net-Model-Path`
- `X-Trace-Net-Upstream-Calls`
- `X-Trace-Net-Model-Prompt-Tokens`
- `X-Trace-Net-Model-Completion-Tokens`

## Production-language regressions

The live gate covers conversational direct-parent comparisons, direct contents,
children-versus-descendants, ambiguous-parent explanations, IPL evidence wording,
and benchmark-identifier blocking.

## Required live-20 result

- 19 model-backed requests
- 19 total model calls
- 18 NHA constrained-Gemma paths
- 1 upstream cognitive path
- 1 allowed zero-call synthetic block
- 0 unexpected zero-call requests
- 0 source/database writes
