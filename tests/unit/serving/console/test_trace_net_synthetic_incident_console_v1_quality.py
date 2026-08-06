import random

from tiff.trace_net_synthetic_incident_console_v1 import make_random_synthetic_incident, make_synthetic_incident, quality_report, summarize_incidents


def test_quality_passes_for_safe_incidents() -> None:
    incidents = [make_synthetic_incident("answer_gate"), make_synthetic_incident("visual_diagram")]
    summary = summarize_incidents(incidents)
    q = quality_report({"summary": summary}, min_incidents=2)
    assert q["status"] == "PASS"
    assert q["source_truth_mutation_allowed_count"] == 0
    assert q["raw_feedback_direct_to_llm_count"] == 0


def test_quality_fails_when_min_incidents_not_met() -> None:
    q = quality_report({"summary": summarize_incidents([])}, min_incidents=1)
    assert q["status"] == "FAIL"
    assert q["checks"]["incident_count_min"] is False


def test_quality_fails_for_unsafe_incident() -> None:
    incident = make_synthetic_incident("source_ingest")
    incident["can_mutate_source_truth"] = True
    incident["source_truth_mutation_allowed"] = True
    summary = summarize_incidents([incident])
    q = quality_report({"summary": summary})
    assert q["status"] == "FAIL"
    assert q["source_truth_mutation_allowed_count"] == 1


def test_quality_counts_random_incidents() -> None:
    incidents = [make_random_synthetic_incident(random.Random(3))]
    summary = summarize_incidents(incidents)
    q = quality_report({"summary": summary}, min_incidents=1)
    assert q["status"] == "PASS"
    assert summary["randomly_generated_incident_count"] == 1
    assert summary["random_template_count"] == 1
