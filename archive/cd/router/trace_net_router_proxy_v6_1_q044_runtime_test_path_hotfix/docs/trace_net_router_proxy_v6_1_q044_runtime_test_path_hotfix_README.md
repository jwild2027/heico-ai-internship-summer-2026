# TRACE-Net q044 runtime test path hotfix

This patch fixes a test-only NameError in `test_q044_runtime_shim_is_defined_before_main_guard`.

## Bug

The runtime-order regression test referenced `ROUTER_PATH`, but the q044 test file did not define it at module scope.

## Fix

Define:

```python
ROUTER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "serve_trace_net_guided_discovery_router_proxy_v6.py"
```

and reuse that path in the dynamic import loader.

## Scope

No router behavior, endpoint behavior, launcher behavior, generated artifacts, database writes, or safety gates are changed.
