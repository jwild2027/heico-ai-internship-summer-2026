"""TRACE-Net deterministic follow-up question planner v1.

The planner uses only router atoms and fixed question templates. It does not let
an LLM invent source fields, claims, or search routes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _values(atoms: Mapping[str, Any], key: str) -> List[Any]:
    value = atoms.get(key)
    return list(value) if isinstance(value, list) else []


def _add(questions: List[str], topics: List[str], topic: str, question: str) -> None:
    if question not in questions:
        questions.append(question)
    if topic not in topics:
        topics.append(topic)


def build_follow_up_plan(
    query: str,
    atoms: Mapping[str, Any],
    selected_tunnel: str,
) -> Dict[str, Any]:
    """Return inspectable, context-aware follow-up questions."""
    questions: List[str] = []
    topics: List[str] = []

    part_numbers = _values(atoms, "part_numbers")
    manual_refs = _values(atoms, "manual_references")
    ata_sections = _values(atoms, "ata_sections")
    figures = _values(atoms, "figures")
    pages = _values(atoms, "pages")
    companies = _values(atoms, "companies")
    part_hints = _values(atoms, "part_hints")
    function_hints = _values(atoms, "function_hints")
    prefix = str(atoms.get("prefix") or "")

    if selected_tunnel == "guided_candidate_discovery":
        _add(
            questions,
            topics,
            "part_number",
            (
                f"Do you remember any characters after the prefix {prefix}, including a dash number or suffix?"
                if prefix
                else "Do you remember any part-number characters, digits, prefix, suffix, or dash number?"
            ),
        )
        if not companies:
            _add(
                questions,
                topics,
                "manufacturer",
                "Do you know the manufacturer or company, such as Honeywell, Embraer, Collins, Safran, Boeing, or Airbus?",
            )
        if not manual_refs and not ata_sections:
            _add(
                questions,
                topics,
                "ata_system",
                "Do you know the ATA chapter, system, aircraft area, or manual section where the part appeared?",
            )
        _add(
            questions,
            topics,
            "physical_description",
            "What did the part look like or do—for example hinge, bracket, latch, pin, fitting, seat component, or panel?",
        )
        _add(
            questions,
            topics,
            "source_context",
            "Was it seen in an IPL table, figure callout, drawing, page, or body text?",
        )

    elif selected_tunnel == "descriptive_part_discovery":
        if not part_numbers and not prefix:
            _add(
                questions,
                topics,
                "part_number",
                "Do you remember any possible part-number characters, prefix, suffix, digits, or dash number?",
            )
        if not companies:
            _add(
                questions,
                topics,
                "manufacturer",
                "Do you know the manufacturer or company, such as Honeywell, Embraer, Collins, Safran, Boeing, or Airbus?",
            )
        if not manual_refs and not ata_sections:
            _add(
                questions,
                topics,
                "ata_system",
                "Which ATA chapter, aircraft system, cabin area, or manual section was the part associated with?",
            )
        descriptor = str((part_hints or function_hints or [""])[0])
        _add(
            questions,
            topics,
            "physical_description",
            (
                f"Can you narrow the {descriptor} description—for example its location, material, shape, size, function, or connected assembly?"
                if descriptor
                else "Can you describe the part's location, material, shape, size, function, or connected assembly?"
            ),
        )
        _add(
            questions,
            topics,
            "source_context",
            "Was it seen in an illustrated parts list, a figure callout, a drawing, a page, or nearby text?",
        )

    elif selected_tunnel == "fast_clarification":
        _add(
            questions,
            topics,
            "search_goal",
            "Are you trying to identify a part, find a figure, locate a table entry, retrieve a procedure, or check an approval claim?",
        )
        _add(
            questions,
            topics,
            "identifiers",
            "Do you remember any part number, ATA number, figure number, page number, manufacturer, or exact wording?",
        )
        _add(
            questions,
            topics,
            "physical_description",
            "What component, assembly, physical feature, or function was involved?",
        )
        _add(
            questions,
            topics,
            "source_context",
            "Was the information in a table, figure, warning, procedure, or ordinary body text?",
        )

    elif selected_tunnel == "visual_figure_retrieval":
        if not part_numbers:
            _add(
                questions,
                topics,
                "part_number",
                "Do you know an exact or partial part number shown in the diagram?",
            )
        if not figures and not pages:
            _add(
                questions,
                topics,
                "figure_page",
                "Do you remember the figure number, sheet number, page, or any visible callout?",
            )
        _add(
            questions,
            topics,
            "assembly_context",
            "Which assembly or physical subject should the drawing show?",
        )
        if not manual_refs and not ata_sections:
            _add(
                questions,
                topics,
                "ata_system",
                "Which ATA chapter, aircraft system, or manual section should contain the visual?",
            )

    elif selected_tunnel == "table_exact_or_structured_retrieval":
        _add(
            questions,
            topics,
            "exact_text",
            "What exact row text, nomenclature, item number, column value, or phrase should TRACE-Net match?",
        )
        if not part_numbers:
            _add(
                questions,
                topics,
                "part_number",
                "Do you know a full or partial part number associated with the table entry?",
            )
        if not figures and not pages:
            _add(
                questions,
                topics,
                "table_page",
                "Do you know the table title, figure number, page, or nearby item number?",
            )
        if not manual_refs and not ata_sections:
            _add(
                questions,
                topics,
                "ata_system",
                "Which ATA chapter, manual section, or system area contains the table?",
            )

    elif selected_tunnel == "procedure_warning_text_retrieval":
        if not part_numbers:
            _add(
                questions,
                topics,
                "component_identity",
                "Which exact component, assembly, nomenclature, or part number does the task apply to?",
            )
        _add(
            questions,
            topics,
            "task_scope",
            "Are you looking for removal, installation, inspection, repair, cleaning, testing, adjustment, or reassembly steps?",
        )
        if not manual_refs and not ata_sections:
            _add(
                questions,
                topics,
                "manual_revision",
                "Which ATA chapter, manual, revision, or section should govern the procedure?",
            )
        _add(
            questions,
            topics,
            "configuration_effectivity",
            "Do you know the aircraft configuration, effectivity, seat model, or assembly variant?",
        )
        _add(
            questions,
            topics,
            "warning_context",
            "Should TRACE-Net also locate warnings, cautions, notes, tools, materials, or torque values?",
        )

    elif selected_tunnel == "safety_authority_search":
        _add(
            questions,
            topics,
            "exact_parts",
            "What exact source and replacement part numbers are being compared?",
        )
        _add(
            questions,
            topics,
            "source_authority",
            "Which approved source should establish the claim—for example the CMM, IPC/IPL, service bulletin, engineering order, or another authority?",
        )
        if not manual_refs and not ata_sections:
            _add(
                questions,
                topics,
                "manual_revision",
                "What manual number, ATA chapter, revision, and section apply?",
            )
        _add(
            questions,
            topics,
            "configuration_effectivity",
            "What aircraft, serial range, configuration, effectivity, or installation position applies?",
        )
        _add(
            questions,
            topics,
            "claim_type",
            "Is the claim about fit, interchangeability, eligibility, effectivity, approval, or installation safety?",
        )

    required = selected_tunnel in {
        "guided_candidate_discovery",
        "descriptive_part_discovery",
        "fast_clarification",
    }
    recommended = bool(questions) and not required

    return {
        "planner_version": "trace_net_follow_up_question_planner_v1",
        "query": str(query or ""),
        "selected_tunnel": selected_tunnel,
        "clarification_required": required,
        "clarification_recommended": recommended,
        "follow_up_topics": topics,
        "clarifying_questions": questions[:5],
        "question_count": min(5, len(questions)),
        "llm_question_invention_allowed": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    }
