from __future__ import annotations

import http.client
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import scripts.operations.serving.serve_trace_net_guided_candidate_discovery_endpoint_v1 as endpoint


def write_fake_artifacts(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ocr_source.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "page_id": "t_p_120_1176_p000491",
                        "text": "part_number: 244CS-3-2 nomenclature: AR - FASTENER ATA 25-21-00 EMB CMM ATA 25-21-00 REV.4",
                    }
                ),
                json.dumps(
                    {
                        "page_id": "t_p_120_1176_p000055",
                        "text": "part_number: 120-48024-001 nomenclature: RING, LOCKING ATA 25-21-00 EMB CMM ATA 25-21-00 REV.4",
                    }
                ),
                json.dumps(
                    {
                        "page_id": "t_p_120_1176_p000024",
                        "text": "filename 00000024.tif should not become a candidate part number",
                    }
                ),
                json.dumps(
                    {
                        "page_id": "t_p_120_1176_p000180",
                        "text": "artifact id 248c-5c38-8683 should be rejected as uuid/hash-like noise",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )


def test_discover_once_returns_strict_and_loose_candidates(tmp_path: Path) -> None:
    artifact_root = tmp_path / "trace_net"
    write_fake_artifacts(artifact_root)
    response = endpoint.discover_once(
        artifact_root=artifact_root,
        output_dir=tmp_path / "out",
        question="I am looking for a part that starts with numbers 2 and 4 but I do not have the rest",
        top_k=8,
        loose_top_k=8,
        max_files=100,
    )
    assert response["quality_status"] == "PASS"
    assert response["final_answer_allowed"] is False
    strict_parts = [r["candidate_part_number"] for r in response["strict_prefix_candidates"]]
    loose_parts = [r["candidate_part_number"] for r in response["loose_candidates"]]
    assert "244CS-3-2" in strict_parts
    assert "120-48024-001" in loose_parts
    all_parts = strict_parts + loose_parts
    assert "00000024.tif" not in all_parts
    assert "248c-5c38-8683" not in all_parts
    assert response["output_paths"]["response"]
    assert response["output_paths"]["view"]


def test_health_reports_runner_and_safety(tmp_path: Path) -> None:
    artifact_root = tmp_path / "trace_net"
    write_fake_artifacts(artifact_root)
    config = endpoint.EndpointConfig(artifact_root=artifact_root, output_dir=tmp_path / "out")
    health = endpoint.build_health(config)
    assert health["quality_status"] == "PASS"
    assert health["runner"] == "guided_candidate_discovery_v4"
    assert health["final_answer_allowed"] is False
    assert health["safety_contract"]["postgres_write_attempt_count"] == 0


def test_http_post_endpoint(tmp_path: Path) -> None:
    artifact_root = tmp_path / "trace_net"
    write_fake_artifacts(artifact_root)
    config = endpoint.EndpointConfig(artifact_root=artifact_root, output_dir=tmp_path / "out", max_files=100)
    server = endpoint.build_server("127.0.0.1", 0, config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        payload = json.dumps(
            {
                "question": "I am looking for a part that starts with numbers 2 and 4 but I do not have the rest",
                "top_k": 8,
                "loose_top_k": 8,
                "include_view": False,
                "max_files": 100,
            }
        )
        conn.request("POST", "/api/trace-net/guided-discovery", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert body["quality_status"] == "PASS"
        assert body["source_trace_status"] == "candidate-discovery-only"
        assert body["final_answer_allowed"] is False
        assert "view_text" not in body
        assert body["strict_prefix_candidate_count"] >= 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_rejects_missing_question(tmp_path: Path) -> None:
    artifact_root = tmp_path / "trace_net"
    write_fake_artifacts(artifact_root)
    config = endpoint.EndpointConfig(artifact_root=artifact_root, output_dir=None, max_files=100)
    server = endpoint.build_server("127.0.0.1", 0, config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        conn.request("POST", "/api/trace-net/guided-discovery", body=json.dumps({}), headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 500
        assert body["quality_status"] == "FAIL"
        assert body["final_answer_allowed"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
