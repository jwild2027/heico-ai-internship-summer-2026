# TRACE-Net v2 summary guidance index strict filter v1

This patch tightens `trace_net_v2_summary_guidance_index_v1` so the guidance index is safe for the engineering query planner.

It rejects path-like `summary_path` values, feedback/community summaries, page-id-only values, and duplicate copied page summaries. The index remains guidance-only and does not grant answer permission.
