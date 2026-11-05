---
name: minilms-security-audit
description: Coaches step-by-step authorized localhost miniLMS security testing using pytest, Burp Suite, ZAP, conditional sqlmap, fault injection, and evidence logging.
---

# Skill: Security & Reliability Verification

## Scope
Only user's own local miniLMS/lab. First ask Agent to **confirm current project, host/port, authorization and snapshot**. Scope hard gate before scanning. No third-party probing, no public targets. Tests use bounded intensity and fake seed.

## Read
- `docs/agent-kit/05_SECURITY_TEST_MATRIX.md`
- `docs/agent-kit/06_TOOL_RUNBOOK_STEP_BY_STEP.md`
- `docs/agent-kit/08_EVIDENCE_TEMPLATE.md`
- `docs/agent-kit/01_REQUIREMENTS_TRACEABILITY.md`

## Runbook hành vi
1. Inventory routes and auth roles in code; enumerate test matrix with IDs.
2. Give user **one tool procedure at a time**, including buttons to click, test request, expected response, how to interpret, screenshot to save, how to redact.
3. Start `pytest` and local curl smoke test. For Burp: proxy browser -> history -> Repeater -> adjust permitted URL/body -> observe response. For ZAP: passive first, local-only active if appropriate and non-destructive. For sqlmap: skip if no SQL path; otherwise low settings only, no data extraction.
4. Run fake upstream delay to test #6; simulations do not target real provider. Use deterministic clocks for state and expiry.
5. Test role boundaries: Admin/instructor/student cross-course, attempt owner, exported grade scope, seat owner; differentiate authn vs authz.
6. Log ALL actual results to evidence register with command, screenshot path, host, SHA, expected/observed; no fabricated output.
7. Conclude each finding with root cause, patch recommendation, re-test. Never report 'secure' from zero alerts.

## Safety
Do not script uncontrolled DOS, credential sprays, mass scans, exfiltration, shell exploitation, or payloads for remote targets. Constrain max 20 parallel local requests and 60s. Obtain explicit human approval before potentially destructive local scans. Never show raw secrets in transcript or screenshots.
