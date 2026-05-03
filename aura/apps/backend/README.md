# Backend
FastAPI deterministic runtime with planner/executor/observer/safety, sqlite profile memory, macros, snapshots, retention.

Run:
```bash
uvicorn src.api.main:app --reload --port 8000
```

Install for local development:
```bash
pip install -e .
```

Focused hardening tests:
```bash
python -m compileall -q src
pytest -q tests/test_safety.py tests/test_memory_engine.py tests/test_workflow_engine.py tests/test_guardian.py
```

Important endpoints:
- `/command`: submit desktop command.
- `/runs/{run_id}` and `/runs/{run_id}/events`: inspect active run state.
- `/runs/{run_id}/approve`, `/retry`, `/reject`, `/resume`: approval flow.
- `/guardian/status` and `/guardian/events`: AURA Guardian status and trust events.
- `/memory/items`, `/memory/search`, `/memory/compact`: typed memory.
- `/workflows`, `/workflows/{workflow_id}/run`: workflow save/replay.
- `/audit`: redacted audit log.
