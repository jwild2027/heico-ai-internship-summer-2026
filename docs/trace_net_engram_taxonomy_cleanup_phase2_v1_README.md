# TRACE-Net Engram Taxonomy Cleanup — Phase 2

## Purpose

This phase fixes the difference between temporary working state and persisted
behavior memory.

Previously, the committed H17 artifact contained static records labeled
`working_memory`. It also lost readable IDs and behavior fields that already
existed in the Engram core.

## Changes

- Working memory is runtime-only.
- Static summary-boundary memory becomes semantic memory.
- Unknown-part handling becomes procedural memory.
- Saved query-planner examples become episodic memory.
- Core `engram_id` becomes the active atom ID.
- Former hash IDs remain available as aliases.
- `good_behavior` and `bad_behavior` are retained.
- Static working-memory records are rejected by validation.

## Runtime working-memory schema

The live policy compiler continues to create the current request state:

- question
- route
- requested claims
- requested part numbers
- searches attempted
- evidence found
- evidence rejected
- best result
- unresolved fields
- remaining repair budget
- Engram policy hash

That object is temporary and has `persist_source_truth=false`.

## Safety

This phase performs no database writes and changes no source facts. It changes
only the organization, readability, and validation of behavior memory.
