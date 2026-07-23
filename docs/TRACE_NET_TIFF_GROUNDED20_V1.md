# TRACE-Net TIFF-grounded 20-question benchmark

This runner builds 20 questions dynamically from the canonical graph and the V3 page-intelligence artifact derived from the 509 TIFF pages. It saves a grounded question bank, one raw response per question, a CSV, a JSON summary, and a Markdown report.

The first run is diagnostic. It explicitly counts `unknown_citation_id` instead of stopping the run.
