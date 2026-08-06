# TRACE-Net repository stage inventory v2

This is a read-only dependency-aware scanner. It does not move, rename, delete,
edit, stage, or commit repository files.

## Clean the v1 scanner leftovers

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026

rm -f trace_net_repo_stage_inventory_v1.py
rm -rf trace_net_repo_stage_inventory_v1
```

## Run v2 from Windows Git Bash

```bash
unzip -o \
  /c/Users/juswil/Downloads/trace_net_repo_stage_inventory_v2.zip \
  -d .

cp \
  trace_net_repo_stage_inventory_v2/trace_net_repo_stage_inventory_v2.py \
  .

python -B trace_net_repo_stage_inventory_v2.py \
  --repo . \
  --output-dir repo_stage_inventory_v2 \
  --package
```

The scanner prints progress every 250–500 files.

Expected ending:

```text
TRACE_NET_REPO_STAGE_INVENTORY_V2=PASS
```

Generated reports:

- `repo_stage_inventory_v2/repo_stage_map.csv`
- `repo_stage_inventory_v2/repo_stage_inventory.json`
- `repo_stage_inventory_v2/repo_dependency_graph.json`
- `repo_stage_inventory_v2/repo_active_entrypoints.json`
- `repo_stage_inventory_v2/repo_legacy_candidates.json`
- `repo_stage_inventory_v2/repo_unresolved_files.json`
- `repo_stage_inventory_v2/repo_move_manifest_draft.json`
- `repo_stage_inventory_v2/repo_version_families.json`
- `repo_stage_inventory_v2/repo_organization_report.md`
- `repo_stage_inventory_v2.zip`

Upload `repo_stage_inventory_v2.zip` back to ChatGPT for the reviewed final
file-by-file move plan.
