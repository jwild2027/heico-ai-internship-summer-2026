from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPT = Path("scripts/build/visual/build_trace_net_meaningful_image_route_detector_v1_2.py")


def make_table(path: Path) -> None:
    img = Image.new("L", (800, 1000), "white")
    d = ImageDraw.Draw(img)
    for y in range(120, 880, 45):
        d.line((80, y, 720, y), fill=0, width=3)
    for x in range(80, 721, 120):
        d.line((x, 120, x, 860), fill=0, width=3)
    img.save(path)


def make_diagram(path: Path) -> None:
    img = Image.new("L", (800, 1000), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((230, 260, 560, 560), outline=0, width=8)
    d.rectangle((300, 420, 680, 680), outline=0, width=7)
    d.line((180, 190, 310, 310), fill=0, width=4)
    d.line((180, 190, 155, 210), fill=0, width=4)
    d.line((180, 190, 200, 215), fill=0, width=4)
    d.text((140, 160), "1", fill=0)
    d.line((650, 300, 520, 420), fill=0, width=4)
    d.text((660, 280), "2", fill=0)
    d.arc((210, 600, 700, 900), start=200, end=340, fill=0, width=4)
    img.save(path)


def make_text(path: Path) -> None:
    img = Image.new("L", (800, 1000), "white")
    d = ImageDraw.Draw(img)
    y = 80
    for _ in range(55):
        d.rectangle((80, y, 690, y + 6), fill=0)
        y += 15
    img.save(path)


def make_blank(path: Path) -> None:
    Image.new("L", (800, 1000), "white").save(path)


def test_meaningful_image_route_detector_classifies_synthetic_pages(tmp_path: Path) -> None:
    tiffs = tmp_path / "tiffs"
    out = tmp_path / "out"
    tiffs.mkdir()

    make_diagram(tiffs / "t_p_120_1176_p000001.tif")
    make_table(tiffs / "t_p_120_1176_p000002.tif")
    make_text(tiffs / "t_p_120_1176_p000003.tif")
    make_blank(tiffs / "t_p_120_1176_p000004.tif")

    route_manifest = tmp_path / "routes.jsonl"
    route_manifest.write_text(
        "\n".join(
            [
                json.dumps({"page_id": "t_p_120_1176_p000001", "primary_route": "image_visual"}),
                json.dumps({"page_id": "t_p_120_1176_p000002", "primary_route": "image_visual"}),
                json.dumps({"page_id": "t_p_120_1176_p000003", "primary_route": "normal_text"}),
                json.dumps({"page_id": "t_p_120_1176_p000004", "primary_route": "blank_candidate"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--tiff-root",
            str(tiffs),
            "--route-manifest",
            str(route_manifest),
            "--output-dir",
            str(out),
            "--min-processed-pages",
            "4",
            "--min-output-records",
            "4",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "PASS"
    assert summary["summary"]["processed_page_count"] == 4
    assert summary["summary"]["visual_candidate_review_count"] >= 1
    assert summary["summary"]["old_image_rejected_as_table_count"] >= 1

    rows = [
        json.loads(line)
        for line in (out / "trace_net_meaningful_image_route_detector_v1_2.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_page = {row["page_id"]: row for row in rows}
    assert by_page["t_p_120_1176_p000001"]["new_route"] == "visual_candidate_review"
    assert by_page["t_p_120_1176_p000002"]["new_route"] == "table"
    assert by_page["t_p_120_1176_p000004"]["new_route"] == "blank_candidate"


def test_route_manifest_loader_accepts_jsonl(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path.cwd() / "scripts"))
    import scripts.build.visual.build_trace_net_meaningful_image_route_detector_v1_2 as m

    path = tmp_path / "routes.jsonl"
    path.write_text(
        json.dumps({"page_id": "t_p_120_1176_p000010", "primary_route": "image_visual"}) + "\n",
        encoding="utf-8",
    )
    routes = m.load_route_manifest(path, "t_p_120_1176")
    assert routes["t_p_120_1176_p000010"]["old_image_visual_candidate"] is True
