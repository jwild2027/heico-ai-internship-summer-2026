# TRACE-Net router proxy v6.1 q044 runtime-order fix

Moves the q044 loose-contains/exact-policy shim above the `if __name__ == "__main__": main()` guard.

Why: imports/tests execute the whole module, so an appended shim can pass unit tests. But when the file is launched as a server, `main()` blocks before code below the guard executes. That left the live 8017 endpoint routing q044 to `normal_ask`.

Safety contract: unchanged. This remains read-only, with no source-truth mutation, no database writes, and no final-answer permission.
