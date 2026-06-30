# TRACE-Net Fast Chat Runner Image Adapter Import Path Fix v1

This focused fix patches `tiff/trace_net_fast_chat_runner_v1.py` so direct execution works with image-route adapter imports.

Problem:

```bash
python -B tiff/trace_net_fast_chat_runner_v1.py ...
```

sets Python's script path to `tiff/`, so package imports like `tiff.trace_net_image_route_fast_chat_adapter_v1` can fail even when the module exists.

Fix:

- insert the repo root into `sys.path` near the top of the runner
- preserve `from __future__` imports
- make the patch idempotent
- validate with `ast.parse`

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
