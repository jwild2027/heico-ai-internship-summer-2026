# TIFF API contract tests

This patch adds endpoint-level contract tests for the FastAPI boundary used by the Streamlit API-mode UI.

The contract tests validate the stable API behavior, not the local implementation details. This is the seam that should stay stable when the backend moves from local artifacts to PostgreSQL, OpenSearch, Qdrant, and real ResCarta links.

## Install patch

```bash
unzip -o ~/Downloads/heico_tiff_api_contract_tests_patch.zip -d .
python -m pytest tests/unit/test_tiff_api_contract_tests.py -q
```

## Run against a live API server

Start FastAPI:

```bash
python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000
```

Run contract tests:

```bash
python scripts/run_api_contract_tests.py --write-json
```

## Run in-process without uvicorn

```bash
python scripts/run_api_contract_tests.py --in-process --write-json
```

## Include slow LLM/RAG case

```bash
python scripts/run_api_contract_tests.py --include-slow --write-json
```

## List or run one case

```bash
python scripts/run_api_contract_tests.py --list
python scripts/run_api_contract_tests.py --case trace_vector_payload_000495 --write-json
```

Default JSON output:

```text
local_data/api/api_contract_results.json
```

Default cases cover:

- `/status`
- `/organization/summary`
- `/organization/parts/{part_number}`
- `/organization/pages/{page_id}`
- `/organization/ata/{ata_code}`
- `/trace/part/{part_number}`
- `/trace/page/{page_id}`
- `/trace/vector`
- `/ask`
- `/feedback`
- `/feedback/summary`
