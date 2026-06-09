# TRACE-Net Ask Hybrid Flag v1

Status: **ASK_RAN**
Quality status: **PASS**
Retrieval mode: `hybrid-simulate`
Query: `Which pages discuss manual revision history?`

> Hybrid retrieval is running in simulation mode only. This report is a retrieval preview, not a final answer.

## Safety contract

- Vector and page-profile hits cannot answer directly.
- Vector and page-profile hits cannot prove claims by themselves.
- Every future answer must resolve through source evidence, citation, and trust authority.
- This step does not mutate source truth, trust tiers, citations, Postgres, or Qdrant.

## Summary
- **regression_quality_status**: PASS
- **hybrid_quality_status**: PASS
- **ranked_group_count**: 8
- **safe_group_count**: 8
- **unsafe_group_count**: 0
- **direct_answer_allowed_group_count**: 0
- **claim_proof_allowed_group_count**: 0
- **source_truth_mutation_allowed_group_count**: 0
- **candidate_collection_count**: 1476
- **page_profile_collection_count**: 509
- **embedding_mode**: ollama
- **embedding_model_name**: bge-m3:latest
- **embedding_dim**: 1024

## Top retrieval groups
- Rank 1: page `t_p_120_1176_p000013`, score `1.690117`, candidate hits `1`, page hits `1`, answer allowed `False`
- Rank 2: page `t_p_120_1176_p000001`, score `1.637078`, candidate hits `1`, page hits `1`, answer allowed `False`
- Rank 3: page `t_p_120_1176_p000008`, score `1.631871`, candidate hits `1`, page hits `1`, answer allowed `False`
- Rank 4: page `t_p_120_1176_p000005`, score `1.615604`, candidate hits `1`, page hits `1`, answer allowed `False`
- Rank 5: page `t_p_120_1176_p000007`, score `0.714176`, candidate hits `1`, page hits `0`, answer allowed `False`
- Rank 6: page `t_p_120_1176_p000010`, score `0.694642`, candidate hits `1`, page hits `0`, answer allowed `False`
- Rank 7: page `t_p_120_1176_p000048`, score `0.687948`, candidate hits `0`, page hits `1`, answer allowed `False`
- Rank 8: page `t_p_120_1176_p000028`, score `0.687692`, candidate hits `0`, page hits `1`, answer allowed `False`
