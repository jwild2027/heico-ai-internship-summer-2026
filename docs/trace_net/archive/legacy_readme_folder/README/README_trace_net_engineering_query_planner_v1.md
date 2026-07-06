# TRACE-Net Engineering Query Planner v1

Reads the engineering reasoning kernel and turns user engineering questions into structured TRACE-Net retrieval/context plans.

It is dynamic context engineering glue:
- selects the right engineering playbook
- extracts seed entities and requested changes
- maps retrieval steps to route handoffs
- creates a context-pack blueprint
- does not call an LLM
- does not execute retrieval
- does not answer the user question
