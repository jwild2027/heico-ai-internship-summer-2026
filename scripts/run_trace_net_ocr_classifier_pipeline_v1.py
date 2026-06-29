from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_ocr_classifier_pipeline_runner_v1 import build_pipeline_runner


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run TRACE-Net OCR/classifier dry-run pipeline in one command.")
    parser.add_argument("--source-package", required=True)
    parser.add_argument("--tesseract-cmd", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--route-label-taxonomy",
        default="local_data/organization/trace_net/route_label_taxonomy/trace_net_route_label_taxonomy_v1.json",
    )
    parser.add_argument("--psm-modes", default="3,6,11")
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    build_pipeline_runner(
        source_package=args.source_package,
        output_dir=args.output_dir,
        tesseract_cmd=args.tesseract_cmd,
        route_label_taxonomy=args.route_label_taxonomy,
        psm_modes=args.psm_modes,
        request_timeout=args.request_timeout,
        python_executable=args.python_executable,
        quality=args.quality,
    )


if __name__ == "__main__":
    main()
