# TRACE-Net image route endpoint direct smoke hardening v1

This patch hardens the image-route OpenWebUI endpoint smoke layer by using the same image-route adapter and image-route quality gate directly. It avoids a fragile subprocess/report-discovery path for endpoint smoke/runtime calls while preserving the safety contract: no database/vector/search writes, no source-truth mutation, and no answer permission.
