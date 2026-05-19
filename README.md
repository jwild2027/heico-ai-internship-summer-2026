# heico-ai-internship-summer-2026
Ai internship project for heico

Software installed
- Docker(https://docs.docker.com/desktop/setup/install/windows-install/)
- Ollama (https://ollama.com/download)
- Gemma for Ollama (https://ollama.com/library/gemma3:4b)
- Git bash (https://git-scm.com/install/windows). Git Desktop (https://desktop.github.com/download/)
- chroma DB use pip install chromadb
- Streamlit (https://streamlit.io/)
- LlamaIndex (https://cloud.llamaindex.ai/project/06aa1528-ed1d-43b6-bb66-cbbdb78c7b7b)


guides:
https://medium.com/@jonigl/using-ollama-with-python-a-simple-guide-0752369e1e55
https://github.com/ollama/ollama-python
https://developers.openai.com/cookbook
https://www.pinecone.io/learn/vector-database/


Reusable prompts:
# Reusable AI Operations Prompt Library (v1.0)

## Overview

This prompt library contains reusable templates for operational AI workflows including:

* Helpdesk triage
* Incident and log summarization
* Policy explanation
* Escalation routing
* Customer communication
* Root cause analysis
* SLA monitoring

Each prompt is version-controlled using:

* Prompt ID
* Version number
* Last updated date
* Change log
* Input/output specification

---

# Prompt Governance Standard

## Prompt Metadata Template

```yaml
prompt_id: HD-001
name: Helpdesk Ticket Classifier
version: 1.0.0
owner: Operations Team
last_updated: 2026-05-19
status: production
model_compatibility:
  - GPT-5.5
  - GPT-4.1
change_log:
  - version: 1.0.0
    date: 2026-05-19
    changes: Initial release
```

## Versioning Rules

| Change Type | Version Example | Usage                                  |
| ----------- | --------------- | -------------------------------------- |
| Major       | 2.0.0           | Structural changes or behavior changes |
| Minor       | 1.1.0           | Added capabilities or new fields       |
| Patch       | 1.0.1           | Wording fixes or formatting updates    |

---

# 1. Helpdesk Triage Prompts

## Prompt HD-001 — Helpdesk Ticket Classifier

```yaml
prompt_id: HD-001
version: 1.0.0
```

### Prompt

```text
You are a helpdesk triage assistant.

Analyze the ticket and classify:
1. Priority (P1–P4)
2. Category
3. Likely root cause
4. Required team
5. Suggested next action
6. Customer sentiment

Rules:
- P1 = complete outage or security risk
- P2 = major functionality impaired
- P3 = partial issue or workaround exists
- P4 = informational or cosmetic

Return JSON only.

Ticket:
{{ticket_text}}
```

### Expected Output

```json
{
  "priority": "P2",
  "category": "Authentication",
  "root_cause": "Expired SSO certificate",
  "assigned_team": "IAM",
  "next_action": "Rotate certificate and validate login flow",
  "customer_sentiment": "Frustrated"
}
```

---

## Prompt HD-002 — Duplicate Ticket Detector

```yaml
prompt_id: HD-002
version: 1.0.0
```

### Prompt

```text
Determine whether the incoming ticket matches an existing incident.

Compare:
- Symptoms
- Error messages
- Service names
- Time range
- Affected users

Return:
- duplicate_match: true/false
- confidence_score: 0-100
- matching_incident
- reasoning

Incoming ticket:
{{incoming_ticket}}

Known incidents:
{{known_incidents}}
```

---

## Prompt HD-003 — Escalation Recommendation Engine

```yaml
prompt_id: HD-003
version: 1.0.0
```

### Prompt

```text
Review the ticket and determine whether escalation is required.

Escalate if:
- SLA breach risk exists
- Security implications exist
- Multiple customers affected
- Revenue impact possible
- No workaround exists

Provide:
- escalation_required
- escalation_team
- escalation_reason
- urgency_level
- recommended_owner

Ticket:
{{ticket}}
```

---

## Prompt HD-004 — Customer Reply Draft Generator

```yaml
prompt_id: HD-004
version: 1.0.0
```

### Prompt

```text
Draft a professional customer support response.

Tone:
- Empathetic
- Clear
- Non-technical unless requested

Include:
- Acknowledgement
- Current status
- ETA if available
- Workaround if available
- Next update timing

Ticket:
{{ticket}}
Internal notes:
{{internal_notes}}
```

---

## Prompt HD-005 — SLA Risk Predictor

```yaml
prompt_id: HD-005
version: 1.0.0
```

### Prompt

```text
Analyze the ticket queue and identify SLA breach risks.

For each ticket provide:
- risk_level
- time_remaining
- blockers
- recommended_action
- staffing recommendation

Queue:
{{ticket_queue}}
```

---

# 2. Log and Incident Summary Prompts

## Prompt LG-001 — Application Log Summarizer

```yaml
prompt_id: LG-001
version: 1.0.0
```

### Prompt

```text
Summarize the following application logs.

Identify:
- Primary failure
- Timeline of events
- Error frequency
- Affected systems
- Most likely root cause
- Immediate remediation steps

Keep summary under 250 words.

Logs:
{{logs}}
```

---

## Prompt LG-002 — Incident Timeline Generator

```yaml
prompt_id: LG-002
version: 1.0.0
```

### Prompt

```text
Create a chronological incident timeline.

Extract:
- Timestamp
- Event
- Severity
- System impacted
- Action taken

Format as a markdown table.

Incident data:
{{incident_data}}
```

---

## Prompt LG-003 — Root Cause Analysis Assistant

```yaml
prompt_id: LG-003
version: 1.0.0
```

### Prompt

```text
Perform a structured root cause analysis.

Provide:
1. Symptoms
2. Trigger event
3. Root cause
4. Contributing factors
5. Detection gaps
6. Preventive actions
7. Long-term fixes

Evidence:
{{evidence}}
```

---

## Prompt LG-004 — Security Event Summary

```yaml
prompt_id: LG-004
version: 1.0.0
```

### Prompt

```text
Review the security logs and summarize:
- Threat type
- Indicators of compromise
- Affected assets
- Severity level
- Recommended containment actions
- Required notifications

Security logs:
{{security_logs}}
```

---

## Prompt LG-005 — Change Failure Analysis

```yaml
prompt_id: LG-005
version: 1.0.0
```

### Prompt

```text
Analyze whether a recent deployment caused the incident.

Correlate:
- Deployment timestamps
- Error increases
- Infrastructure changes
- Service degradation

Provide:
- probable_change_cause
- confidence
- rollback_recommendation
- impacted_components

Data:
{{deployment_and_logs}}
```

---

# 3. Policy Explainer Prompts

## Prompt PL-001 — Internal Policy Simplifier

```yaml
prompt_id: PL-001
version: 1.0.0
```

### Prompt

```text
Explain the following policy in simple business language.

Requirements:
- Avoid legal jargon
- Use bullet points
- Include practical examples
- Explain who is affected
- Explain required actions

Policy:
{{policy_text}}
```

---

## Prompt PL-002 — Compliance Gap Analyzer

```yaml
prompt_id: PL-002
version: 1.0.0
```

### Prompt

```text
Compare current operational practices against the policy.

Identify:
- Non-compliant areas
- Risk severity
- Missing controls
- Required remediation
- Recommended owner

Policy:
{{policy}}

Operational process:
{{process}}
```

---

## Prompt PL-003 — Access Control Policy Advisor

```yaml
prompt_id: PL-003
version: 1.0.0
```

### Prompt

```text
Review the requested access and determine policy alignment.

Provide:
- approval_recommendation
- least_privilege_assessment
- segregation_of_duties_risk
- required_approvals
- compensating_controls

Request:
{{access_request}}
Policy:
{{policy}}
```

---

## Prompt PL-004 — Data Retention Explainer

```yaml
prompt_id: PL-004
version: 1.0.0
```

### Prompt

```text
Explain the data retention requirements.

Include:
- Required retention period
- Data categories impacted
- Disposal requirements
- Legal considerations
- Examples of compliant handling

Policy:
{{retention_policy}}
```

---

## Prompt PL-005 — Executive Policy Summary

```yaml
prompt_id: PL-005
version: 1.0.0
```

### Prompt

```text
Summarize the policy for executive leadership.

Keep under 300 words.

Include:
- Business impact
- Key risks
- Required investments
- Compliance implications
- Recommended decisions

Policy:
{{policy_document}}
```

---

# 4. Operations and Monitoring Prompts

## Prompt OP-001 — On-Call Handoff Summary

```yaml
prompt_id: OP-001
version: 1.0.0
```

### Prompt

```text
Generate an on-call handoff summary.

Include:
- Open incidents
- Current mitigations
- Pending actions
- Escalations
- Risks to monitor
- Important timestamps

Operational notes:
{{handoff_notes}}
```

---

## Prompt OP-002 — Monitoring Alert Prioritizer

```yaml
prompt_id: OP-002
version: 1.0.0
```

### Prompt

```text
Review the alerts and prioritize operational response.

For each alert provide:
- priority
- probable impact
- false positive likelihood
- recommended action
- escalation need

Alerts:
{{alerts}}
```

---

## Prompt OP-003 — Runbook Recommendation Assistant

```yaml
prompt_id: OP-003
version: 1.0.0
```

### Prompt

```text
Based on the incident details, recommend the most relevant runbook.

Provide:
- recommended_runbook
- confidence_score
- required_prerequisites
- estimated_resolution_time
- fallback_actions

Incident:
{{incident}}
Runbooks:
{{runbooks}}
```

---

## Prompt OP-004 — Postmortem Draft Generator

```yaml
prompt_id: OP-004
version: 1.0.0
```

### Prompt

```text
Generate a blameless postmortem draft.

Sections:
- Executive summary
- Customer impact
- Timeline
- Root cause
- Resolution
- Lessons learned
- Action items

Incident data:
{{incident_data}}
```

---

## Prompt OP-005 — Knowledge Base Article Generator

```yaml
prompt_id: OP-005
version: 1.0.0
```

### Prompt

```text
Convert the incident resolution into a knowledge base article.

Structure:
- Problem
- Symptoms
- Cause
- Resolution
- Verification steps
- Prevention guidance

Audience:
{{audience}}

Incident details:
{{incident_details}}
```

---

# Recommended Repository Structure

```text
prompt-library/
├── helpdesk/
│   ├── HD-001.yaml
│   ├── HD-002.yaml
│   └── ...
├── logs/
├── policy/
├── operations/
├── tests/
├── changelog/
└── README.md
```

---

# Recommended Git Workflow

## Branch Naming

```text
feature/prompt-hd-001-update
fix/log-summary-format
experiment/new-policy-prompts
```

## Pull Request Checklist

* Prompt tested with sample inputs
* Output formatting validated
* Hallucination risk reviewed
* Security/privacy reviewed
* Prompt metadata updated
* Changelog updated

---

# Prompt Testing Framework

## Suggested Evaluation Metrics

| Metric                | Description                              |
| --------------------- | ---------------------------------------- |
| Accuracy              | Correctness of classification or summary |
| Consistency           | Stable outputs across similar inputs     |
| Latency               | Response time                            |
| Hallucination Rate    | Unsupported claims                       |
| Escalation Precision  | Correct escalation recommendations       |
| Formatting Compliance | Structured output correctness            |

---

# Suggested CI/CD Validation

Automate:

* JSON schema validation
* Prompt linting
* Output structure tests
* Regression comparison
* Red-team safety checks
* Sensitive data leakage tests

---

# Example Prompt File Format

```yaml
prompt_id: LG-001
name: Application Log Summarizer
version: 1.2.0
owner: SRE Team
status: production
last_updated: 2026-05-19

input_schema:
  logs: string

output_schema:
  summary: string
  root_cause: string
  remediation: array

prompt: |
  Summarize the following application logs.
  ...
```

---

# Release Notes

## v1.0.0

* Initial release
* Added 20 reusable operational prompts
* Added governance and versioning model
* Added CI/CD recommendations
