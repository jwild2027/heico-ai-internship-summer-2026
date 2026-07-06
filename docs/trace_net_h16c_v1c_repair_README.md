# TRACE-Net H16C v1c Repair

This repair removes the bad incomplete-answer guard that v1b could insert into
`build_arg_parser()` and re-applies the guard only to the actual Ollama response
helper. It also updates the q18 question-bank filter helper so direct script
execution works without manually setting `PYTHONPATH=.`.

Safety contract: artifact/test reliability only. No Postgres writes, no Qdrant
writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer
permission.
