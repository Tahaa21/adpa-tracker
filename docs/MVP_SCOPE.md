# MVP Scope

## Product goal

AD Security Remediation Tracker sits between assessment and risk reduction:

```
Security Assessment → Risk Prioritization → Remediation → Validation → Risk Reduction
```

It answers: **what should we fix first, who owns it, has it been fixed, and can we
show that risk was reduced?** It is not an attack-path graphing tool and does not
replace BloodHound.

## In scope for this MVP

- Pentera CSV assessment import (tolerant column mapping, per-row error handling).
- Normalization of raw Pentera findings into internal categories/types.
- Deterministic fingerprinting so the same logical issue is recognized across
  repeated assessments (trend analysis).
- Explainable risk scoring (0-100) and P1/P2/P3 priority banding.
- Findings table with search + filters (priority, status, category, severity, owner).
- Finding detail view: risk explanation, assessment history, remediation notes,
  validation records.
- Remediation workflow: owner assignment, status transitions, notes.
- Validation workflow: manually recorded evidence/result, separate from "remediated".
- Dashboard: top metrics, remediation funnel, risk distribution, category
  distribution, assessment-over-assessment comparison (new/recurring/resolved,
  risk reduction %).
- Sanitized sample Pentera-like CSV data (two assessments) for demo purposes.
- Backend tests for parsing, normalization, fingerprinting, risk scoring, and
  repeated-assessment behavior.

## Explicitly out of scope (for now)

Do **not** build in this MVP:

- Neo4j / attack-path graphing / BloodHound ingestion
- PingCastle, Purple Knight, Defender for Identity ingestion
- Automatic PowerShell remediation or validation
- Any AD/LDAP connection, real credentials, or remote agents
- Enterprise SSO, complex RBAC
- Jira / ServiceNow integration
- AI/LLM-generated remediation suggestions
- Kubernetes or cloud deployment infrastructure

These may be added after the Pentera MVP is proven end-to-end.

## Definition of done

The MVP is complete when this flow works, live, against the running app:

1. Open dashboard.
2. Upload a Pentera CSV assessment.
3. See normalized findings with P1/P2/P3 priorities.
4. Open a P1 finding, assign an owner/team, move to `IN_REMEDIATION`, add a note.
5. Move to `READY_FOR_VALIDATION`, add validation evidence/result, mark `VALIDATED`.
6. Import a second Pentera assessment.
7. Dashboard shows new/recurring/resolved findings and a measurable risk reduction
   between the two assessments.

Compiling and rendering a page is not "done" — the workflow above must actually work.

## Simplification rules

If any feature threatens completion of the workflow above, cut it down:
- Owner/team is a flat list, not an identity/RBAC system.
- Validation is manual data entry, never remote execution.
- Risk scoring is a small set of additive rules, not a statistical model.
- One file at a time upload, CSV only, size-limited.
