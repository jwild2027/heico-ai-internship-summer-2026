#!/usr/bin/env bash
set -euo pipefail

# Phase 20 now uses the no-rebuild blue-green candidate gate. Production remains
# live while the inactive color runs mixed12 and Gemma100 acceptance tests.
REPO="${TRACE_NET_REPO:-$(pwd)}"
cd "$REPO"
exec bash scripts/benchmark/graph/run_trace_net_nha_blue_green_final_gate_v1.sh
