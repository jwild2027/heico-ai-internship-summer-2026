# TRACE-Net Engram Non-Redundancy Phase 3

Phase 3 introduces the canonical rule registry.

## Before

The same lesson could exist in multiple packs with copied rule text and copied
policy effects. For example, both H30 v1 and H30 v2 stored their own version of
the specialized-tunnel rule.

## After

One registry record owns:

```text
specialized_tunnel_first
```

The H30 route memories contain:

```json
{
  "atom_id": "h30_correct_route_requires_correct_tunnel_v2",
  "inherits": ["specialized_tunnel_first"]
}
```

The selector resolves inheritance and removes repeated rule references before
the policy compiler runs.

## Multi-rule inheritance

A navigation episode may inherit:

- `navigation_exact_entity_presentation`
- `guidance_is_not_proof`
- `exact_entity_gate`
- `specialized_tunnel_first`
- `direct_source_before_fallback`

This uses one selected route memory to bring in the full relevant policy
without storing five copied lessons inside that route memory.

## Safety

Unknown references fail closed. An atom with an unresolved canonical rule is
not allowed to contribute policy.

The registry cannot execute searches, write databases, grant answer permission,
or promote guidance to proof.
