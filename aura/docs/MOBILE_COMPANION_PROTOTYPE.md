# Mobile Companion Prototype

The mobile companion starts as a lightweight approval and handoff surface for desktop AURA.

## Prototype Capabilities

- Pair a phone with desktop AURA.
- View mobile companion status.
- Receive approval cards.
- Approve or reject handoffs.
- View run summaries.
- Send future command handoffs to desktop.

## Backend-First Contract

The first mobile app should call:

- `POST /mobile/pairing-code`
- `POST /mobile/devices`
- `GET /mobile/status`
- `GET /mobile/inbox`
- `POST /mobile/approval-cards`
- `POST /mobile/handoffs/{handoff_id}/decision`
- `GET /mobile/runs/{run_id}`

## Safety

Mobile approvals must show:

- The action.
- The risk.
- The target app/site when known.
- The proposed payload.
- Approve/reject controls.

Mobile must not become a bypass around desktop safety. It is another approval surface attached to the same run, audit, and handoff records.

## Future App Shape

The first app can be React Native or a small local web app. It should not own memory directly. It should request scoped summaries and approval cards from the desktop/backend instance.
