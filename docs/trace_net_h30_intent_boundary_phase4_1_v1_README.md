# TRACE-Net H30 Intent Boundary Repair — Phase 4.1

## Fixed regression 1: OCR target versus independent claim

An exact part number in a request such as:

```text
Recover OCR labels for part 120-41824-003.
```

is the target that scopes the OCR search. It is not automatically a separate
identity claim.

Correct route:

```text
ocr_scan_recovery
```

A truly separate request remains multi-claim:

```text
Find part 120-41824-003 and recover its OCR labels.
```

Correct route:

```text
multi_question_research
```

## Fixed regression 2: unresolved navigation pronouns

A request such as:

```text
Which page contains it?
```

has no entity-bearing clue in the current request. TRACE-Net now fails closed
to `clarification_no_evidence` before retrieval instead of running expensive
navigation, semantic, graph, and repair searches.

A named target such as:

```text
Which page discusses the component?
```

continues to use `document_page_navigation`.

## Safety

- no database writes;
- no source-truth mutation;
- no answer permission;
- no retrieval for unresolved pronoun-only navigation;
- no change to the 19-route registry.
