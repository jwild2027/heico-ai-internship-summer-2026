# TRACE-Net H30 Phase 4.5.1 Launcher Environment Fix

## Problem

The interactive shell accepted `TRACE_NET_H30_PLANNER_ROLLOUT_MODE` and related
Phase 4.5 settings, but the launcher generated a separate tmux startup script for
port 8118 without copying those variables. The router therefore used its defaults:
`validate_only`, phase 2, execution disabled.

## Fix

The launcher now captures and propagates seven validated-planner settings into the
8118 process. After startup it saves the health response and verifies that live
mode, phase, and execution state exactly match the requested deployment.

The launcher refuses to continue on a mismatch. It does not alter route validators,
retrieval, Self-RAG, CRAG, answer permissions, database state, ports 8017, or port
8130.
