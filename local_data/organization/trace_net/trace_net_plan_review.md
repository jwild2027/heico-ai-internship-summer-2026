# TRACE-Net route plan

Status: **OK**

## Summary

- records: 509
- usable_for_rag_records: 0
- needs_human_review_records: 509
- fishnet_enabled_records: 495
- table_route_records: 0
- figure_route_records: 485
- parts_list_route_records: 0
- front_matter_route_records: 10
- blank_route_records: 14

## route_counts

- blank: 14
- figure_diagram: 485
- front_matter: 10

## priority_counts

- high: 334
- medium: 175

## trust_tier_counts

- C: 493
- D: 16

## extractor_counts

- skip_blank: 14
- title_header_context_route: 10
- vision_figure_callout_route: 485

## reason_counts

- blank_or_low_value: 14
- no_visual_record: 484
- table_expected_missing: 331
- trust_tier_c: 493
- trust_tier_d: 16

## Sample page plans

### t_p_120_1176_p000001

- route: `front_matter`
- priority: `medium`
- extractor: `title_header_context_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: trust_tier_c
- safety layers: rescue_768(768/1200)

### t_p_120_1176_p000002

- route: `blank`
- priority: `medium`
- extractor: `skip_blank`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: blank_or_low_value, no_visual_record, trust_tier_c

### t_p_120_1176_p000003

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000004

- route: `front_matter`
- priority: `high`
- extractor: `title_header_context_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200)

### t_p_120_1176_p000005

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000006

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000007

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000008

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000009

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000010

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000011

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000012

- route: `blank`
- priority: `medium`
- extractor: `skip_blank`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: blank_or_low_value, no_visual_record, trust_tier_c

### t_p_120_1176_p000013

- route: `front_matter`
- priority: `high`
- extractor: `title_header_context_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200)

### t_p_120_1176_p000014

- route: `front_matter`
- priority: `high`
- extractor: `title_header_context_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200)

### t_p_120_1176_p000015

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000016

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000017

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000018

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000019

- route: `figure_diagram`
- priority: `medium`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000020

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000021

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000022

- route: `front_matter`
- priority: `high`
- extractor: `title_header_context_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200)

### t_p_120_1176_p000023

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000024

- route: `figure_diagram`
- priority: `medium`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000025

- route: `blank`
- priority: `medium`
- extractor: `skip_blank`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: blank_or_low_value, no_visual_record, trust_tier_c

### t_p_120_1176_p000026

- route: `front_matter`
- priority: `high`
- extractor: `title_header_context_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: trust_tier_d
- safety layers: rescue_768(768/1200)

### t_p_120_1176_p000027

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `D`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_d
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000028

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000029

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000030

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000031

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000032

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000033

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000034

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000035

- route: `blank`
- priority: `medium`
- extractor: `skip_blank`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: blank_or_low_value, no_visual_record, trust_tier_c

### t_p_120_1176_p000036

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000037

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000038

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000039

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000040

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000041

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000042

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000043

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000044

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000045

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000046

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000047

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000048

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000049

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000050

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000051

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000052

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000053

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000054

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000055

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000056

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000057

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000058

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000059

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000060

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000061

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000062

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000063

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000064

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000065

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000066

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000067

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000068

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000069

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000070

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000071

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000072

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000073

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000074

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000075

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000076

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000077

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000078

- route: `figure_diagram`
- priority: `high`
- extractor: `vision_figure_callout_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, table_expected_missing, trust_tier_c
- safety layers: rescue_768(768/1200), rescue_512(512/1200)

### t_p_120_1176_p000079

- route: `blank`
- priority: `medium`
- extractor: `skip_blank`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: blank_or_low_value, no_visual_record, trust_tier_c

### t_p_120_1176_p000080

- route: `front_matter`
- priority: `medium`
- extractor: `title_header_context_route`
- trust tier: `C`
- usable_for_rag: `False`
- needs_human_review: `True`
- reasons: no_visual_record, trust_tier_c
- safety layers: rescue_768(768/1200)
