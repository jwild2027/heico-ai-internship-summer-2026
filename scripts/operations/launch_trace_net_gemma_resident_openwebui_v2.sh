#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "launcher_redirect=launch_trace_net_gemma_resident_openwebui_v2_1.sh"
exec "$SCRIPT_DIR/launch_trace_net_gemma_resident_openwebui_v2_1.sh" "$@"
