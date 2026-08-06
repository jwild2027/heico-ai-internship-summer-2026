from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.trace_net.ingestion.batch_scan_tiffs_to_json import (
    iter_tiff_files_from_list,
    scan_folder_to_json,
)


def make_tiff(path: Path, size: tuple[int, int] = (16, 12)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("1", size, 1).save(path, format="TIFF")


def test_iter_tiff_files_from_list_resolves_relative_paths_and_ignores_comments(tmp_path: Path) -> None:
    root = tmp_path / "sample_tiffs"
    make_tiff(root / "a.tif")
    make_tiff(root / "nested" / "b.tiff")
    (root / "ignore.txt").write_text("not a tiff", encoding="utf-8")

    input_list = tmp_path / "changed.txt"
    input_list.write_text(
        "\n".join(
            [
                "# comment",
                "a.tif",
                "nested/b.tiff",
                "ignore.txt",
                "a.tif",  # duplicate should be ignored
                "",
            ]
        ),
        encoding="utf-8",
    )

    files = iter_tiff_files_from_list(input_list, input_dir=root)
    assert [p.name for p in files] == ["a.tif", "b.tiff"]


def test_scan_folder_to_json_with_empty_input_list_scans_zero_files(tmp_path: Path) -> None:
    root = tmp_path / "sample_tiffs"
    root.mkdir()
    out = tmp_path / "json_scans"
    input_list = tmp_path / "changed_tiffs.txt"
    input_list.write_text("", encoding="utf-8")

    result = scan_folder_to_json(
        input_dir=root,
        input_list=input_list,
        output_dir=out,
        db_path=None,
        run_ocr=False,
        summary_output=tmp_path / "summary.json",
    )

    assert result.total_discovered == 0
    assert result.total_attempted == 0
    assert result.total_succeeded == 0
    assert (tmp_path / "summary.json").exists()


def test_scan_folder_to_json_with_input_list_scans_only_listed_tiffs(tmp_path: Path) -> None:
    root = tmp_path / "sample_tiffs"
    make_tiff(root / "scan_me.tif")
    make_tiff(root / "skip_me.tif")

    out = tmp_path / "json_scans"
    input_list = tmp_path / "changed_tiffs.txt"
    input_list.write_text("scan_me.tif\n", encoding="utf-8")

    result = scan_folder_to_json(
        input_dir=root,
        input_list=input_list,
        output_dir=out,
        db_path=None,
        run_ocr=False,
        summary_output=tmp_path / "summary.json",
    )

    assert result.total_discovered == 1
    assert result.total_attempted == 1
    assert result.total_succeeded == 1
    assert (out / "scan_me.tif.scan.json").exists()
    assert not (out / "skip_me.tif.scan.json").exists()
