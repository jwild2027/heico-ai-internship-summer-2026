# TRACE-Net Graph Explorer v1.1 Decimal serialization fix

Fixes JSON/HTML serialization for PostgreSQL numeric fields returned as Python Decimal values.

Apply:

```bash
unzip -o ~/Downloads/heico_trace_net_graph_explorer_v1_1_decimal_fix.zip -d .
```

Then rerun:

```bash
python scripts/build_trace_net_graph_explorer.py --database-url "$TRACE_NET_DATABASE_URL" --open
```
