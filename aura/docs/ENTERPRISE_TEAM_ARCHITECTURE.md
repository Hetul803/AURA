# Enterprise and Team Architecture

Aegisure starts personal, but the platform must support company and team deployments without mixing ownership boundaries.

## Identity Model

Each Aegisure context belongs to an identity:

- Personal Aegisure: user-owned memory, preferences, workflows, and policy.
- Company Aegisure: organization-owned memory, workflow agents, audit requirements, and policy.
- Team Aegisure: scoped company identity for a team or department.
- Collaborative Aegisure: permissioned coordination between identities.

Identities have separate memory scopes and policy scopes. The backend exposes this through identity records and boundary policies.

## Boundary Policies

Boundary checks answer:

- Source identity.
- Target identity.
- Data class.
- Action.
- Decision.
- Reason.

Decisions:

- `allow`
- `deny`
- `require_approval`

Default posture is conservative: cross-identity transfers require approval unless an explicit policy allows or denies them.

## Non-Negotiable Rules

- Company confidential data must not enter personal memory by default.
- Personal private data must not enter company memory without explicit approval.
- Company policy can restrict actions inside company context.
- Audit logs are required for company-controlled actions.
- Team workflows must respect role-based access.

## Future Enterprise Runtime

Enterprise Aegisure should add:

- Tenant isolation.
- RBAC and group mapping.
- Admin policy configuration.
- Company audit export.
- Company memory search.
- Team workflow agents.
- Legal/compliance retention.
- Branded assistant identity.

## Personal + Company Coordination

Personal Aegisure can know that a work task exists without ingesting confidential details. For example:

```text
You have a work meeting at 2 PM.
```

or:

```text
You were assigned a coding task. Do you want me to open your work Aegisure?
```

The handoff payload must be explicit and policy-checked.
