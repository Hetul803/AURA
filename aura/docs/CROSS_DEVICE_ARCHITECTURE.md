# Cross-Device Architecture

AURA starts on desktop, but desktop is only the first surface. Phone, home, car, wearable, and enterprise deployments must plug into the same platform primitives: identity, context, tools, policy, approvals, memory, audit, cost, workflows, and run timelines.

## Core Contract

Every device adapter must describe:

- Context sources it can provide.
- Input methods it supports.
- Output methods it supports.
- Actions it can execute.
- Actions it must refuse.
- Approval capabilities.
- Policy constraints.
- Memory boundary rules.
- Audit requirements.

The backend already exposes adapter metadata through `/devices`. Planned adapters include phone, home, car, wearable/ambient, and enterprise surfaces.

## Handoff Primitive

Cross-device behavior should use handoffs rather than hidden state transfer.

A handoff includes:

- Source device.
- Target device.
- Optional run id.
- Payload.
- Status.
- Whether approval is required.
- Audit/timeline correlation.

Examples:

- Desktop to phone: “Approve this paste/send from your phone.”
- Phone to desktop: “Continue this coding task on the desktop.”
- Car to phone: “Save this message draft for later approval.”
- Enterprise workspace to personal desktop: “A work task exists, but company data remains in company memory.”

## Memory Boundaries

Personal, work, company, household, and car contexts must not be blindly merged.

- Personal memory stays personal.
- Company memory stays company-owned.
- Household memory must support user-specific boundaries.
- Car mode should avoid durable capture of sensitive passenger context unless permitted.
- Handoffs carry explicit payloads and policy metadata.

## Approval Surfaces

Approvals must be device-independent.

- Desktop overlay approval is the first surface.
- Phone quick approval is next.
- Wearable approval can be lightweight.
- Car approval must be safety-limited and mostly defer complex actions.
- Enterprise approval may require role-based policy.

## Phone First Prototype Direction

The first mobile companion should support:

- Read current run status.
- Receive approval cards.
- Approve/reject/edit where safe.
- Send a text/voice command to desktop.
- Receive handoff payloads from desktop.
- View local-first memory summaries only when sync is explicitly enabled.

## Car and Home Constraints

AURA Car:

- Voice-first.
- Minimal visual complexity.
- No long-form interaction while driving.
- Defer complex actions to phone/desktop.
- Message sending still requires explicit confirmation.

AURA Home:

- Household routines.
- Smart home actions.
- Family/member boundaries.
- Security-sensitive actions require confirmation.

## Enterprise Constraints

Enterprise AURA uses the same handoff shape but adds:

- RBAC.
- Admin policy.
- Tenant isolation.
- Company audit requirements.
- Separate company-owned memory.
- Permissioned collaboration with personal AURA.
