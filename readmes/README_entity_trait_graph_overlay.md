# Entity-trait graph overlay

This patch adds a separate entity-trait overlay on top of the existing document organization graph.

It keeps the core graph clean:

```text
Document -> ATA Section -> Page -> Source / TIFF / OCR / Part / Context
```

and adds a new overlay:

```text
Entity -> HAS_TRAIT_ASSERTION -> TraitAssertion -> ASSERTS_TRAIT -> Trait
                                  |
                                  +-> DERIVED_FROM -> EvidenceSource

Entity -> HAS_TRAIT -> Trait
Entity -> INHERITS_TRAITS_FROM -> ParentEntity
```

The shortcut `HAS_TRAIT` edge makes browsing/filtering fast. The assertion node preserves why the trait exists: method, source artifact, confidence, scope, and evidence source.

## New files

```text
tiff/entity_trait_graph.py
tiff/entity_trait_graph_quality.py
scripts/export_entity_trait_graph.py
scripts/check_entity_trait_graph_quality.py
tests/unit/test_tiff_entity_trait_graph.py
tests/unit/test_tiff_entity_trait_graph_quality.py
README_entity_trait_graph_overlay.md
```

## Output files

By default, the exporter writes to:

```text
local_data/organization/entity_traits/
```

Files written:

```text
entity_traits.json
trait_graph_nodes.json
trait_graph_edges.json
page_character_cards.json
part_character_cards.json
trait_graph_summary.json
```

The quality checker can also write:

```text
entity_trait_quality.json
```

## Run

```bash
python -m pytest tests/unit/test_tiff_entity_trait_graph.py tests/unit/test_tiff_entity_trait_graph_quality.py -q
python scripts/export_entity_trait_graph.py
python scripts/check_entity_trait_graph_quality.py --write-json
```

## Current behavior

The overlay reads the existing graph artifacts:

```text
local_data/organization/graph/graph_nodes.json
local_data/organization/graph/graph_edges.json
```

It optionally reads:

```text
local_data/organization/image_recognition/page_image_recognition_audit.json
local_data/organization/page_visual_objects_audit.json
```

If those optional audits are missing, the exporter still runs. It just creates fewer image/visual traits.

## Traits currently generated

Page examples:

```text
structure:entity_kind=page
hierarchy:parent_type=document
hierarchy:parent_type=ata_section
source:has_source_link=true
source:has_tiff=true
source:has_ocr=true
ocr:ocr_state=non_empty
context:has_page_context=true
context:page_role=parts_list
context:topic=magazine_holder
image_recognition:image_class=likely_table_or_grid
visual:likely_table_or_grid=true
visual:likely_visual=true
quality:fully_traceable_page=true
quality:answer_ready_page=true
quality:high_confidence_parts_list_page=true
quality:verified_blank_page=true
```

Part examples:

```text
structure:entity_kind=part
catalog:has_nomenclature=true
catalog:appears_on_pages=true
catalog:appears_on_multiple_pages=true
quality:source_traceable_part=true
quality:high_confidence_part=true
```

Document/ATA examples:

```text
structure:entity_kind=document
structure:entity_kind=ata_section
structure:ata_code=25_21_00
structure:has_pages=true
```

## Why this graph shape

This implements the "video game character sheet" idea without creating a full mesh where every trait connects to every other trait.

Recommended model:

```text
Entity = character
Parent entity = class/faction/location
Source/TIFF/OCR = equipment/proof
Trait = status/stat/ability
TraitAssertion = why the trait exists
Derived trait = combo/buff
Page/part card = cached character sheet
```

The graph can now answer questions like:

```text
Which pages are fully traceable?
Which pages look like high-confidence parts-list pages?
Which blank pages are verified by both OCR and image signals?
Which parts have nomenclature and source-traceable evidence?
Why does the system think this page has a table/grid visual trait?
```

## Design rule

Do this:

```text
Page -> TraitAssertion -> Trait
TraitAssertion -> EvidenceSource
Page -> INHERITS_TRAITS_FROM -> ATA / Document
```

Avoid this:

```text
Every trait -> every other trait -> every cousin trait
```

The overlay keeps the evidence graph explainable and avoids runaway traversal noise.
