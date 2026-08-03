# TRACE-Net NHA Phase N4 Hierarchy v1

This offline, read-only phase consumes the N0-N3 pilot artifacts and resolves a
conservative IPL hierarchy view.

## What N4 adds

- closes sticky OCR `ATTACHING PARTS` regions when a substantive component begins;
- groups contiguous same-nomenclature component variants;
- distinguishes direct children (`hierarchy_depth=1`) from attaching/lower parts
  (`hierarchy_depth=2`);
- preserves ambiguous top-assembly and immediate-parent variant sets;
- emits a real-source answer key and a read-only graph bundle;
- never loads or mutates a production graph.

## Safety rules

Only narrow hardware nouns (bolt, nut, screw, washer, pin, fitting, rivet, clip,
fastener, and similar conventional hardware) are eligible for attaching-part
resolution. `SUPPORT, ATTACH`, structures, seats, protectors, plates, armrests,
and other substantive components close the sticky attaching region and remain
figure-level direct components.

A supported attaching relationship points to its immediate component, never to
the top assembly. A separate `LOWER_DESCENDANT_OF` edge may describe the derived
two-hop relationship and is explicitly marked non-direct.

Multi-variant parents remain ambiguous until a later usage/effectivity phase.
