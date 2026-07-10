# TRACE-Net q044 runtime test path hotfix

This is a test-only cleanup for the q044 runtime-order regression test. The previous test referenced `ROUTER_PATH` but did not define it in some test-file versions. This patch defines `ROUTER_PATH` at module scope and uses it for dynamic router imports.

Router behavior, endpoint behavior, launcher behavior, and the read-only safety contract are unchanged.
