# Aegisure Deploy Guide

## Supabase

Use Supabase for hosted Postgres, pgvector, and GitHub Auth.

1. Create a Supabase project.
2. Enable GitHub as an Auth provider.
3. Run the backend Alembic migration against Supabase:

```bash
cd apps/backend
DATABASE_URL="postgresql+psycopg://..." alembic upgrade head
```

The migration creates `vector` and enables Row-Level Security on workspace-scoped tables.

## Railway

Deploy the FastAPI backend and future worker on Railway.

Required env:

```bash
AEGISURE_API_TOKEN=
DATABASE_URL=
SUPABASE_JWT_SECRET=
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=
GITHUB_WEBHOOK_SECRET=
AEGISURE_ANTHROPIC_API_KEY=
AEGISURE_OPENAI_API_KEY=
AEGISURE_PROVIDED_DAILY_CAP_USD=0.25
```

Start command:

```bash
cd apps/backend && uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

## Vercel

Deploy `apps/web`.

Required env:

```bash
AEGISURE_BACKEND_URL=https://your-railway-backend
AEGISURE_API_TOKEN=
AEGISURE_WORKSPACE_ID=local
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_POSTHOG_KEY=
NEXT_PUBLIC_POSTHOG_HOST=
```

## PyPI

Do not upload from CI yet. Founder runs:

```bash
cd apps/backend
python -m pip install -U build twine
python -m build
twine check dist/*
twine upload dist/*
```

Verify local package first:

```bash
cd apps/backend
pip install -e .
aegisure --help
```
