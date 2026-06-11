# TRACE-Net Dublin Core Crosswalk Field Map v1

| Field | Meaning |
|---|---|
| dc:identifier | Standard page/document identifier. |
| dc:type | Standard broad resource/page type. |
| dc:format | Media format, usually image/tiff for source pages. |
| dc:source | Source trace pointer for the page. |
| dc:description | Human-readable page metadata description. |
| dc:subject | Topic/type/candidate metadata useful for catalog/search. |
| dc:relation | Related citations, routes, and community IDs. |
| dcterms:isPartOf | Parent document ID. |
| dcterms:hasPart | Human-readable element-type pointers. |
| dcterms:extent | Human-readable element count summary. |
| trace_net:element_count | Machine-readable detailed element count. |
| trace_net:element_type_count | Number of detected/planned element types. |
| trace_net:element_type_counts | Per-type element counts. |
| trace_net:review_required | Whether TRACE-Net has review signals for the page. |
| trace_net:complexity_class | low, medium, high, high_review, or blank. |
| trace_net:can_answer_directly | Always false for this metadata export. |
| trace_net:can_prove_claims | Always false for this metadata export. |
| trace_net:source_truth_mutation_allowed | Always false for this metadata export. |
