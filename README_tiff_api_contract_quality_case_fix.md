# API contract quality case-name compatibility fix

This patch makes `check_api_contract_quality.py` read the actual case names emitted by
`run_api_contract_tests.py --in-process`, including `status_endpoint`,
`part_lookup_120_37313_001`, `trace_vector_payload_000495`, `ask_exact_part_120_37313_001`,
and feedback round-trip/summary checks.
