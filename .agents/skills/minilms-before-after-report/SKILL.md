---
name: minilms-before-after-report
description: Builds evidence-based miniLMS Timeout and Fallback pattern #6 before-versus-after patch demonstration and academic security testing report.
---

# Skill: Before/After Timeout & Fallback Report

## Read
- `docs/agent-kit/04_TIMEOUT_FALLBACK_DESIGN.md`
- `docs/agent-kit/07_REPORT_BEFORE_AFTER_TIMEOUT.md`
- `docs/agent-kit/08_EVIDENCE_TEMPLATE.md`

## Steps
1. Audit current dashboard callpath to identify how upstream slow responses could block normal user requests. If no actual bug, construct a strictly isolated **lab baseline** without timeout solely to demonstrate failure; label as simulated baseline, do not misrepresent original app.
2. Preserve baseline local tag/branch or fake test fixture; do not deploy vulnerable implementation. Write reproduction steps with auth, local fake stats delay, expected slow behavior and actual measured latency.
3. Implement patch with request deadline, upstream timeout, scoped safe fallback/controlled 503, valid cache only with current authorization, bounded execution.
4. Measure same scenario N>=10 before and after; record raw CSV and aggregate median/p95 **from executed runs**. Also test concurrent calls + unauthorized actors.
5. Capture redacted Burp screenshots and unit/integration test output. Pair screenshot/log IDs and corresponding commit SHAs.
6. Draft report using actual data, put TODO/NOT RUN on unexecuted experiments. Explain root cause, exploitability assumptions, reliability impact, security relevance, limitations (staleness, async cancellation, dev server limitations).
7. Ask user to review report text, but do not block test/code work waiting for unnecessary approvals.

## Final test
Ensure another person can reproduce from clean checkout with documented uv commands, fake provider setup, branch/commit refs, seed test account, and environment. Ensure report cites both PDFs accurately, never claims all six patterns were formally selected for grading.
