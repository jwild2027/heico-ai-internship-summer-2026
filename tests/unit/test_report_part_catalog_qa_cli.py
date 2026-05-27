from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "report_part_catalog_qa.py"
    spec = importlib.util.spec_from_file_location("report_part_catalog_qa_cli", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_html_is_opt_in_by_default():
    module = _load_script_module()
    args = module.build_arg_parser().parse_args([])

    assert args.write_html is False


def test_write_html_flag_is_available():
    module = _load_script_module()
    args = module.build_arg_parser().parse_args(["--write-html"])

    assert args.write_html is True


def test_summarize_by_report_counts_report_names():
    module = _load_script_module()

    class Record:
        def __init__(self, report: str):
            self.report = report

    summary = module.summarize_by_report(
        [Record("a"), Record("b"), Record("a")]
    )

    assert summary == {"a": 2, "b": 1}
