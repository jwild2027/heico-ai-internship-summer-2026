# TRACE-Net Route Dispatch Contract Loader v1

Small read-only helper for downstream processors that need to obey `trace_net_route_dispatch_processor_contract_v1`.

## Purpose

Downstream modules should not reimplement route logic. They should load the processor contract and ask simple route questions:

```python
from tiff.trace_net_route_dispatch_contract_loader_v1 import load_route_dispatch_processor_contract

contract = load_route_dispatch_processor_contract(
    "local_data/organization/trace_net/route_dispatch_processor_contract/trace_net_route_dispatch_processor_contract_v1.json"
)

if contract.is_table_allowed("t_p_120_1176_p000005"):
    ...

if contract.is_image_visual_allowed("metadata_page_000005"):
    ...

if contract.is_review_required(5):
    ...
```

## Supported aliases

A page can be addressed by:

- `page_id`, for example `t_p_120_1176_p000005`
- `source_page_id`, for example `metadata_page_000005`
- page number, for example `5`

## Safety

This loader is read-only. It does not grant answer permission, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch.

## Test

```bash
PYTHONPATH=. python -m pytest tests/unit/test_trace_net_route_dispatch_contract_loader_v1.py -q
```
