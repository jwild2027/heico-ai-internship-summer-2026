# TRACE-Net Canonical Engram Rule Registry v1

## Purpose

This registry stores each reusable Engram behavior rule once.

The existing H30 regression packs now store:

- route and claim triggers;
- route-specific examples;
- source/provenance;
- `inherits` references.

They no longer copy the canonical rule text or policy effects.

## Runtime flow

```text
route/episode atom
→ inherits canonical rule IDs
→ registry resolves rules
→ selector removes repeated rule references
→ policy compiler validates effects
→ router and presentation code consume the validated policy
```

## Important boundary

The registry contains behavior policy only. It is:

- not source evidence;
- not citable;
- not answer permission;
- not a database command store;
- not allowed to execute retrieval.

## Quality gate

The checker requires:

- unique canonical rule IDs;
- no repeated normalized rule meanings;
- readable titles and behavior fields;
- guidance-only proof role;
- no answer permission;
- no source-truth or mutation permission.

## Check command

```bash
PYTHONPATH=. python -B \
  scripts/check_trace_net_h30_engram_canonical_registry_v1.py \
  --registry \
  local_data/organization/trace_net/engram_canonical_rule_registry_v1/trace_net_engram_canonical_rule_registry_v1.json
```
