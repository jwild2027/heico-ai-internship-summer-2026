#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-promote}"
REPO="${TRACE_NET_REPO:-$(pwd)}"
cd "$REPO"

case "$MODE" in
  promote)
    export TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED=1
    export TRACE_NET_H30_PHASE19_EXACT_IDENTIFIER_MAX_CALLS="${TRACE_NET_H30_PHASE19_EXACT_IDENTIFIER_MAX_CALLS:-2}"
    export TRACE_NET_H30_PHASE19_EXACT_TABLE_MAX_CALLS="${TRACE_NET_H30_PHASE19_EXACT_TABLE_MAX_CALLS:-2}"
    export TRACE_NET_H30_PHASE19_ATA_MAX_CALLS="${TRACE_NET_H30_PHASE19_ATA_MAX_CALLS:-2}"
    export TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED=1
    export TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS="${TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS:-384}"
    echo "TRACE_NET_NHA_PHASE19_STACK_PROMOTION=START"
    bash scripts/launch_trace_net_cognitive_openwebui_v1.sh
    bash scripts/launch_trace_net_cognitive_openwebui_nha_unified_v1.sh promote
    echo "TRACE_NET_NHA_PHASE19_STACK_PROMOTION=PASS"
    ;;
  rollback)
    export TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED=0
    export TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED=0
    echo "TRACE_NET_NHA_PHASE19_STACK_ROLLBACK=START"
    bash scripts/launch_trace_net_cognitive_openwebui_v1.sh
    bash scripts/launch_trace_net_cognitive_openwebui_nha_unified_v1.sh promote
    echo "TRACE_NET_NHA_PHASE19_STACK_ROLLBACK=PASS"
    ;;
  *)
    echo "usage: $0 [promote|rollback]" >&2
    exit 2
    ;;
esac
