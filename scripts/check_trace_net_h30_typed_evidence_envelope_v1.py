#!/usr/bin/env python3
"""Check the Phase 4 typed evidence contract with deterministic sample data."""
from __future__ import annotations

import json

from scripts.trace_net_h30_typed_evidence_envelope_v1 import (
    build_typed_evidence_view,
)


def main() -> int:
    envelope = {
        "route": "guided_part_discovery",
        "direct_evidence": [
            {
                "page_id": "t_p_demo_p000001",
                "document": "DEMO CMM ATA 25-21-00",
                "field_name": "part_number",
                "normalized_value": "120-41824-003",
                "citation_ready": True,
                "source_trace_ready": True,
                "direct_proof_authority": True,
                "source_truth": True,
            },
            {
                "page_id": "",
                "field_name": "ocr_text",
                "value": "unresolved OCR text",
                "citation_ready": False,
                "source_trace_ready": False,
            },
        ],
        "candidate_evidence": [
            {
                "candidate_value": "120-41824-007",
                "page_id": "t_p_demo_p000002",
                "guidance_only": True,
                "source_truth": False,
            }
        ],
        "visual_guidance": [
            {
                "page_id": "t_p_demo_p000003",
                "part_numbers": ["120-41824-003"],
                "figure_refs": ["2"],
                "guidance_only": True,
                "source_truth": False,
            }
        ],
        "semantic_guidance": [
            {
                "point_id": "qdrant-1",
                "candidate_type": "v3_page_intelligence",
                "page_id": "t_p_demo_p000004",
                "guidance_only": True,
                "source_truth": False,
            },
            {
                "point_id": "graph-1",
                "candidate_type": "leiden_graph_relationship",
                "page_id": "t_p_demo_p000005",
                "guidance_only": True,
                "source_truth": False,
            },
        ],
        "contradictions": [
            {
                "type": "ata_document_mismatch",
                "candidate": "120-41824-297",
                "candidate_ata": "25-21-00",
                "document_ata": "25-22-00",
            }
        ],
        "source_resolution": [
            {
                "candidate_value": "120-41824-003",
                "resolution_status": "candidate_source_resolution_attempted",
            }
        ],
        "authority_evidence": [],
    }
    typed = build_typed_evidence_view(envelope)
    records = typed["records"]
    unsafe = [
        row for row in records
        if row.get("guidance_only")
        and row.get("claim_support_allowed")
    ]
    support = [
        row for row in records
        if row.get("claim_support_allowed")
    ]
    modalities = set(typed["coverage"]["modality_counts"])
    required_modalities = {
        "textual_source",
        "ocr",
        "visual",
        "summary",
        "graph",
        "conflict",
        "source_resolution",
    }
    quality = (
        "PASS"
        if typed["quality_status"] == "PASS"
        and len(records) == 8
        and len(support) == 1
        and not unsafe
        and required_modalities.issubset(modalities)
        else "FAIL"
    )
    output = {
        "quality_status": quality,
        "schema_version": typed["schema_version"],
        "typed_record_count": len(records),
        "claim_support_allowed_count": len(support),
        "guidance_support_violation_count": len(unsafe),
        "modality_counts": typed["coverage"]["modality_counts"],
        "validation": typed["validation"],
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }
    print(json.dumps(output, indent=2))
    return 0 if quality == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
