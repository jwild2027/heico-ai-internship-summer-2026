#!/usr/bin/env python3
"""Run the TRACE-Net H30 full-stack 200-question server benchmark.

The benchmark calls the full cognitive TRACE-Net endpoint and then requires a
separate Gemma4 rendering pass for every one of the 200 questions. Progress is
printed for retrieval and Gemma separately, every completed question is
checkpointed, and the final JSON contains the question, TRACE-Net safe draft,
Gemma-rendered answer, follow-up questions, route, evidence, Self-RAG/CRAG,
validation status, safety checks, model metadata, and timing.

This runner is read-only. It does not mutate source truth or write to Postgres,
Qdrant, or OpenSearch.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


MODULE = "trace_net_h30_server_benchmark_200_v1"
VERSION = "v1"
SCHEMA_VERSION = 3
DEFAULT_BANK = ""
EMBEDDED_QUESTION_BANK_JSON = r'''{"module":"trace_net_h30_server_benchmark_200_question_bank_v1","version":"v1","question_count":200,"route_count":19,"routes":["safe_general_chat","exact_identifier_lookup","guided_part_discovery","ata_system_discovery","nomenclature_function_search","exact_table_ipl_lookup","visual_figure_callout_lookup","procedure_task_lookup","warning_caution_note_lookup","authority_eligibility_verification","document_page_navigation","graph_relationship_reasoning","semantic_discovery","cross_source_comparison","contradiction_resolution","ocr_scan_recovery","high_degree_entity_aggregation","multi_question_research","clarification_no_evidence"],"expected_route_counts":{"safe_general_chat":10,"exact_identifier_lookup":11,"guided_part_discovery":10,"ata_system_discovery":11,"nomenclature_function_search":10,"exact_table_ipl_lookup":10,"visual_figure_callout_lookup":12,"procedure_task_lookup":10,"warning_caution_note_lookup":10,"authority_eligibility_verification":12,"document_page_navigation":10,"graph_relationship_reasoning":10,"semantic_discovery":10,"cross_source_comparison":11,"contradiction_resolution":10,"ocr_scan_recovery":11,"high_degree_entity_aggregation":11,"multi_question_research":11,"clarification_no_evidence":10},"purpose":"Exercise every H30 cognitive route plus the legacy normal, guided, visual, table, OCR, graph, semantic, Self-RAG, CRAG, and Gemma validation paths.","safety_contract":{"read_only":true,"source_truth_mutation_allowed":false,"postgres_write_attempt":false,"qdrant_write_attempt":false,"opensearch_write_attempt":false},"questions":[{"question_id":"q001","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"hello"},{"question_id":"q002","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"hi"},{"question_id":"q003","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"hey"},{"question_id":"q004","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"good morning"},{"question_id":"q005","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"good afternoon"},{"question_id":"q006","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"good evening"},{"question_id":"q007","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"howdy"},{"question_id":"q008","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"thanks"},{"question_id":"q009","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"thank you"},{"question_id":"q010","suite":"route_core","expected_route":"safe_general_chat","legacy_family":"general_chat","question":"what can you do?"},{"question_id":"q011","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Find part 120-41824-003"},{"question_id":"q012","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Look up part 120-41824-007"},{"question_id":"q013","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Search for P/N 120-41824-001"},{"question_id":"q014","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Locate part 120-45850-007"},{"question_id":"q015","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Find component 120-45850-507"},{"question_id":"q016","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Look up P/N 120-41824-009"},{"question_id":"q017","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Find part 120-41824-297"},{"question_id":"q018","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Search for part 120-11760-084"},{"question_id":"q019","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Locate P/N 120-45850-003"},{"question_id":"q020","suite":"route_core","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Find part 120-41824"},{"question_id":"q021","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"The P/N contains 41824"},{"question_id":"q022","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"The part number starts with MS49"},{"question_id":"q023","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"The P/N ends with 003"},{"question_id":"q024","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"I only remember that the P/N starts with NAS"},{"question_id":"q025","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"The component number contains 45850"},{"question_id":"q026","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"The part begins with 120-4"},{"question_id":"q027","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"I only know the part number contains 4956"},{"question_id":"q028","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"The P/N suffix is 007"},{"question_id":"q029","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"The component number starts with MS"},{"question_id":"q030","suite":"route_core","expected_route":"guided_part_discovery","legacy_family":"guided_candidate_discovery_plus_source_resolution","question":"I only remember a part number fragment 41824"},{"question_id":"q031","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"I have a part I want to find, ATA number starts with 25"},{"question_id":"q032","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"Search ATA 25"},{"question_id":"q033","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"Find material under ATA 25-21-00"},{"question_id":"q034","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"The ATA chapter begins with 32"},{"question_id":"q035","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"Look in chapter 21"},{"question_id":"q036","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"ATA code starts with 27"},{"question_id":"q037","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"The component is somewhere in ATA 33"},{"question_id":"q038","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"Search the ATA 35 system area"},{"question_id":"q039","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"I only know the ATA chapter is 24"},{"question_id":"q040","suite":"route_core","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"Find the relevant section in ATA 52"},{"question_id":"q041","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Find the locking ring near the seat"},{"question_id":"q042","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Search for a retaining ring in the cabin"},{"question_id":"q043","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Find the bracket near the armrest"},{"question_id":"q044","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Locate the latch near the seat"},{"question_id":"q045","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Find a fastener near the seat assembly"},{"question_id":"q046","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Search for the hinge by the armrest"},{"question_id":"q047","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Find the washer used near the seat"},{"question_id":"q048","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Locate the spring in the cabin panel"},{"question_id":"q049","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Find the clip near the seat"},{"question_id":"q050","suite":"route_core","expected_route":"nomenclature_function_search","legacy_family":"guided_normal_visual_hybrid","question":"Search for a fitting in the galley"},{"question_id":"q051","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Search the IPL table for item 14"},{"question_id":"q052","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Find item 17 in the illustrated parts list"},{"question_id":"q053","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Show the table row for item 3"},{"question_id":"q054","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Search the IPL for nomenclature RING LOCKING"},{"question_id":"q055","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Find the quantity column for item 22"},{"question_id":"q056","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Look up item 8 in the parts table"},{"question_id":"q057","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Search the row containing 120-41824-003"},{"question_id":"q058","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Find the table entry for SINGLE PASSENGER SEAT ASSY"},{"question_id":"q059","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Show item 5 from the IPL"},{"question_id":"q060","suite":"route_core","expected_route":"exact_table_ipl_lookup","legacy_family":"normal_table_structured_retrieval","question":"Which column lists the vendor code in the table?"},{"question_id":"q061","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Show the diagram for this component"},{"question_id":"q062","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Find figure 2 sheet 1"},{"question_id":"q063","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Show the drawing for part 120-41824-003"},{"question_id":"q064","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Which callout points to the locking ring?"},{"question_id":"q065","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Find an exploded view of the seat assembly"},{"question_id":"q066","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Show the illustration for the armrest"},{"question_id":"q067","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Locate figure 15"},{"question_id":"q068","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Find the schematic for the seat latch"},{"question_id":"q069","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Show the image containing part 120-45850-007"},{"question_id":"q070","suite":"route_core","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Find the visual page for callout 17"},{"question_id":"q071","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"How do I remove this assembly?"},{"question_id":"q072","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"What are the installation steps for the seat latch?"},{"question_id":"q073","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"Give the procedure for replacing the armrest"},{"question_id":"q074","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"What tools are required for this task?"},{"question_id":"q075","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"Show the disassembly steps for the seat assembly"},{"question_id":"q076","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"How is the bracket installed?"},{"question_id":"q077","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"What step follows removal of the panel?"},{"question_id":"q078","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"Find the assembly procedure for the seat"},{"question_id":"q079","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"How do I replace the fitting?"},{"question_id":"q080","suite":"route_core","expected_route":"procedure_task_lookup","legacy_family":"normal_procedure_retrieval","question":"List the steps to remove the cover"},{"question_id":"q081","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"What warning applies to this task?"},{"question_id":"q082","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"Find the caution for seat removal"},{"question_id":"q083","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"Show the note associated with the procedure"},{"question_id":"q084","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"What safety precaution applies here?"},{"question_id":"q085","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"Find any hazard statement for this task"},{"question_id":"q086","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"What caution appears before installation?"},{"question_id":"q087","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"Show warnings for the panel procedure"},{"question_id":"q088","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"Find the safety note for this assembly"},{"question_id":"q089","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"What precaution applies to removing the seat?"},{"question_id":"q090","suite":"route_core","expected_route":"warning_caution_note_lookup","legacy_family":"normal_warning_retrieval","question":"Find the warning block related to the fitting"},{"question_id":"q091","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"Is part 120-41824-003 an approved replacement?"},{"question_id":"q092","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"What effectivity applies to part 120-41824-007?"},{"question_id":"q093","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"Is this component interchangeable?"},{"question_id":"q094","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"Is part 120-45850-007 eligible?"},{"question_id":"q095","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"Does this part fitment have explicit authority?"},{"question_id":"q096","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"What installation authority applies to this component?"},{"question_id":"q097","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"What applicability authority exists for this component?"},{"question_id":"q098","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"Is 120-41824-001 approved for installation?"},{"question_id":"q099","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"Can part 120-41824-009 be used as an approved replacement?"},{"question_id":"q100","suite":"route_core","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"What interchangeability authority exists for 120-41824-003?"},{"question_id":"q101","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Which page discusses the component?"},{"question_id":"q102","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Where is the seat assembly discussed?"},{"question_id":"q103","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Find the page containing the locking ring"},{"question_id":"q104","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Take me to the manual location for the armrest"},{"question_id":"q105","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Which page contains part 120-41824-003?"},{"question_id":"q106","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Where does the manual mention the seat latch?"},{"question_id":"q107","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Find the first page for the cabin panel"},{"question_id":"q108","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Show nearby pages for t_p_120_1176_p000084"},{"question_id":"q109","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"What is the location in the manual for the fitting?"},{"question_id":"q110","suite":"route_core","expected_route":"document_page_navigation","legacy_family":"normal_navigation_retrieval","question":"Find the page where the bracket appears"},{"question_id":"q111","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"What assembly contains this part?"},{"question_id":"q112","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"Which components are connected to the seat assembly?"},{"question_id":"q113","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"What is linked to the armrest?"},{"question_id":"q114","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"Which parts are mentioned together with the latch?"},{"question_id":"q115","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"What relationship connects the bracket and seat assembly?"},{"question_id":"q116","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"Which assembly contains the locking ring?"},{"question_id":"q117","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"What references this component?"},{"question_id":"q118","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"What is connected to part 120-41824-003?"},{"question_id":"q119","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"Which components are linked to the cabin panel?"},{"question_id":"q120","suite":"route_core","expected_route":"graph_relationship_reasoning","legacy_family":"graph_guidance_plus_source_resolution","question":"What assembly relationship exists for the seat fitting?"},{"question_id":"q121","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Find pages about corrosion prevention topics"},{"question_id":"q122","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Search for information related to electrical bonding"},{"question_id":"q123","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Find material about passenger comfort systems"},{"question_id":"q124","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Find content related to surface treatment"},{"question_id":"q125","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Search for pages on structural inspection"},{"question_id":"q126","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Find something about corrosion control"},{"question_id":"q127","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Locate information about cleaning materials"},{"question_id":"q128","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Search the topic of environmental protection"},{"question_id":"q129","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"What does the manual discuss about lubrication requirements?"},{"question_id":"q130","suite":"route_core","expected_route":"semantic_discovery","legacy_family":"qdrant_summary_graph_plus_source_resolution","question":"Find pages on general maintenance philosophy"},{"question_id":"q131","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Compare both manuals for the same topic"},{"question_id":"q132","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Compare the two revisions for this component"},{"question_id":"q133","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"What is the difference between revision 3 and revision 4?"},{"question_id":"q134","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Compare the nomenclature used in both manuals"},{"question_id":"q135","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Compare source A with source B for this part"},{"question_id":"q136","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"What changed between revisions?"},{"question_id":"q137","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Compare both manuals for ATA 25-21-00"},{"question_id":"q138","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Compare the table descriptions between revisions"},{"question_id":"q139","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Show the difference between two manual versions"},{"question_id":"q140","suite":"route_core","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Compare how each revision describes the component"},{"question_id":"q141","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"These two sources disagree and show different numbers"},{"question_id":"q142","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"Resolve the conflict between these part references"},{"question_id":"q143","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"Why is there a mismatch between the two records?"},{"question_id":"q144","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"The pages show different numbers; which one is supported?"},{"question_id":"q145","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"Find the contradiction in the revision data"},{"question_id":"q146","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"The OCR and table disagree about the value"},{"question_id":"q147","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"Resolve conflicting ATA references"},{"question_id":"q148","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"Find the contradiction between these sources"},{"question_id":"q149","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"Explain the metadata mismatch for the candidate"},{"question_id":"q150","suite":"route_core","expected_route":"contradiction_resolution","legacy_family":"normal_conflict_resolution","question":"Two manual entries disagree about the nomenclature"},{"question_id":"q151","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"The scan is blurry; read the image"},{"question_id":"q152","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"Use OCR on the faint page"},{"question_id":"q153","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"The number is hard to read in the scan"},{"question_id":"q154","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"Read the image because the text is blurry"},{"question_id":"q155","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"Recover the value from the scanned page"},{"question_id":"q156","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"Check OCR for the faded label"},{"question_id":"q157","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"The scan is faint and difficult to read"},{"question_id":"q158","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"Read the blurry callout"},{"question_id":"q159","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"Use OCR to recover the table value"},{"question_id":"q160","suite":"route_core","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"The scanned text is hard to read"},{"question_id":"q161","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Show every document mentioning this component"},{"question_id":"q162","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"List all references to this part"},{"question_id":"q163","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Find all pages for this component"},{"question_id":"q164","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Search across the manuals for this identifier"},{"question_id":"q165","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Show every page mentioning the seat assembly"},{"question_id":"q166","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Summarize all references to the bracket"},{"question_id":"q167","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Where is this part used across the manuals?"},{"question_id":"q168","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Find every document containing 120-41824-003"},{"question_id":"q169","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Show all pages that reference the fitting"},{"question_id":"q170","suite":"route_core","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"List every page related to this component"},{"question_id":"q171","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Find part 120-41824-003 and show its figure"},{"question_id":"q172","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Find part 120-41824-007 and determine whether it is approved"},{"question_id":"q173","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Search the IPL table and show the warning for item 14"},{"question_id":"q174","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Locate ATA 25-21-00 and compare both manuals"},{"question_id":"q175","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Find the procedure and show the associated figure"},{"question_id":"q176","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Find part 120-45850-007 and identify its table row"},{"question_id":"q177","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Show the caution and removal procedure for the assembly"},{"question_id":"q178","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Find figure 15 and determine the installation authority"},{"question_id":"q179","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Locate page t_p_120_1176_p000084 and compare its revision"},{"question_id":"q180","suite":"route_core","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Find part 120-41824-003 and identify its ATA 25-21-00 section"},{"question_id":"q181","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"Can you assist me?"},{"question_id":"q182","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"I need help with something"},{"question_id":"q183","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"I am looking for something"},{"question_id":"q184","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"Can you search for it?"},{"question_id":"q185","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"I do not remember enough details"},{"question_id":"q186","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"Where should I begin?"},{"question_id":"q187","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"I need to find an unknown thing"},{"question_id":"q188","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"Can you identify what detail is missing?"},{"question_id":"q189","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"I have very little information"},{"question_id":"q190","suite":"route_core","expected_route":"clarification_no_evidence","legacy_family":"clarification_exit","question":"Please help me identify it"},{"question_id":"q191","suite":"cross_route_regression","expected_route":"exact_identifier_lookup","legacy_family":"normal_source_truth_plus_guided_visual_recovery","question":"Hello, find part 120-41824-003"},{"question_id":"q192","suite":"cross_route_regression","expected_route":"ata_system_discovery","legacy_family":"guided_normal_semantic_hybrid","question":"ATA number starts with 25, not the part number"},{"question_id":"q193","suite":"cross_route_regression","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Show figure 2 for part 120-41824-003"},{"question_id":"q194","suite":"cross_route_regression","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"Is part 120-41824-003 approved for installation?"},{"question_id":"q195","suite":"cross_route_regression","expected_route":"ocr_scan_recovery","legacy_family":"ocr_visual_recovery","question":"The scan is blurry and the table is hard to read"},{"question_id":"q196","suite":"cross_route_regression","expected_route":"cross_source_comparison","legacy_family":"normal_cross_source_retrieval","question":"Compare warnings between revisions"},{"question_id":"q197","suite":"cross_route_regression","expected_route":"high_degree_entity_aggregation","legacy_family":"graph_aggregation_plus_source_retrieval","question":"Show every page about the locking ring"},{"question_id":"q198","suite":"cross_route_regression","expected_route":"visual_figure_callout_lookup","legacy_family":"visual_figure_retrieval","question":"Which page has figure 15?"},{"question_id":"q199","suite":"cross_route_regression","expected_route":"multi_question_research","legacy_family":"multi_route_decomposition","question":"Find part 120-41824-003 and show item 14 in the IPL"},{"question_id":"q200","suite":"cross_route_regression","expected_route":"authority_eligibility_verification","legacy_family":"normal_authority_retrieval","question":"The P/N contains 41824 and is it approved?"}]}'''
DEFAULT_BASE_URL = "http://127.0.0.1:8128"
DEFAULT_API_KEY = "trace-net-gemma-cognitive-local"
DEFAULT_OUTPUT = (
    "/data/trace_net_runs/cognitive_benchmark_200_gemma_every_question_v1/"
    "trace_net_h30_server_benchmark_200_v1.json"
)
DEFAULT_GEMMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_GEMMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
DEFAULT_GEMMA_MODEL = "gemma4:26b"
FOLLOWUP_KEYS = {
    "follow_up_questions",
    "followup_questions",
    "followups",
    "clarifying_questions",
    "helpful_follow_up_questions",
    "questions_for_user",
}
UNSAFE_TRUE_FLAGS = (
    "answer_permission",
    "final_answer_allowed",
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
)
PROMPT_LEAK_MARKERS = (
    "SYSTEM INSTRUCTIONS",
    "EVIDENCE_ENVELOPE",
    "NON-NEGOTIABLE RULES",
    "DIRECT CITATION-READY EVIDENCE",
)


def compact(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def load_question_bank(path_value: str, repo_root: Path) -> Dict[str, Any]:
    if str(path_value or "").strip():
        path = Path(path_value)
        if not path.is_absolute():
            path = repo_root / path
        bank = load_json(path)
        bank["_path"] = str(path)
        return bank
    bank = json.loads(EMBEDDED_QUESTION_BANK_JSON)
    if not isinstance(bank, dict):
        raise ValueError("Embedded question bank root must be an object")
    bank["_path"] = "<embedded:trace_net_h30_server_benchmark_200_v1>"
    return bank


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    return round(ordered[lower] * (1.0 - weight) + ordered[upper] * weight, 3)


def unique_strings(values: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen = set()
    for raw in values:
        text = re.sub(r"\s+", " ", str(raw or "")).strip()
        text = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", text).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def collect_keyed_questions(value: Any, output: List[str], *, depth: int = 0) -> None:
    if depth > 5:
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FOLLOWUP_KEYS:
                if isinstance(child, list):
                    output.extend(str(item) for item in child)
                elif isinstance(child, str):
                    output.extend(child.splitlines())
                continue
            collect_keyed_questions(child, output, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            collect_keyed_questions(child, output, depth=depth + 1)


def questions_from_answer(answer: str) -> List[str]:
    questions: List[str] = []
    in_followup_section = False
    for raw_line in str(answer or "").splitlines():
        line = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", raw_line.strip())
        lower = line.lower().rstrip(":")
        if lower in {
            "helpful follow-up questions",
            "follow-up questions",
            "clarifying questions",
            "questions",
            "next questions",
        }:
            in_followup_section = True
            continue
        if not line:
            continue
        if line.endswith("?") and (in_followup_section or len(line) <= 400):
            questions.append(line)
    return questions


def extract_follow_up_questions(result: Mapping[str, Any], answer: str) -> List[str]:
    values: List[str] = []
    collect_keyed_questions(result, values)
    values.extend(questions_from_answer(answer))
    return unique_strings(values)


def post_json(
    url: str,
    api_key: str,
    payload: Mapping[str, Any],
    timeout: float,
) -> Tuple[int, Dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            value = json.loads(raw)
            return response.status, value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return exc.code, value if isinstance(value, dict) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def get_json(url: str, timeout: float) -> Tuple[int, Dict[str, Any]]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
            return response.status, value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return exc.code, value if isinstance(value, dict) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def compact_json(value: Any, limit: int = 24000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(value)
    return text[:limit]


def parse_gemma_json(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\\s*", "", raw, flags=re.I)
        raw = re.sub(r"\\s*```$", "", raw)
    candidates = [raw]
    if "{" in raw and "}" in raw:
        candidates.append(raw[raw.find("{"): raw.rfind("}") + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        if isinstance(value, dict):
            return value
    return {}


def gemma_render_prompt(
    question: str,
    expected_route: str,
    result: Mapping[str, Any],
    safe_answer: str,
) -> str:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        envelope = {}
    bounded = {
        "direct_evidence": envelope.get("direct_evidence") or [],
        "candidate_evidence": envelope.get("candidate_evidence") or [],
        "visual_guidance": envelope.get("visual_guidance") or [],
        "semantic_guidance": envelope.get("semantic_guidance") or [],
        "authority_evidence": envelope.get("authority_evidence") or [],
        "contradictions": envelope.get("contradictions") or [],
        "uncertainties": envelope.get("uncertainties") or [],
        "retrieval_tunnels_used": envelope.get("retrieval_tunnels_used") or [],
    }
    return f"""You are Gemma4 acting as TRACE-Net's benchmark answer renderer.

This call is required for every benchmark question, including greetings and
fail-closed technical responses. You do not choose evidence and you must not
add facts from memory.

NON-NEGOTIABLE RULES
1. Use only the user question, TRACE-Net safe draft, and bounded evidence below.
2. Preserve all uncertainty and fail-closed language.
3. Candidate, visual, semantic, graph, and summary material is guidance only.
4. Direct technical claims require direct evidence and matching citation IDs.
5. Never invent identifiers, ATA references, pages, figures, table values,
   procedures, warnings, manufacturers, revisions, or citations.
6. Approval, fit, interchangeability, effectivity, eligibility, applicability,
   and installation safety require explicit authority evidence. Otherwise say
   authority was not established.
7. Keep follow-up questions useful and deduplicated.
8. Return one JSON object only. Do not use markdown fences.

JSON SCHEMA
{{
  "answer": "complete user-facing answer",
  "follow_up_questions": ["question?"],
  "review": {{
    "clue_satisfaction": "PASS or FAIL",
    "source_support": "PASS or FAIL",
    "citation_alignment": "PASS or FAIL",
    "safety_boundary": "PASS or FAIL",
    "notes": ["brief reason"]
  }}
}}

QUESTION
{question}

EXPECTED ROUTE
{expected_route}

ACTUAL ROUTE
{result.get('route')}

TRACE-NET SAFE DRAFT
{safe_answer}

BOUNDED TRACE-NET MATERIAL
{compact_json(bounded, 24000)}
"""


def call_gemma_every_question(
    *,
    gemma_url: str,
    gemma_model: str,
    gemma_timeout: float,
    question: str,
    expected_route: str,
    result: Mapping[str, Any],
    safe_answer: str,
) -> Dict[str, Any]:
    payload = {
        "model": gemma_model,
        "messages": [
            {"role": "system", "content": "Follow the TRACE-Net evidence-only benchmark rules exactly."},
            {"role": "user", "content": gemma_render_prompt(question, expected_route, result, safe_answer)},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 900},
    }
    started = time.time()
    status, response = post_json(gemma_url, "", payload, gemma_timeout)
    elapsed = round(time.time() - started, 3)
    message = response.get("message") if isinstance(response, Mapping) else None
    content = str(message.get("content") or "") if isinstance(message, Mapping) else ""
    parsed = parse_gemma_json(content)
    answer = str(parsed.get("answer") or "").strip()
    followups_raw = parsed.get("follow_up_questions")
    followups = unique_strings(followups_raw if isinstance(followups_raw, list) else [])
    review = parsed.get("review") if isinstance(parsed.get("review"), Mapping) else {}
    return {
        "http_status_code": status,
        "model_requested": gemma_model,
        "model_returned": response.get("model") if isinstance(response, Mapping) else None,
        "elapsed_seconds": elapsed,
        "raw_content": content,
        "parsed": parsed,
        "answer": answer,
        "follow_up_questions": followups,
        "review": dict(review),
        "error": response.get("error") if isinstance(response, Mapping) else None,
    }


def allowed_render_identifiers(question: str, safe_answer: str, result: Mapping[str, Any]) -> Dict[str, set[str]]:
    envelope = result.get("evidence_envelope") if isinstance(result.get("evidence_envelope"), Mapping) else {}
    blob = " ".join((
        question,
        safe_answer,
        compact_json(envelope.get("direct_evidence") or [], 60000),
        compact_json(envelope.get("candidate_evidence") or [], 60000),
        compact_json(envelope.get("visual_guidance") or [], 30000),
        compact_json(envelope.get("semantic_guidance") or [], 30000),
        compact_json(envelope.get("authority_evidence") or [], 30000),
    ))
    return {
        "identifiers": {normalize_token(value) for value in PART_OR_STANDARD_RE.findall(blob)},
        "atas": {normalize_token(value) for value in re.findall(r"\b\d{2}-\d{2}-\d{2}\b", blob)},
        "pages": {normalize_token(value) for value in re.findall(r"\bt_p_[A-Za-z0-9_]+\b", blob, re.I)},
    }


def evaluate_gemma_every_question(
    question: str,
    expected_route: str,
    result: Mapping[str, Any],
    safe_answer: str,
    gemma: Mapping[str, Any],
) -> Dict[str, Any]:
    failures: List[str] = []
    answer = str(gemma.get("answer") or "").strip()
    status = int(gemma.get("http_status_code") or 0)
    requested_model = str(gemma.get("model_requested") or "")
    returned_model = str(gemma.get("model_returned") or "")
    if status != 200:
        failures.append(f"gemma_http_status:{status}")
    if not answer:
        failures.append("gemma_empty_answer")
    if requested_model != DEFAULT_GEMMA_MODEL:
        failures.append(f"unexpected_gemma_model_requested:{requested_model}")
    if returned_model and returned_model != requested_model:
        failures.append(f"unexpected_gemma_model_returned:{returned_model}")
    if answer.lstrip().startswith("{"):
        failures.append("gemma_answer_is_json_blob")
    upper = answer.upper()
    for marker in PROMPT_LEAK_MARKERS:
        if marker in upper:
            failures.append(f"gemma_prompt_leak_marker:{marker}")

    allowed = allowed_render_identifiers(question, safe_answer, result)
    for value in PART_OR_STANDARD_RE.findall(answer):
        if normalize_token(value) not in allowed["identifiers"]:
            failures.append(f"gemma_unsupported_identifier:{value}")
    for value in re.findall(r"\b\d{2}-\d{2}-\d{2}\b", answer):
        if normalize_token(value) not in allowed["atas"]:
            failures.append(f"gemma_unsupported_ata:{value}")
    for value in re.findall(r"\bt_p_[A-Za-z0-9_]+\b", answer, re.I):
        if normalize_token(value) not in allowed["pages"]:
            failures.append(f"gemma_unsupported_page:{value}")

    direct = envelope_rows(result, "direct_evidence")
    authority = envelope_rows(result, "authority_evidence")
    cited = {int(value) for value in CITATION_RE.findall(answer)}
    valid_citations = set(range(1, len(direct) + 1))
    if not cited.issubset(valid_citations):
        failures.append("gemma_citation_id_out_of_range")
    if not direct and cited:
        failures.append("gemma_citation_without_direct_evidence")
    if expected_route in TECHNICAL_ROUTES and not direct and not answer_has_fail_closed_boundary(answer):
        failures.append("gemma_missing_fail_closed_boundary_without_direct_evidence")

    low = answer.lower()
    if any(term in low for term in DANGEROUS_CLAIM_TERMS) and not authority:
        negative = any(marker in low for marker in (
            "not approved", "not found", "not proven", "cannot confirm",
            "no explicit authority", "requires explicit", "not established",
            "insufficient", "authority was not established",
        ))
        if not negative:
            failures.append("gemma_safety_sensitive_claim_without_authority")

    followups = gemma.get("follow_up_questions")
    values = followups if isinstance(followups, list) else []
    if find_duplicate_questions(values):
        failures.append("gemma_duplicated_follow_up_questions")

    unique_failures = list(dict.fromkeys(failures))
    return {
        "quality_status": "PASS" if not unique_failures else "FAIL",
        "passed": not unique_failures,
        "failures": unique_failures,
        "model_requested": requested_model,
        "model_returned": returned_model,
        "gemma_called": True,
        "gemma_answer_character_count": len(answer),
        "gemma_follow_up_question_count": len(values),
    }


def evidence_counts(result: Mapping[str, Any]) -> Dict[str, int]:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        return {
            "direct": 0,
            "candidate": 0,
            "visual": 0,
            "semantic": 0,
            "authority": 0,
            "contradictions": 0,
            "uncertainties": 0,
        }

    def count(name: str) -> int:
        value = envelope.get(name)
        return len(value) if isinstance(value, list) else 0

    return {
        "direct": count("direct_evidence"),
        "candidate": count("candidate_evidence"),
        "visual": count("visual_guidance"),
        "semantic": count("semantic_guidance"),
        "authority": count("authority_evidence"),
        "contradictions": count("contradictions"),
        "uncertainties": count("uncertainties"),
    }


def retrieval_tunnels(result: Mapping[str, Any]) -> List[str]:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        return []
    value = envelope.get("retrieval_tunnels_used")
    return unique_strings(value if isinstance(value, list) else [])


def crag_repairs(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("crag_repair_attempts", "crag_repairs"):
        value = result.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    envelope = result.get("evidence_envelope")
    if isinstance(envelope, Mapping):
        value = envelope.get("crag_repairs")
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def evaluate_safety(result: Mapping[str, Any], answer: str) -> Dict[str, Any]:
    failures: List[str] = []

    for key in UNSAFE_TRUE_FLAGS:
        if result.get(key) is True:
            failures.append(f"unsafe_true_flag:{key}")

    if not answer.strip():
        failures.append("empty_answer")
    if answer.lstrip().startswith("{"):
        failures.append("json_blob_answer")
    upper = answer.upper()
    for marker in PROMPT_LEAK_MARKERS:
        if marker in upper:
            failures.append(f"prompt_leak_marker:{marker}")

    validation = result.get("post_answer_validation")
    writer_mode = str(result.get("writer_mode") or "")
    if isinstance(validation, Mapping) and validation.get("accepted") is False:
        if "fallback" not in writer_mode:
            failures.append("rejected_gemma_output_without_safe_fallback")

    counts = evidence_counts(result)
    if counts["direct"] == 0 and writer_mode.startswith("gemma_"):
        failures.append("gemma_used_without_direct_evidence")

    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "passed": not failures,
        "failures": failures,
    }



CITATION_RE = re.compile(r"\[(\d{1,3})\]")
PART_OR_STANDARD_RE = re.compile(
    r"\b(?:\d{2,3}-\d{4,6}(?:-\d{3})?|[A-Z]{2,5}\d[A-Z0-9-]{1,20})\b",
    re.I,
)
GARBAGE_CANDIDATE_WORDS = {
    "LIST", "VENDORS", "VENDOR", "NUMERICAL", "LEP", "INDEX", "TOC",
    "CONTENTS", "PAGE", "PAGES", "FIGURE", "TABLE", "REVISION", "REV",
}
FAIL_CLOSED_MARKERS = (
    "not citation-ready", "not citation ready", "not source proof", "not source-truth proof",
    "not source truth", "not a final identification", "candidate evidence", "guidance only",
    "not proven", "not found", "no direct", "no explicit authority", "cannot confirm",
    "could not verify", "requires explicit", "not established", "unresolved", "insufficient evidence",
)
DANGEROUS_CLAIM_TERMS = (
    "approved replacement", "approved for installation", "interchangeable", "interchangeability",
    "safe to install", "fits", "fitment", "eligible", "eligibility", "effectivity",
    "installation authority", "applicable to",
)
TECHNICAL_ROUTES = {
    "exact_identifier_lookup", "guided_part_discovery", "ata_system_discovery",
    "nomenclature_function_search", "exact_table_ipl_lookup", "visual_figure_callout_lookup",
    "procedure_task_lookup", "warning_caution_note_lookup", "authority_eligibility_verification",
    "document_page_navigation", "graph_relationship_reasoning", "semantic_discovery",
    "cross_source_comparison", "contradiction_resolution", "ocr_scan_recovery",
    "high_degree_entity_aggregation", "multi_question_research",
}
ROUTE_FIELD_MARKERS = {
    "safe_general_chat": ("hello", "help", "search", "welcome", "thank"),
    "exact_identifier_lookup": ("part", "p/n", "component", "identifier"),
    "guided_part_discovery": ("candidate", "part", "p/n", "prefix", "suffix", "contains"),
    "ata_system_discovery": ("ata", "chapter", "system"),
    "nomenclature_function_search": ("ring", "bracket", "latch", "pin", "seat", "assembly", "component", "nomenclature"),
    "exact_table_ipl_lookup": ("table", "ipl", "item", "row", "column", "nomenclature", "quantity", "vendor"),
    "visual_figure_callout_lookup": ("figure", "diagram", "drawing", "visual", "image", "callout", "illustration"),
    "procedure_task_lookup": ("procedure", "step", "remove", "removal", "install", "installation", "tool", "task"),
    "warning_caution_note_lookup": ("warning", "caution", "note", "precaution", "hazard", "safety"),
    "authority_eligibility_verification": ("approval", "approved", "effectivity", "interchange", "authority", "eligibility", "applicability", "installation"),
    "document_page_navigation": ("page", "location", "manual", "nearby"),
    "graph_relationship_reasoning": ("assembly", "relationship", "linked", "connected", "contains", "references"),
    "semantic_discovery": ("page", "topic", "related", "about", "information", "material"),
    "cross_source_comparison": ("compare", "comparison", "difference", "revision", "source", "manual"),
    "contradiction_resolution": ("conflict", "contradiction", "mismatch", "disagree", "different", "unresolved"),
    "ocr_scan_recovery": ("ocr", "scan", "scanned", "blurry", "faint", "image", "read"),
    "high_degree_entity_aggregation": ("all", "every", "across", "coverage", "page", "document", "reference"),
    "multi_question_research": ("part", "figure", "table", "warning", "procedure", "authority", "ata", "page", "revision"),
    "clarification_no_evidence": ("clue", "detail", "part", "ata", "manufacturer", "figure", "table", "page", "describe"),
}


def normalize_token(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def answer_has_fail_closed_boundary(answer: str) -> bool:
    low = str(answer or "").lower()
    return any(marker in low for marker in FAIL_CLOSED_MARKERS)


def envelope_rows(result: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        return []
    rows = envelope.get(key)
    return [dict(row) for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def candidate_value(row: Mapping[str, Any]) -> str:
    for key in ("candidate_value", "part_number", "normalized_value", "value", "identifier"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def candidate_is_ocr_noise(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    alnum = sum(ch.isalnum() for ch in text)
    if alnum < 3:
        return True
    if alnum / max(1, len(text)) < 0.55:
        return True
    if re.search(r"([^A-Za-z0-9\s-])\1{2,}", text):
        return True
    return False


def candidate_is_navigation_garbage(value: str) -> bool:
    tokens = {token.upper() for token in re.findall(r"[A-Za-z]+", str(value or ""))}
    return bool(tokens & GARBAGE_CANDIDATE_WORDS)


def query_constraints(question: str) -> Dict[str, Any]:
    exact = [match.group(0).upper() for match in PART_OR_STANDARD_RE.finditer(question)]
    ata_exact = [match.group(1) for match in re.finditer(r"\b(?:ATA\s*)?(\d{2}-\d{2}-\d{2})\b", question, re.I)]
    ata_prefix = None
    match = re.search(r"\b(?:ATA|chapter)(?:\s+(?:number|code))?.{0,20}?(\d{2})(?!\d)", question, re.I)
    if match:
        ata_prefix = match.group(1)
    prefix = None
    match = re.search(r"\b(?:part(?:\s+number)?|p/?n|component(?:\s+number)?)\b.{0,35}?\b(?:starts?|begins?|prefix)\b\s*(?:with\s+)?([A-Za-z0-9-]{2,16})", question, re.I)
    if match and not ata_prefix:
        prefix = match.group(1).strip(".,;: ").upper()
    contains = None
    match = re.search(r"\b(?:part(?:\s+number)?|p/?n|component(?:\s+number)?)\b.{0,35}?\bcontains?\b.{0,15}?([A-Za-z0-9-]{2,16})", question, re.I)
    if match:
        contains = match.group(1).strip(".,;: ").upper()
    suffix = None
    match = re.search(r"\b(?:part(?:\s+number)?|p/?n)\b.{0,35}?\b(?:ends?|suffix)\b.{0,15}?([A-Za-z0-9-]{2,16})", question, re.I)
    if match:
        suffix = match.group(1).strip(".,;: ").upper()
    figures = re.findall(r"\b(?:figure|fig\.?)[\s#:.-]*(\d{1,4})", question, re.I)
    items = re.findall(r"\bitem[\s#:.-]*(\d{1,4})", question, re.I)
    pages = re.findall(r"\bt_p_[A-Za-z0-9_]+\b", question, re.I)
    nomenclature = [term for term in (
        "locking ring", "retaining ring", "ring", "bracket", "latch", "fastener", "hinge",
        "washer", "spring", "clip", "fitting", "armrest", "seat assembly", "seat", "panel",
    ) if term in question.lower()]
    return {
        "exact": exact,
        "ata_exact": ata_exact,
        "ata_prefix": ata_prefix,
        "prefix": prefix,
        "contains": contains,
        "suffix": suffix,
        "figures": figures,
        "items": items,
        "pages": pages,
        "nomenclature": nomenclature,
    }


def find_duplicate_questions(values: Iterable[str]) -> List[str]:
    seen = set()
    duplicates: List[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
        if not normalized:
            continue
        if normalized in seen and normalized not in duplicates:
            duplicates.append(normalized)
        seen.add(normalized)
    return duplicates


def evaluate_answer_quality(
    question: str,
    expected_route: str,
    result: Mapping[str, Any],
    answer: str,
    followups: Sequence[str],
) -> Dict[str, Any]:
    failures: List[str] = []
    warnings: List[str] = []
    dimensions: Dict[str, str] = {}
    low_answer = str(answer or "").lower()
    constraints = query_constraints(question)
    candidates = envelope_rows(result, "candidate_evidence")
    direct = envelope_rows(result, "direct_evidence")
    visual = envelope_rows(result, "visual_guidance")
    semantic = envelope_rows(result, "semantic_guidance")
    authority = envelope_rows(result, "authority_evidence")
    evidence_blob = compact([direct, candidates, visual, semantic, authority], 120000)
    normalized_blob = normalize_token(answer + " " + evidence_blob)

    # Clue satisfaction: explicit identifiers and entity-bound ATA/figure/item/page clues
    # must survive into the answer/evidence envelope. Nomenclature clues must be answered
    # or explicitly fail closed rather than silently drifting to an unrelated component.
    clue_failures: List[str] = []
    for value in constraints["exact"]:
        if normalize_token(value) not in normalized_blob:
            clue_failures.append(f"missing_exact_clue:{value}")
    for value in constraints["ata_exact"]:
        if normalize_token(value) not in normalized_blob:
            clue_failures.append(f"missing_ata_clue:{value}")
    if constraints["ata_prefix"] and constraints["ata_prefix"] not in answer + " " + evidence_blob:
        clue_failures.append(f"missing_ata_prefix:{constraints['ata_prefix']}")
    for value in constraints["figures"]:
        if not re.search(rf"\b(?:figure|fig\.?)\s*{re.escape(value)}\b", answer + " " + evidence_blob, re.I):
            clue_failures.append(f"missing_figure_clue:{value}")
    for value in constraints["items"]:
        if not re.search(rf"\bitem\s*{re.escape(value)}\b", answer + " " + evidence_blob, re.I):
            clue_failures.append(f"missing_item_clue:{value}")
    for value in constraints["pages"]:
        if normalize_token(value) not in normalized_blob:
            clue_failures.append(f"missing_page_clue:{value}")
    if constraints["nomenclature"]:
        if not any(term in low_answer or term in evidence_blob.lower() for term in constraints["nomenclature"]):
            if not answer_has_fail_closed_boundary(answer):
                clue_failures.append("nomenclature_clue_not_satisfied_or_bounded")
    failures.extend(clue_failures)
    dimensions["clue_satisfaction"] = "PASS" if not clue_failures else "FAIL"

    # Candidate validity: preserve exact alphanumeric prefix/contains/suffix clues,
    # reject unrelated fallback candidates and obvious OCR/navigation garbage.
    candidate_failures: List[str] = []
    for row in candidates:
        value = candidate_value(row)
        normalized = normalize_token(value)
        if candidate_is_navigation_garbage(value):
            candidate_failures.append(f"navigation_garbage_candidate:{value}")
        if candidate_is_ocr_noise(value):
            candidate_failures.append(f"ocr_noise_candidate:{value}")
        if constraints["prefix"] and not normalized.startswith(normalize_token(constraints["prefix"])):
            candidate_failures.append(f"candidate_prefix_mismatch:{value}")
        if constraints["contains"] and normalize_token(constraints["contains"]) not in normalized:
            candidate_failures.append(f"candidate_contains_mismatch:{value}")
        if constraints["suffix"] and not normalized.endswith(normalize_token(constraints["suffix"])):
            candidate_failures.append(f"candidate_suffix_mismatch:{value}")
    failures.extend(candidate_failures)
    dimensions["candidate_validity"] = "PASS" if not candidate_failures else "FAIL"

    # Metadata conflicts must remain visibly unresolved in the answer.
    conflict_rows = [row for row in candidates if row.get("metadata_conflict")]
    if conflict_rows and not any(word in low_answer for word in ("conflict", "unresolved", "mismatch")):
        failures.append("metadata_conflict_promoted_without_warning")
        dimensions["metadata_consistency"] = "FAIL"
    else:
        dimensions["metadata_consistency"] = "PASS"

    # Follow-up duplication is graded on the user-visible answer text and structured
    # fields separately. Mirroring the same question in metadata and text is not itself
    # considered duplication.
    structured_raw: List[str] = []
    collect_keyed_questions(result, structured_raw)
    visible_raw = questions_from_answer(answer)
    duplicates = find_duplicate_questions(structured_raw) + find_duplicate_questions(visible_raw)
    if duplicates:
        failures.append("duplicated_follow_up_questions")
    if len({q.casefold() for q in followups}) != len(followups):
        failures.append("deduplicated_follow_up_output_still_contains_duplicates")
    dimensions["follow_up_deduplication"] = "PASS" if not duplicates else "FAIL"

    # Requested field relevance. Generic no-evidence text that ignores table, procedure,
    # warning, OCR, relationship, etc. is recorded as an answer-quality failure even
    # though it may still be safely fail-closed.
    field_markers = ROUTE_FIELD_MARKERS.get(expected_route, ())
    if field_markers and not any(marker in low_answer for marker in field_markers):
        failures.append("requested_field_not_addressed")
        dimensions["requested_field"] = "FAIL"
    else:
        dimensions["requested_field"] = "PASS"

    # Citation alignment and source support.
    cited = {int(value) for value in CITATION_RE.findall(answer)}
    valid = set(range(1, len(direct) + 1))
    citation_failures: List[str] = []
    if not cited.issubset(valid):
        citation_failures.append("citation_id_out_of_range")
    writer_mode = str(result.get("writer_mode") or "")
    if direct and writer_mode.startswith("gemma_") and not cited:
        citation_failures.append("direct_gemma_answer_missing_citation")
    if not direct and cited:
        citation_failures.append("citation_present_without_direct_evidence")
    validation = result.get("post_answer_validation")
    if not isinstance(validation, Mapping):
        citation_failures.append("post_answer_validation_missing")
    elif validation.get("accepted") is not True:
        if "fallback" not in writer_mode:
            citation_failures.append("rejected_answer_not_replaced_by_safe_fallback")
    failures.extend(citation_failures)
    dimensions["citation_alignment"] = "PASS" if not citation_failures else "FAIL"

    support_failures: List[str] = []
    if expected_route in TECHNICAL_ROUTES and not direct:
        if not answer_has_fail_closed_boundary(answer):
            support_failures.append("guidance_or_no_evidence_answer_missing_proof_boundary")
        if writer_mode.startswith("gemma_"):
            support_failures.append("gemma_used_without_direct_source_support")
    if any(term in low_answer for term in DANGEROUS_CLAIM_TERMS) and not authority:
        negative = any(marker in low_answer for marker in (
            "not approved", "not found", "not proven", "cannot confirm", "no explicit authority",
            "requires explicit", "not established", "insufficient",
        ))
        if not negative:
            support_failures.append("safety_sensitive_claim_without_explicit_authority")
    failures.extend(support_failures)
    dimensions["source_support"] = "PASS" if not support_failures else "FAIL"

    # Route/tunnel preservation and fail-closed safety flags.
    tunnels = retrieval_tunnels(result)
    route_failures: List[str] = []
    if expected_route in TECHNICAL_ROUTES and not tunnels:
        route_failures.append("technical_route_missing_retrieval_tunnels")
    if str(result.get("route") or "") != expected_route:
        route_failures.append("route_not_preserved")
    failures.extend(route_failures)
    dimensions["route_and_tunnel_preservation"] = "PASS" if not route_failures else "FAIL"

    flag_failures = [
        f"safety_flag_not_false:{key}"
        for key in UNSAFE_TRUE_FLAGS
        if result.get(key) is not False
    ]
    failures.extend(flag_failures)
    dimensions["fail_closed_flags"] = "PASS" if not flag_failures else "FAIL"

    unique_failures = list(dict.fromkeys(failures))
    return {
        "quality_status": "PASS" if not unique_failures else "FAIL",
        "passed": not unique_failures,
        "failures": unique_failures,
        "warnings": list(dict.fromkeys(warnings)),
        "dimensions": dimensions,
        "query_constraints": constraints,
        "candidate_count_checked": len(candidates),
        "direct_citation_count": len(direct),
        "authority_evidence_count": len(authority),
        "visible_follow_up_duplicate_count": len(find_duplicate_questions(visible_raw)),
        "structured_follow_up_duplicate_count": len(find_duplicate_questions(structured_raw)),
    }

def load_router_module(repo_root: Path) -> Any:
    path = repo_root / "scripts" / "serve_trace_net_cognitive_router_v1.py"
    if not path.is_file():
        raise FileNotFoundError(f"Missing cognitive router for bank preflight: {path}")
    spec = importlib.util.spec_from_file_location("trace_net_benchmark_router_preflight", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not create import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def preflight_question_bank(bank: Mapping[str, Any], repo_root: Path) -> Dict[str, Any]:
    questions = bank.get("questions")
    if not isinstance(questions, list):
        raise ValueError("Question bank is missing questions[]")
    if len(questions) != 200:
        raise ValueError(f"Expected exactly 200 questions, found {len(questions)}")

    module = load_router_module(repo_root)
    failures: List[Dict[str, str]] = []
    route_counts: Counter[str] = Counter()
    ids = set()

    for raw in questions:
        if not isinstance(raw, Mapping):
            raise ValueError("Every question-bank record must be an object")
        question_id = str(raw.get("question_id") or "")
        expected = str(raw.get("expected_route") or "")
        question = str(raw.get("question") or "")
        if not question_id or question_id in ids:
            raise ValueError(f"Missing or duplicate question_id: {question_id!r}")
        ids.add(question_id)
        atoms = module.extract_query_atoms(question)
        plan = module.plan_route(atoms)
        actual = str(plan.primary_route)
        route_counts[expected] += 1
        if actual != expected:
            failures.append({
                "question_id": question_id,
                "question": question,
                "expected_route": expected,
                "planned_route": actual,
            })

    all_routes = set(getattr(module, "ALL_ROUTES"))
    missing_routes = sorted(all_routes - set(route_counts))
    low_coverage_routes = sorted(route for route in all_routes if route_counts.get(route, 0) < 10)
    return {
        "quality_status": "PASS" if not failures and not missing_routes and not low_coverage_routes else "FAIL",
        "question_count": len(questions),
        "route_count": len(route_counts),
        "expected_route_counts": dict(sorted(route_counts.items())),
        "missing_routes": missing_routes,
        "routes_below_10_questions": low_coverage_routes,
        "planner_mismatch_count": len(failures),
        "planner_mismatches": failures,
    }


def summarize(
    records: Sequence[Mapping[str, Any]],
    bank: Mapping[str, Any],
    *,
    started_at_epoch: float,
    status: str,
) -> Dict[str, Any]:
    expected_counts: Counter[str] = Counter()
    actual_counts: Counter[str] = Counter()
    writer_modes: Counter[str] = Counter()
    gemma_statuses: Counter[str] = Counter()
    critic_statuses: Counter[str] = Counter()
    durations: List[float] = []
    failures: List[str] = []

    for record in records:
        expected_counts[str(record.get("expected_route") or "")] += 1
        actual_counts[str(record.get("actual_route") or "")] += 1
        writer_modes[str(record.get("writer_mode") or "")] += 1
        gemma_statuses[str(record.get("gemma_status") or "")] += 1
        critic_statuses[str(record.get("critic_quality_status") or "")] += 1
        durations.append(float(record.get("elapsed_seconds") or 0.0))
        if not record.get("passed"):
            failures.append(str(record.get("question_id") or ""))

    expected_routes = set(bank.get("routes") or [])
    actual_routes = {route for route in actual_counts if route}
    route_pass_count = sum(1 for record in records if record.get("route_pass"))
    safety_pass_count = sum(1 for record in records if record.get("safety_pass"))
    answer_pass_count = sum(1 for record in records if record.get("answer_pass"))
    semantic_answer_pass_count = sum(1 for record in records if record.get("semantic_answer_pass"))
    pass_count = sum(1 for record in records if record.get("passed"))
    gemma_every_question_count = sum(1 for record in records if record.get("benchmark_gemma_called") is True)
    gemma_every_question_pass_count = sum(1 for record in records if record.get("benchmark_gemma_pass") is True)
    gemma_render_durations = [float(record.get("benchmark_gemma_elapsed_seconds") or 0.0) for record in records]

    return {
        "status": status,
        "quality_status": "PASS" if status == "COMPLETE" and pass_count == len(records) == 200 else "FAIL",
        "question_count_expected": int(bank.get("question_count") or 200),
        "question_count_completed": len(records),
        "pass_count": pass_count,
        "failure_count": len(records) - pass_count,
        "failed_question_ids": failures,
        "route_pass_count": route_pass_count,
        "answer_pass_count": answer_pass_count,
        "semantic_answer_pass_count": semantic_answer_pass_count,
        "safety_pass_count": safety_pass_count,
        "gemma_every_question_count": gemma_every_question_count,
        "gemma_every_question_pass_count": gemma_every_question_pass_count,
        "gemma_every_question_required": True,
        "gemma_model": DEFAULT_GEMMA_MODEL,
        "gemma_render_elapsed_seconds_sum": round(sum(gemma_render_durations), 3),
        "gemma_render_elapsed_seconds_mean": round(statistics.mean(gemma_render_durations), 3) if gemma_render_durations else 0.0,
        "expected_route_counts": dict(sorted(expected_counts.items())),
        "actual_route_counts": dict(sorted(actual_counts.items())),
        "routes_covered": sorted(actual_routes),
        "missing_routes": sorted(expected_routes - actual_routes),
        "writer_mode_counts": dict(sorted(writer_modes.items())),
        "gemma_status_counts": dict(sorted(gemma_statuses.items())),
        "critic_quality_status_counts": dict(sorted(critic_statuses.items())),
        "elapsed_seconds_total": round(time.time() - started_at_epoch, 3),
        "request_elapsed_seconds_sum": round(sum(durations), 3),
        "request_elapsed_seconds_mean": round(statistics.mean(durations), 3) if durations else 0.0,
        "request_elapsed_seconds_median": round(statistics.median(durations), 3) if durations else 0.0,
        "request_elapsed_seconds_p95": percentile(durations, 0.95),
        "request_elapsed_seconds_max": round(max(durations), 3) if durations else 0.0,
    }


def build_report(
    records: Sequence[Mapping[str, Any]],
    bank: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    base_url: str,
    output_path: Path,
    jsonl_path: Path,
    started_at_epoch: float,
    status: str,
) -> Dict[str, Any]:
    return {
        "module": MODULE,
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "benchmark_status": status,
        "generated_at_epoch": int(time.time()),
        "base_url": base_url,
        "endpoint": "/api/trace-net/ask",
        "question_bank_module": bank.get("module"),
        "question_bank_path": str(bank.get("_path") or ""),
        "answer_quality_dimensions": [
            "clue_satisfaction", "candidate_validity", "metadata_consistency",
            "follow_up_deduplication", "requested_field", "citation_alignment",
            "source_support", "route_and_tunnel_preservation", "fail_closed_flags",
        ],
        "preflight": dict(preflight),
        "summary": summarize(records, bank, started_at_epoch=started_at_epoch, status=status),
        "output_paths": {
            "json": str(output_path),
            "jsonl": str(jsonl_path),
            "checkpoint": str(output_path.with_name(output_path.stem + "_checkpoint.json")),
        },
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "candidate_semantic_visual_graph_summary_guidance_is_not_proof": True,
            "production_gemma_requires_direct_citation_ready_evidence": True,
            "benchmark_gemma_render_required_for_every_question": True,
            "benchmark_gemma_may_only_rephrase_bounded_trace_net_material": True,
            "post_answer_validation_required": True,
        },
        "records": list(records),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--question-bank", default=DEFAULT_BANK)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--gemma-url", default=DEFAULT_GEMMA_URL)
    parser.add_argument("--gemma-tags-url", default=DEFAULT_GEMMA_TAGS_URL)
    parser.add_argument("--gemma-model", default=DEFAULT_GEMMA_MODEL)
    parser.add_argument("--gemma-timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--max-questions", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--skip-bank-preflight", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    output_path = Path(args.output)
    checkpoint_path = output_path.with_name(output_path.stem + "_checkpoint.json")
    jsonl_path = output_path.with_suffix(".jsonl")

    bank = load_question_bank(args.question_bank, repo_root)

    preflight = (
        {
            "quality_status": "SKIPPED",
            "question_count": len(bank.get("questions") or []),
        }
        if args.skip_bank_preflight
        else preflight_question_bank(bank, repo_root)
    )
    if preflight.get("quality_status") == "FAIL":
        report = build_report(
            [], bank, preflight,
            base_url=args.base_url,
            output_path=output_path,
            jsonl_path=jsonl_path,
            started_at_epoch=time.time(),
            status="BANK_PREFLIGHT_FAILED",
        )
        write_json_atomic(output_path, report)
        print(json.dumps(preflight, indent=2, ensure_ascii=False), flush=True)
        print(f"BENCHMARK_JSON={output_path}", flush=True)
        raise SystemExit("TRACE_NET_H30_SERVER_BENCHMARK_200=BANK_PREFLIGHT_FAILED")

    questions = list(bank.get("questions") or [])
    selected = [
        row for index, row in enumerate(questions, 1)
        if index >= max(1, args.start_index)
    ]
    if args.max_questions > 0:
        selected = selected[: args.max_questions]

    records: List[Dict[str, Any]] = []
    completed_ids = set()
    if args.resume and checkpoint_path.is_file():
        checkpoint = load_json(checkpoint_path)
        if checkpoint.get("schema_version") != SCHEMA_VERSION:
            print(
                f"INCOMPATIBLE_CHECKPOINT_IGNORED path={checkpoint_path} "
                f"found_schema={checkpoint.get('schema_version')} expected_schema={SCHEMA_VERSION}",
                flush=True,
            )
        else:
            previous = checkpoint.get("records")
            if isinstance(previous, list):
                records = [dict(row) for row in previous if isinstance(row, Mapping)]
                completed_ids = {str(row.get("question_id") or "") for row in records}
                print(
                    f"RESUME checkpoint={checkpoint_path} completed={len(completed_ids)}/200",
                    flush=True,
                )

    if not args.resume and jsonl_path.exists():
        jsonl_path.unlink()

    started_at_epoch = time.time()
    total = int(bank.get("question_count") or len(questions))
    url = args.base_url.rstrip("/") + "/api/trace-net/ask"

    tags_status, tags = get_json(args.gemma_tags_url, min(30.0, args.gemma_timeout_seconds))
    models = tags.get("models") if isinstance(tags, Mapping) else []
    model_names = {
        str(row.get("name") or row.get("model"))
        for row in models if isinstance(row, Mapping)
    } if isinstance(models, list) else set()
    if tags_status != 200 or args.gemma_model not in model_names:
        raise SystemExit(
            f"GEMMA_EVERY_QUESTION_PREFLIGHT_FAILED status={tags_status} "
            f"required_model={args.gemma_model} available={sorted(model_names)}"
        )
    print(
        f"GEMMA_EVERY_QUESTION_PREFLIGHT=PASS model={args.gemma_model} "
        f"url={args.gemma_url}",
        flush=True,
    )

    try:
        for bank_index, raw in enumerate(questions, 1):
            question_id = str(raw.get("question_id") or "")
            if question_id in completed_ids:
                continue
            if raw not in selected:
                continue

            expected_route = str(raw.get("expected_route") or "")
            question = str(raw.get("question") or "")
            print(
                f"[{bank_index:03d}/{total}] START "
                f"id={question_id} expected={expected_route} "
                f"question={compact(question, 140)}",
                flush=True,
            )

            total_started = time.time()
            trace_started = time.time()
            status_code, result = post_json(
                url,
                args.api_key,
                {
                    "query": question,
                    "messages": [{"role": "user", "content": question}],
                    "temperature": 0,
                    "stream": False,
                },
                args.timeout_seconds,
            )
            trace_elapsed = round(time.time() - trace_started, 3)
            safe_answer = str(result.get("content") or "").strip()
            actual_route = str(result.get("route") or "")
            print(
                f"[{bank_index:03d}/{total}] TRACE_NET_DONE "
                f"route={actual_route or 'NONE'} elapsed={trace_elapsed:.3f}s "
                f"writer={result.get('writer_mode') or 'NONE'}",
                flush=True,
            )
            print(
                f"[{bank_index:03d}/{total}] GEMMA_START model={args.gemma_model}",
                flush=True,
            )
            gemma = call_gemma_every_question(
                gemma_url=args.gemma_url,
                gemma_model=args.gemma_model,
                gemma_timeout=args.gemma_timeout_seconds,
                question=question,
                expected_route=expected_route,
                result=result,
                safe_answer=safe_answer,
            )
            gemma_evaluation = evaluate_gemma_every_question(
                question, expected_route, result, safe_answer, gemma
            )
            gemma_pass = bool(gemma_evaluation["passed"])
            print(
                f"[{bank_index:03d}/{total}] GEMMA_DONE "
                f"status={gemma.get('http_status_code')} "
                f"elapsed={float(gemma.get('elapsed_seconds') or 0.0):.3f}s "
                f"accepted={str(gemma_pass).lower()}",
                flush=True,
            )

            answer = str(gemma.get("answer") or "").strip() if gemma_pass else safe_answer
            production_followups = extract_follow_up_questions(result, safe_answer)
            gemma_followups = gemma.get("follow_up_questions")
            followups = (
                unique_strings(gemma_followups)
                if gemma_pass and isinstance(gemma_followups, list)
                else production_followups
            )
            elapsed = round(time.time() - total_started, 3)
            counts = evidence_counts(result)
            repairs = crag_repairs(result)
            critic = result.get("self_rag_critic")
            if not isinstance(critic, Mapping):
                critic = {}
            safety = evaluate_safety(result, answer)
            answer_quality = evaluate_answer_quality(
                question, expected_route, result, answer, followups
            )

            route_pass = actual_route == expected_route
            response_pass = status_code == 200 and bool(safe_answer)
            safety_pass = bool(safety["passed"])
            semantic_pass = bool(answer_quality["passed"])
            answer_pass = response_pass and semantic_pass and gemma_pass
            passed = route_pass and answer_pass and safety_pass

            record: Dict[str, Any] = {
                "question_index": bank_index,
                "question_id": question_id,
                "suite": raw.get("suite"),
                "legacy_family": raw.get("legacy_family"),
                "expected_route": expected_route,
                "actual_route": actual_route,
                "route_pass": route_pass,
                "question": question,
                "trace_net_safe_answer": safe_answer,
                "answer": answer,
                "follow_up_questions": followups,
                "production_follow_up_questions": production_followups,
                "benchmark_gemma_answer": gemma.get("answer"),
                "benchmark_gemma_follow_up_questions": gemma.get("follow_up_questions"),
                "benchmark_gemma_review": gemma.get("review"),
                "benchmark_gemma_called": True,
                "benchmark_gemma_model_requested": gemma.get("model_requested"),
                "benchmark_gemma_model_returned": gemma.get("model_returned"),
                "benchmark_gemma_http_status_code": gemma.get("http_status_code"),
                "benchmark_gemma_elapsed_seconds": gemma.get("elapsed_seconds"),
                "benchmark_gemma_evaluation": gemma_evaluation,
                "benchmark_gemma_pass": gemma_pass,
                "benchmark_gemma_fallback_used": not gemma_pass,
                "http_status_code": status_code,
                "trace_net_elapsed_seconds": trace_elapsed,
                "elapsed_seconds": elapsed,
                "answer_character_count": len(answer),
                "follow_up_question_count": len(followups),
                "quality_status": result.get("quality_status"),
                "writer_mode": result.get("writer_mode"),
                "gemma_status": result.get("gemma_status"),
                "post_answer_validation": result.get("post_answer_validation"),
                "critic_quality_status": critic.get("quality_status"),
                "self_rag_critic": dict(critic),
                "crag_repair_count": len(repairs),
                "crag_repair_attempts": repairs,
                "citation_count": result.get("citation_count"),
                "evidence_counts": counts,
                "retrieval_tunnels_used": retrieval_tunnels(result),
                "safety_evaluation": safety,
                "answer_quality_evaluation": answer_quality,
                "semantic_answer_pass": semantic_pass,
                "response_pass": response_pass,
                "answer_permission": result.get("answer_permission"),
                "final_answer_allowed": result.get("final_answer_allowed"),
                "can_answer_directly": result.get("can_answer_directly"),
                "can_prove_claims": result.get("can_prove_claims"),
                "source_truth_mutation_allowed": result.get("source_truth_mutation_allowed"),
                "route_pass": route_pass,
                "answer_pass": answer_pass,
                "safety_pass": safety_pass,
                "passed": passed,
                "error": result.get("error"),
            }
            records.append(record)
            append_jsonl(jsonl_path, record)

            checkpoint_report = build_report(
                records,
                bank,
                preflight,
                base_url=args.base_url,
                output_path=output_path,
                jsonl_path=jsonl_path,
                started_at_epoch=started_at_epoch,
                status="RUNNING",
            )
            write_json_atomic(checkpoint_path, checkpoint_report)

            label = "PASS" if passed else "FAIL"
            print(
                f"[{bank_index:03d}/{total}] {label} "
                f"route={actual_route or 'NONE'} "
                f"elapsed={elapsed:.3f}s "
                f"answer_chars={len(answer)} "
                f"followups={len(followups)} "
                f"citations={result.get('citation_count') or 0} "
                f"repairs={len(repairs)} "
                f"production_writer={result.get('writer_mode') or 'NONE'} "
                f"benchmark_gemma={args.gemma_model} "
                f"gemma_elapsed={float(gemma.get('elapsed_seconds') or 0.0):.3f}s",
                flush=True,
            )
            if not passed:
                reasons = []
                if not route_pass:
                    reasons.append(f"route expected={expected_route} actual={actual_route}")
                if not response_pass:
                    reasons.append(f"http={status_code} empty_answer={not bool(answer)}")
                if not semantic_pass:
                    reasons.extend(answer_quality.get("failures") or [])
                if not gemma_pass:
                    reasons.extend(gemma_evaluation.get("failures") or [])
                reasons.extend(safety.get("failures") or [])
                print(
                    f"[{bank_index:03d}/{total}] FAILURE_DETAILS "
                    + "; ".join(reasons),
                    flush=True,
                )

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    except KeyboardInterrupt:
        report = build_report(
            records,
            bank,
            preflight,
            base_url=args.base_url,
            output_path=output_path,
            jsonl_path=jsonl_path,
            started_at_epoch=started_at_epoch,
            status="INTERRUPTED",
        )
        write_json_atomic(checkpoint_path, report)
        print("", flush=True)
        print(f"BENCHMARK_INTERRUPTED completed={len(records)}/200", flush=True)
        print(f"CHECKPOINT_JSON={checkpoint_path}", flush=True)
        return 130

    complete = len(records) == 200
    status = "COMPLETE" if complete else "PARTIAL_COMPLETE"
    report = build_report(
        records,
        bank,
        preflight,
        base_url=args.base_url,
        output_path=output_path,
        jsonl_path=jsonl_path,
        started_at_epoch=started_at_epoch,
        status=status,
    )
    write_json_atomic(output_path, report)
    write_json_atomic(checkpoint_path, report)

    summary = report["summary"]
    print("", flush=True)
    print("=" * 72, flush=True)
    print("TRACE-NET H30 SERVER BENCHMARK 200 COMPLETE", flush=True)
    print("=" * 72, flush=True)
    print(f"completed={summary['question_count_completed']}/200", flush=True)
    print(f"pass_count={summary['pass_count']}", flush=True)
    print(f"failure_count={summary['failure_count']}", flush=True)
    print(f"routes_covered={len(summary['routes_covered'])}/19", flush=True)
    print(f"gemma_every_question={summary['gemma_every_question_count']}/200", flush=True)
    print(f"gemma_every_question_pass={summary['gemma_every_question_pass_count']}/200", flush=True)
    print(f"quality_status={summary['quality_status']}", flush=True)
    print(f"BENCHMARK_JSON={output_path}", flush=True)
    print(f"BENCHMARK_JSONL={jsonl_path}", flush=True)
    print(f"CHECKPOINT_JSON={checkpoint_path}", flush=True)

    if summary["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_H30_SERVER_BENCHMARK_200=FAIL")
    print("TRACE_NET_H30_SERVER_BENCHMARK_200=PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
