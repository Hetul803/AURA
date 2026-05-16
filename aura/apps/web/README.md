# AURA Web

Marketing, download, legal, and private-alpha license scaffolding site.

Run:
```bash
pnpm --filter aura-web dev
```

Routes:

- `/` product landing page
- `/downloads` download section
- `/privacy`
- `/terms`
- `/security`
- `/api/releases`
- `/api/download?os=mac`
- `/api/license/issue`

License issuance requires `AURA_VENDOR_PRIVATE_KEY` on the website server. Never ship the vendor private key inside the desktop app.
