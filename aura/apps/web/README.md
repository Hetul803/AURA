# Aegisure Web

Marketing, download, legal, and private-alpha license scaffolding site.

Run:
```bash
pnpm --filter aegisure-web dev
```

Routes:

- `/` product landing page
- `/downloads` download section
- `/privacy`
- `/terms`
- `/security`
- `/api/releases`
- `/api/download?os=mac`
- `/api/checkout/create`
- `/api/stripe/webhook`
- `/api/license/issue`
- `/api/devices/activate`
- `/api/devices/revoke`
- `/api/crash-reports`

License issuance requires `AEGISURE_VENDOR_PRIVATE_KEY` on the website server. Never ship the vendor private key inside the desktop app.

Checkout requires:

```bash
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
PUBLIC_BASE_URL=https://your-domain.com
AEGISURE_VENDOR_PRIVATE_KEY=...
AEGISURE_VENDOR_PUBLIC_KEY=...
AEGISURE_ADMIN_TOKEN=...
```

The private-alpha store defaults to `var/private-alpha-store.json`. For real hosting, set `AEGISURE_WEB_DB_PATH` to a persistent disk path or replace `AlphaStore` with Postgres before scaling beyond a small alpha.
