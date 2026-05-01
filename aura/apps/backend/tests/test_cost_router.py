from fastapi.testclient import TestClient

from api.main import app
from aura.cost_router import (
    get_cached_response,
    list_usage_events,
    model_candidates,
    put_cached_response,
    record_model_usage,
    route_model,
    set_budget,
    usage_summary,
)
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_cost_tables():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM model_usage_events')
        conn.execute('DELETE FROM model_response_cache')
        conn.execute('DELETE FROM cost_budgets')


def test_model_candidates_include_local_cloud_and_user_subscription():
    candidates = model_candidates()
    providers = {(item['provider'], item['model']) for item in candidates}
    assert ('simple', 'simple') in providers
    assert ('openai', 'gpt-5.5') in providers
    assert ('user_web', 'chatgpt_subscription') in providers


def test_route_sensitive_context_prefers_local_and_estimates_savings():
    _clear_cost_tables()
    route = route_model(purpose='planning', prompt='private planning context', privacy='sensitive', complexity='simple')
    assert route['provider'] in {'simple', 'ollama'}
    assert route['estimated_cost_usd'] == 0.0
    assert route['estimated_savings_vs_premium_usd'] >= 0
    assert route['route_reason'] == 'sensitive_context_prefers_local_model'


def test_route_user_task_can_prefer_user_subscription():
    route = route_model(purpose='writing', prompt='draft a reply', prefer_user_subscription=True)
    assert route['provider'] == 'user_web'
    assert route['model'] == 'chatgpt_subscription'


def test_usage_cache_budget_and_api_contracts():
    _clear_cost_tables()
    budget = set_budget(monthly_limit_usd=10.0, warn_at_usd=8.0)
    assert budget['monthly_limit_usd'] == 10.0

    route = route_model(purpose='planning', prompt='plan this task')
    usage = record_model_usage(run_id='r1', route=route)
    assert usage['id']
    assert list_usage_events()[0]['run_id'] == 'r1'
    assert usage_summary()['events_count'] == 1

    put_cached_response('planning', 'plan this task', route['provider'], route['model'], {'answer': 'cached'})
    cached = get_cached_response('planning', 'plan this task')
    assert cached is not None
    assert cached['response']['answer'] == 'cached'
    assert route_model(purpose='planning', prompt='plan this task')['cache_hit'] is True

    assert client.get('/cost/models').status_code == 200
    api_route = client.post('/cost/route', json={'purpose': 'writing', 'prompt': 'reply', 'prefer_user_subscription': True})
    assert api_route.status_code == 200
    assert api_route.json()['provider'] == 'user_web'
    api_usage = client.post('/cost/usage', json={'run_id': 'r2', 'route': api_route.json()})
    assert api_usage.status_code == 200
    assert client.get('/cost/summary').json()['events_count'] >= 2
