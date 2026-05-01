# Home and Car Future Adapters

Home and car support must be safety-first. These adapters are contracts now, not live device integrations.

## AURA Home

Initial future capabilities:

- Household reminders.
- Household routines.
- Smart home state summaries.
- User-specific and family memory boundaries.
- Security-sensitive action approvals.

Hard rules:

- Door locks, alarms, security systems, cameras, and appliance controls require approval.
- Household context must respect each person boundary.
- Guest or family data should not silently enter personal memory.

## AURA Car

Initial future capabilities:

- Voice-first commands.
- Calendar and navigation summaries.
- Message drafts with explicit approval.
- Defer complex work to phone or desktop.

Hard rules:

- No long-form reading or complex visual interaction while driving.
- No code editing while driving.
- Message sending requires explicit confirmation.
- Complex workflows should create a handoff to phone or desktop.

## Adapter Contract

The backend exposes ambient adapter contracts and safety classifiers. Later integrations should plug into these checks before controlling any real home/car device.
