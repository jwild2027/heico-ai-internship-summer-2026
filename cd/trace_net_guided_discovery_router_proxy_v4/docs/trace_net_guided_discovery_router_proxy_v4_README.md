# TRACE-Net guided discovery router proxy v4

This patch improves the 8017 router/proxy after the 50-question discovery smoke showed that clue-only ambiguous part questions were routed to normal ask instead of guided discovery.

## Fix

Routes these query shapes to guided discovery:

- part/nomenclature starts with a prefix, for example fastener starts with 244
- part number contains remembered digits, for example had 36833 in it
- partial family prefix, for example seat assembly started with 120-41824
- nomenclature plus remembered digits, for example ring locking and number had 48024 somewhere

The router remains read-only and non-mutating.
