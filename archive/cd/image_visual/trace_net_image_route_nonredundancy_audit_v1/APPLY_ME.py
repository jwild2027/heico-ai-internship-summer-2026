from pathlib import Path
import shutil
src=Path(__file__).resolve().parent; root=src.parent
for rel in ["scripts/maintenance/visual/audit_trace_net_image_route_nonredundancy_v1.py","tests/unit/test_trace_net_image_route_nonredundancy_audit_v1.py","docs/trace_net_image_route_nonredundancy_audit_v1_README.md"]:
 d=root/rel; d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src/rel,d); print(f"installed={d}")
print("status=TRACE_NET_IMAGE_ROUTE_NONREDUNDANCY_AUDIT_V1_APPLIED")
