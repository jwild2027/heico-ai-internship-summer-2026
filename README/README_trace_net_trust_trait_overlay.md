# TRACE-Net trust trait overlay

This patch starts the trust-tier portion of TRACE-Net.

It reads cleaned visual-text records from:

```text
local_data/organization/visual_text/visual_text_extraction_clean.jsonl
```

and exports graph traits under:

```text
local_data/organization/trust_traits/
```

The graph pattern is:

```text
Page -> HAS_VISUAL_TEXT -> VisualTextContext
VisualTextContext -> HAS_TRAIT_ASSERTION -> TraitAssertion -> ASSERTS_TRAIT -> Trait
TraitAssertion -> DERIVED_FROM -> EvidenceSource
```

Trust is attached to the evidence layer first, for example:

```text
visual_text:t_p_120_1176_p000020
  -> trait:trust:visual_text:C
```

Then page-level derived traits are added for fast traversal:

```text
page:t_p_120_1176_p000020
  -> trait:rag:visual_text:exclude_visual_text
page:t_p_120_1176_p000020
  -> trait:review:visual_text:needs_human_review
```

This avoids saying the whole page is low-trust when only the visual-text layer is low-trust.

## Run

```bash
python scripts/export_trust_trait_overlay.py --expect-records 25
```

Then quality:

```bash
python scripts/check_trust_trait_overlay_quality.py \
  --write-json \
  --min-records 25 \
  --expect-pages 25
```

If you want to block D-tier visual text records from the trust overlay quality gate:

```bash
python scripts/check_trust_trait_overlay_quality.py \
  --write-json \
  --min-records 25 \
  --expect-pages 25 \
  --max-trust-d-records 0
```

## Files written

```text
local_data/organization/trust_traits/trust_trait_assertions.jsonl
local_data/organization/trust_traits/trust_trait_graph_nodes.json
local_data/organization/trust_traits/trust_trait_graph_edges.json
local_data/organization/trust_traits/trust_trait_summary.json
local_data/organization/trust_traits/trust_trait_review.md
local_data/organization/trust_traits/trust_trait_quality.json
```

## Trait examples

```text
trait:trust:visual_text:A
trait:trust:visual_text:B
trait:trust:visual_text:C
trait:trust:visual_text:D
trait:rag:visual_text:include_visual_text
trait:rag:visual_text:exclude_visual_text
trait:review:visual_text:needs_human_review
trait:review:visual_text:hallucination_risk
trait:review:visual_text:table_expected_but_not_extracted
trait:review:visual_text:prompt_template_leakage
trait:review:visual_text:section_bleed
```
