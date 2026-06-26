# TRACE-Net Fishnet Route Dispatch Handoff v1

Quality status: **PASS**

## Summary

- Dispatch records: 509
- Normal text: 15
- Blank candidates: 461
- Tables: 21
- Image/visual: 12
- Changed route handoffs: 14
- Processor execution allowed: 0

## Route handoffs

### normal_text

- Count: `15`
- Processor family: `normal_text_page_context_route`
- Primary contract: `page_context_v2_and_text_retrieval_helpers`
- Dispatch status: `ready_for_normal_text_route`

### blank_candidate

- Count: `461`
- Processor family: `blank_confirmation_route`
- Primary contract: `blank_source_trace_confirmation_and_review_queue`
- Dispatch status: `ready_for_blank_confirmation_route`

### table

- Count: `21`
- Processor family: `table_extraction_route`
- Primary contract: `table_line_geometry_and_table_value_extraction`
- Dispatch status: `ready_for_table_route`

### image_visual

- Count: `12`
- Processor family: `image_visual_observer_route`
- Primary contract: `visual_observer_callout_and_diagram_route`
- Dispatch status: `ready_for_image_visual_route`
