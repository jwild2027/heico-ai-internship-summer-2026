# TRACE-Net router proxy v6.1 q044 runtime-order fix

This patch moves the q044 loose-contains/exact-policy shim above the `if __name__ == "__main__": main()` guard. The previous placement allowed import-based unit tests to pass while the live server still ran the old route, because the process entered blocking `main()` before executing the shim.

Safety contract is unchanged: read-only, no source-truth mutation, no database writes, and no final-answer permission.

Validation target: the q044 direct curl should return `route=guided_discovery`, `fast_clarification_only=true`, and at least three assistant questions before the full 50-question benchmark is rerun.
