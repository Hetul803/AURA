# Aegisure Known Limitations

Aegisure is ready for serious local private-alpha testing, but it should stay honest.

## Not Active Yet

- True OS-wide ambient Guardian monitoring outside Aegisure-managed actions.
- Browser permission interception for location, camera, microphone, or downloads.
- External app file-access monitoring for apps such as Cursor, Slack, Chrome, or Finder.
- Full Slack/Victor enterprise-agent mediation.
- Always-listening wake word.
- Production checkout, device activation, revocation server, and hosted account system.
- Apple Developer ID signing and notarization unless credentials are configured.
- Auto-update.
- Production crash/error reporting.

## Active Today

- Aegisure-managed shell/file/paste/workflow/model/import/export safety.
- Guardian event ledger, policy mode, and trust-rule configuration.
- Local encrypted memory items with inbox, CRUD, search, health, usage, provenance, and scoped identity behavior.
- Local Ed25519 identity fingerprint and action ledger.
- Helper workflows for GitHub clone, draft/paste approval, coding jobs, open URL/app, workspace note creation, and work-session prep.
- Overlay/orb route and desktop bridge where Electron supports it.
- Local model detection and honest fallback.

## External Requirements

- macOS permissions must be granted by the user.
- Native speech input depends on packaged helper and macOS speech permission.
- Ollama model pull depends on Ollama being installed/running and model tag availability.
- Code signing/notarization requires Apple Developer ID certificates and app-specific credentials.
