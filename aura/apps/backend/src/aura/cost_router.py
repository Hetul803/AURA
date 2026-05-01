from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from .models import selected_model_metadata
from .state import db_conn

Purpose = Literal['context', 'planning', 'writing', 'coding', 'browser_user_tool', 'summarization', 'classification']


@dataclass(frozen=True)
class ModelCandidate:
    provider: str
    model: str
    label: str
    privacy: str
    cost_tier: str
    input_cost_per_1k: float
    output_cost_per_1k: float
    available: bool = True
    supports: tuple[str, ...] = ('context', 'planning', 'writing', 'summarization', 'classification')
    notes: str = ''

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data['supports'] = list(self.supports)
        return data


def _now() -> str:
    return datetime.now(UTC).isoformat()


def model_candidates() -> list[dict[str, Any]]:
    selected = selected_model_metadata()
    selected_ollama = selected.get('model') if selected.get('provider') == 'ollama' else 'local-default'
    return [
        ModelCandidate('simple', 'simple', 'Simple deterministic local model', 'local', 'free', 0.0, 0.0, True, notes='Fast deterministic fallback.').to_dict(),
        ModelCandidate('ollama', selected_ollama, f'Ollama local model ({selected_ollama})', 'local', 'free', 0.0, 0.0, bool(selected.get('available', False)) if selected.get('provider') == 'ollama' else False, notes='Preferred for private/simple local reasoning when available.').to_dict(),
        ModelCandidate('openai', 'gpt-5.5', 'OpenAI GPT-5.5 for AURA planning', 'cloud', 'premium', 0.01, 0.03, False, ('context', 'planning', 'writing', 'summarization', 'classification'), 'Configured later with user-controlled cloud policy.').to_dict(),
        ModelCandidate('anthropic', 'claude', 'Claude for AURA reasoning', 'cloud', 'premium', 0.008, 0.024, False, ('context', 'planning', 'writing', 'summarization', 'classification'), 'Configured later with user-controlled cloud policy.').to_dict(),
        ModelCandidate('user_web', 'chatgpt_subscription', 'User-owned ChatGPT web session', 'user_browser', 'subscription', 0.0, 0.0, True, ('writing', 'coding', 'summarization'), 'Uses the user subscription through browser automation; handled as user-tool delegation.').to_dict(),
        ModelCandidate('user_web', 'claude_subscription', 'User-owned Claude web session', 'user_browser', 'subscription', 0.0, 0.0, True, ('writing', 'coding', 'summarization'), 'Uses the user subscription through browser automation; handled as user-tool delegation.').to_dict(),
    ]


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text.split()) + len(text) // 24)


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    candidate = next((c for c in model_candidates() if c['provider'] == provider and c['model'] == model), None)
    if not candidate:
        return {'estimated_cost_usd': 0.0, 'known_pricing': False}
    cost = ((prompt_tokens / 1000) * candidate['input_cost_per_1k']) + ((completion_tokens / 1000) * candidate['output_cost_per_1k'])
    return {'estimated_cost_usd': round(cost, 6), 'known_pricing': True}


def _budget(scope: str = 'personal') -> dict[str, Any]:
    row = db_conn().execute('SELECT * FROM cost_budgets WHERE scope=?', (scope,)).fetchone()
    if row:
        return dict(row)
    return {'scope': scope, 'monthly_limit_usd': None, 'warn_at_usd': None}


def set_budget(scope: str = 'personal', monthly_limit_usd: float | None = None, warn_at_usd: float | None = None) -> dict[str, Any]:
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO cost_budgets(scope, monthly_limit_usd, warn_at_usd, updated_at)
            VALUES(?,?,?,?)
            ON CONFLICT(scope) DO UPDATE SET
              monthly_limit_usd=excluded.monthly_limit_usd,
              warn_at_usd=excluded.warn_at_usd,
              updated_at=excluded.updated_at
            ''',
            (scope, monthly_limit_usd, warn_at_usd, _now()),
        )
    return _budget(scope)


def usage_summary(scope: str | None = None) -> dict[str, Any]:
    rows = db_conn().execute('SELECT * FROM model_usage_events ORDER BY id DESC').fetchall()
    events = [dict(row) for row in rows]
    total = round(sum(float(row.get('estimated_cost_usd') or 0) for row in events), 6)
    saved = round(sum(float(row.get('saved_cost_usd') or 0) for row in events), 6)
    by_provider: dict[str, dict[str, Any]] = {}
    for row in events:
        key = f"{row.get('provider')}:{row.get('model')}"
        entry = by_provider.setdefault(key, {'provider': row.get('provider'), 'model': row.get('model'), 'calls': 0, 'estimated_cost_usd': 0.0})
        entry['calls'] += 1
        entry['estimated_cost_usd'] = round(entry['estimated_cost_usd'] + float(row.get('estimated_cost_usd') or 0), 6)
    budget = _budget(scope or 'personal')
    return {'total_estimated_cost_usd': total, 'estimated_savings_usd': saved, 'by_provider': list(by_provider.values()), 'budget': budget, 'events_count': len(events)}


def _cache_key(purpose: str, prompt: str) -> str:
    return hashlib.sha256(f'{purpose}\n{prompt}'.encode('utf-8')).hexdigest()


def get_cached_response(purpose: str, prompt: str) -> dict[str, Any] | None:
    key = _cache_key(purpose, prompt)
    row = db_conn().execute('SELECT * FROM model_response_cache WHERE cache_key=?', (key,)).fetchone()
    if not row:
        return None
    with db_conn() as conn:
        conn.execute('UPDATE model_response_cache SET hit_count=hit_count+1, updated_at=? WHERE cache_key=?', (_now(), key))
    data = dict(row)
    data['response'] = json.loads(data.pop('response_json') or '{}')
    return data


def put_cached_response(purpose: str, prompt: str, provider: str, model: str, response: dict[str, Any]) -> dict[str, Any]:
    key = _cache_key(purpose, prompt)
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO model_response_cache(cache_key, purpose, provider, model, prompt_hash, response_json, hit_count, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(cache_key) DO UPDATE SET
              response_json=excluded.response_json,
              provider=excluded.provider,
              model=excluded.model,
              updated_at=excluded.updated_at
            ''',
            (key, purpose, provider, model, key, json.dumps(response, sort_keys=True), 0, _now(), _now()),
        )
    return {'cache_key': key, 'cached': True}


def route_model(
    *,
    purpose: Purpose | str,
    prompt: str = '',
    privacy: str = 'normal',
    complexity: str = 'simple',
    allow_cloud: bool = False,
    prefer_user_subscription: bool = False,
) -> dict[str, Any]:
    prompt_tokens = estimate_tokens(prompt)
    completion_tokens = max(64, min(2048, prompt_tokens // 2))
    cache = get_cached_response(purpose, prompt) if prompt else None

    candidates = model_candidates()
    if prefer_user_subscription and purpose in {'writing', 'coding', 'summarization'}:
        chosen = next(c for c in candidates if c['provider'] == 'user_web' and c['model'] == 'chatgpt_subscription')
        reason = 'user_subscription_preferred_for_user_task'
    elif privacy == 'sensitive':
        chosen = next((c for c in candidates if c['provider'] == 'ollama' and c['available']), candidates[0])
        reason = 'sensitive_context_prefers_local_model'
    elif complexity in {'hard', 'expert'} and allow_cloud:
        chosen = next((c for c in candidates if c['provider'] == 'openai' and c['available']), None) or next((c for c in candidates if c['provider'] == 'anthropic' and c['available']), None) or candidates[0]
        reason = 'complex_task_prefers_best_available_cloud_or_fallback'
    else:
        chosen = next((c for c in candidates if c['provider'] == 'ollama' and c['available']), candidates[0])
        reason = 'simple_or_private_task_uses_local_or_free_model'

    cost = estimate_cost(chosen['provider'], chosen['model'], prompt_tokens, completion_tokens)
    premium_baseline = estimate_cost('openai', 'gpt-5.5', prompt_tokens, completion_tokens)['estimated_cost_usd']
    saved = max(0.0, round(premium_baseline - cost['estimated_cost_usd'], 6))
    return {
        'provider': chosen['provider'],
        'model': chosen['model'],
        'label': chosen['label'],
        'purpose': purpose,
        'privacy': privacy,
        'complexity': complexity,
        'route_reason': reason,
        'prompt_tokens_estimate': prompt_tokens,
        'completion_tokens_estimate': completion_tokens,
        'estimated_cost_usd': cost['estimated_cost_usd'],
        'estimated_savings_vs_premium_usd': saved,
        'cache_hit': bool(cache),
        'cached_response': cache['response'] if cache else None,
        'budget': _budget(),
    }


def record_model_usage(
    *,
    run_id: str | None,
    route: dict[str, Any],
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt_tokens = prompt_tokens if prompt_tokens is not None else int(route.get('prompt_tokens_estimate') or 0)
    completion_tokens = completion_tokens if completion_tokens is not None else int(route.get('completion_tokens_estimate') or 0)
    estimated_cost = estimate_cost(route['provider'], route['model'], prompt_tokens, completion_tokens)['estimated_cost_usd']
    saved = float(route.get('estimated_savings_vs_premium_usd') or 0)
    with db_conn() as conn:
        cur = conn.execute(
            '''
            INSERT INTO model_usage_events(
              run_id, purpose, provider, model, route_reason, prompt_tokens, completion_tokens,
              estimated_cost_usd, saved_cost_usd, metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                run_id,
                route.get('purpose'),
                route.get('provider'),
                route.get('model'),
                route.get('route_reason'),
                prompt_tokens,
                completion_tokens,
                estimated_cost,
                saved,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
    return {'id': cur.lastrowid, 'estimated_cost_usd': estimated_cost, 'saved_cost_usd': saved}


def list_usage_events(limit: int = 100) -> list[dict[str, Any]]:
    rows = db_conn().execute('SELECT * FROM model_usage_events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    return [dict(row) for row in rows]
