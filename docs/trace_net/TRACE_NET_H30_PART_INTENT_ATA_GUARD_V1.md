# TRACE-Net H30 Part Intent ATA Guard v1

This focused Phase 4.3 fix prevents ATA chapter and ATA code clues from being
reclassified as part-number prefixes, contains fragments, suffixes, families, or
exact identifiers.

Examples preserved:

- `ATA number starts with 25` remains ATA-system discovery.
- `Find ATA 25-21-00` remains ATA-system discovery.
- `In ATA 25, the P/N starts with MS49` preserves the real `MS49` part prefix.

The fix is read-only and does not change routes, retrieval tunnels, databases,
source truth, authority requirements, or answer permission.
