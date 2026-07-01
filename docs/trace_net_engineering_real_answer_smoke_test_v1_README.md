# TRACE-Net Engineering Real Answer Smoke Test v1

H11 runs the engineering answer runner over a 30-question real-answer smoke set.
It is an evaluation harness only: it does not change retrieval, evidence, LLaVA,
endpoint/OpenWebUI, answer-composer logic, or source-truth artifacts.

## What it measures

The harness grades each answer as:

- `GOOD`: runner passed, source-trace-ready evidence is present, and the answer shape matches the question intent.
- `PARTIAL`: runner passed but the answer needs human review or intent coverage is weak.
- `BAD`: unsupported claims, invalid citations, summary-as-proof, unsafe record, or other hard violation.
- `BLOCKED`: the runner could not produce a passing answer.

## Default 30-question bank

1. What does figure 69 show?
2. What does figure 75 show?
3. What does figure 91 show?
4. Compare figure 69 and figure 75.
5. Compare figure 75 and figure 91.
6. Find part number 120-50645-005 and cite the source.
7. Find part number 120-50645-011 and cite the source.
8. Find part number 120-29068-003 and cite the source.
9. What evidence supports part number 120-50645-005?
10. What evidence supports Figure 69?
11. What can TRACE-Net not prove about part number 120-50645-005?
12. Is 120-50645-005 interchangeable with 120-50645-011?
13. Does figure 69 prove installation safety?
14. Does figure 75 prove fit approval?
15. Does figure 91 prove aircraft effectivity?
16. Why was nomenclature missing from the visual route evidence?
17. Why does the visual route need OCR nomenclature evidence?
18. What changed after the raw OCR nomenclature extractor was added?
19. What source page supports the nomenclature for Figure 69?
20. Cite the proof for Figure 75's part number.
21. Is 120-50645-005 an approved replacement for 120-50645-011?
22. Can I safely install 120-50645-005 based only on Figure 69?
23. Summarize the evidence for DOUBLE PASSENGER SEAT ASSY.
24. Which figures link to DOUBLE PASSENGER SEAT ASSY?
25. Find part number 999-99999-999 and cite the source.
26. What does figure 999 show?
27. Explain the difference between visual proof and OCR proof for Figure 69.
28. What routes were required to answer what Figure 69 shows?
29. Can v2 summaries alone prove Figure 69 part identity?
30. Give the engineering limitations for Figure 91.

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes/uploads.
- No source-truth mutation.
- No answer permission.
- V2 summaries may guide route planning/framing only; they are not proof.
