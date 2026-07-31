# TRACE-Net Visual Lab v1

TRACE-Net Visual Lab turns completed demonstration artifacts into nine separate browser explorers served by one local HTTP server.

## Explorers

1. Source lineage
2. OCR
3. Page classification
4. Graph
5. Vector space
6. Engram memory
7. Storage eligibility
8. Retrieval trace
9. Answer validation

The Visual Lab is presentation-only. It never writes to Postgres, Qdrant, OpenSearch, source TIFFs, or source-truth artifacts.

## Architecture

```text
completed TRACE-Net run directory
        |
        v
build_trace_net_visual_lab_v1.py
        |
        +-- normalized browser-safe JSON
        +-- two-dimensional PCA embedding projection
        +-- optional PNG viewing thumbnails
        +-- catalog entry
        |
        v
local_data/organization/trace_net/visual_lab
        |
        v
python -m http.server 8765
```

The vector explorer uses L2-normalized, mean-centered PCA for display. The original BGE-M3 vectors remain unchanged and are not copied into browser JSON.

## Laptop tests

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026

python -B -m pytest -q \
  tests/unit/test_build_trace_net_visual_lab_v1.py

node --check \
  local_data/organization/trace_net/visual_lab/assets/trace_net_visual_lab.js

python -B -m py_compile \
  scripts/build_trace_net_visual_lab_v1.py
```

Expected:

```text
5 passed
```

## Export the full 509-page dataset on Ubuntu

Run from the server repository after pulling the patch:

```bash
cd /data/trace_net/repos/heico-ai-internship-summer-2026

source /home/jwild/rag-workspace/.venv/bin/activate
export PYTHONPATH="$PWD/scripts:$PWD"

python -B scripts/build_trace_net_visual_lab_v1.py \
  --run-dir /data/trace_net_runs/executive_deep_demo_v4_20260731_130923 \
  --visual-lab-dir local_data/organization/trace_net/visual_lab \
  --dataset-slug full_509 \
  --dataset-label "Full 509-page run" \
  --require-page-count 509 \
  --copy-thumbnails \
  --replace-dataset \
  --quality
```

Required ending:

```text
status=TRACE_NET_VISUAL_LAB_DATASET_BUILT
quality_status=PASS
dataset_slug=full_509
page_count=509
production_write_attempt_count=0
failure_count=0
```

## Export the mini 10-page dataset on Ubuntu

Use the exact completed mini-run directory. For the run shown in the demonstration log:

```bash
cd /data/trace_net/repos/heico-ai-internship-summer-2026

source /home/jwild/rag-workspace/.venv/bin/activate
export PYTHONPATH="$PWD/scripts:$PWD"

python -B scripts/build_trace_net_visual_lab_v1.py \
  --run-dir /data/trace_net_runs/executive_fast10_deep_v5_20260731_134625 \
  --visual-lab-dir local_data/organization/trace_net/visual_lab \
  --dataset-slug mini_10 \
  --dataset-label "Mini 10-page run" \
  --require-page-count 10 \
  --copy-thumbnails \
  --replace-dataset \
  --quality
```

Required ending:

```text
status=TRACE_NET_VISUAL_LAB_DATASET_BUILT
quality_status=PASS
dataset_slug=mini_10
page_count=10
production_write_attempt_count=0
failure_count=0
```

## Inspect generated data

```bash
find local_data/organization/trace_net/visual_lab/data \
  -maxdepth 3 \
  -type f \
  -printf '%p | %s bytes\n' \
  | sort

python -B - <<'PY'
from pathlib import Path
import json

root = Path("local_data/organization/trace_net/visual_lab/data")
catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))

print("dataset_count=", len(catalog.get("datasets") or []))
for dataset in catalog.get("datasets") or []:
    manifest = json.loads(
        (root.parent / dataset["manifest"]).read_text(encoding="utf-8")
    )
    print()
    print("slug=", manifest.get("dataset_slug"))
    print("quality_status=", manifest.get("quality_status"))
    print("page_count=", manifest.get("page_count"))
    print("graph_node_count=", manifest.get("graph_node_count"))
    print("graph_edge_count=", manifest.get("graph_edge_count"))
    print("embedding_point_count=", manifest.get("embedding_point_count"))
    print("engram_layer_count=", manifest.get("engram_layer_count"))
    print("question_count=", manifest.get("question_count"))
    print("production_write_attempt_count=", manifest.get("production_write_attempt_count"))
PY
```

## Move exported presentation data back to the laptop

The generated `visual_lab/data/` files live in the server Git checkout. Review their size before committing.

```bash
git status --short
git diff --stat

git add \
  local_data/organization/trace_net/visual_lab/data

git diff --cached --check
git diff --cached --stat

git commit -m "Add TRACE-Net Visual Lab datasets"
git push origin srv
```

Then on the Windows laptop:

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026

git pull --ff-only origin srv
```

## Host the Visual Lab on Windows

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026/local_data/organization/trace_net/visual_lab

python -m http.server 8765
```

Open:

```text
http://localhost:8765/
```

Direct pages:

```text
http://localhost:8765/01_source_lineage_explorer.html
http://localhost:8765/02_ocr_explorer.html
http://localhost:8765/03_page_classifier_explorer.html
http://localhost:8765/04_graph_explorer.html
http://localhost:8765/05_vector_explorer.html
http://localhost:8765/06_engram_explorer.html
http://localhost:8765/07_storage_explorer.html
http://localhost:8765/08_retrieval_trace_explorer.html
http://localhost:8765/09_answer_validation_explorer.html
```

Use the dataset selector in the top-right corner to switch between `full_509` and `mini_10`.

## Generated dataset files

Each dataset has this stable shape:

```text
data/<dataset>/manifest.json
data/<dataset>/source_lineage.json
data/<dataset>/ocr_pages.json
data/<dataset>/classification.json
data/<dataset>/graph_nodes.json
data/<dataset>/graph_edges.json
data/<dataset>/vector_projection.json
data/<dataset>/engram_layers.json
data/<dataset>/storage_plan.json
data/<dataset>/question_traces.json
data/<dataset>/quality_summary.json
data/<dataset>/thumbnails/*.png        # optional
```

## Safety contract

- Source artifacts are read-only.
- No production database connector is imported or called.
- No Postgres, Qdrant, or OpenSearch write is attempted.
- TIFF files are never modified.
- PNG thumbnails are display-only derivatives.
- The vector scatterplot is a PCA projection, not a replacement for the original embeddings.
- Graph-only safety holds remain visible in graph and classification views but are not marked vector eligible.
- Browser JSON is presentation data, not source truth.
