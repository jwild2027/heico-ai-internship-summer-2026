# TRACE-Net q044 v6.1 test-loader hotfix

This hotfix changes only the q044 regression test loader.

## Why

On Python 3.14, `@dataclass` may inspect `sys.modules[cls.__module__]` while the module is being dynamically imported. The original q044 test used `importlib.util.module_from_spec()` and then called `exec_module()` without first registering the module in `sys.modules`, causing:

```text
AttributeError: 'NoneType' object has no attribute '__dict__'
```

## Fix

The test now does:

```python
sys.modules[module_name] = module
spec.loader.exec_module(module)
```

before loading the router file.

## Scope

No router behavior, launcher behavior, source artifacts, stores, endpoints, or safety gates are changed.
