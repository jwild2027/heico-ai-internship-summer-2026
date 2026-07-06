# TRACE-Net H36B Validator Negation/Regrade Repair

H36B repairs the H36 complex task validator after the H35 custom task run exposed two grading issues:

- Safe boundary answers such as "Does this prove interchangeability? No" were still being flagged as unsafe.
- Old H35 source unsupported counts were carried forward even when H36 recognized the answer text as safe negated boundary language.

H36B keeps the validator artifact-only. It does not call an LLM and does not perform DB/vector/search writes.
