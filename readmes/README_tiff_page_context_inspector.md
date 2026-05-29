# TIFF page-context inspection

This patch adds a read-only inspector for AI-generated page context records.

It validates:

- the number of generated page contexts
- role counts such as `parts_list`, `procedure`, `front_matter`, `blank`
- confidence counts
- warning/error counts
- topic counts
- highlighted part counts
- graph linkage counts for `page_context`, `HAS_CONTEXT`, `TAGGED_AS`, and `HIGHLIGHTS_PART`

Run:

```bash
python scripts/inspect_page_contexts.py --strict --write-json
```

Filter examples:

```bash
python scripts/inspect_page_contexts.py --role parts_list --limit 20
python scripts/inspect_page_contexts.py --topic repair --limit 20
python scripts/inspect_page_contexts.py --page t_p_120_1176_p000042 --limit 5
```

This does not call Gemma, edit the database, or rebuild the graph. It only reads:

```text
local_data/organization/context/page_contexts.json
local_data/organization/graph/graph_summary.json
```
