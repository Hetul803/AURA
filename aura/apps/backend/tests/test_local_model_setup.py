from fastapi.testclient import TestClient

from api.main import app
from aura import local_model_setup
from aura.local_model_setup import local_model_status, pull_model, recommend_local_model, select_model

client = TestClient(app)


def test_hardware_recommendation_chooses_compact_gemma_for_low_memory():
    rec = recommend_local_model({'os': 'Darwin', 'arch': 'arm64', 'ram_gb': 8, 'apple_silicon': True}, [])
    assert rec['recommended_pull'] == 'gemma4:e4b-nvfp4'
    assert 'privacy-sensitive simple tasks' in rec['local_roles']
    assert any(choice['model'] == 'gemma4:e4b-nvfp4' and choice['recommended'] for choice in rec['choices'])
    assert any(choice['id'] == 'simple' for choice in rec['choices'])


def test_hardware_recommendation_chooses_larger_gemma_for_capable_mac():
    rec = recommend_local_model({'os': 'Darwin', 'arch': 'arm64', 'ram_gb': 32, 'apple_silicon': True}, [])
    assert rec['recommended_pull'] == 'gemma4:26b'
    assert rec['cloud_guidance'].startswith('Use Codex')
    assert any(choice['model'] == 'gemma4:26b' and choice['available_for_hardware'] for choice in rec['choices'])


def test_missing_ollama_status_is_guided_fallback(monkeypatch):
    monkeypatch.setattr(local_model_setup.shutil, 'which', lambda name: None)
    status = local_model_status()
    assert status['ollama']['installed'] is False
    assert status['selected_model']['id'] in {'simple', 'ollama:gemma4:e4b-nvfp4'}
    assert 'SimpleLLM' in status['summary']


def test_model_pull_requires_approval_before_download(monkeypatch):
    monkeypatch.setattr(local_model_setup.shutil, 'which', lambda name: '/usr/local/bin/ollama')
    result = pull_model('gemma4:e4b-nvfp4', approved=False)
    assert result['ok'] is False
    assert result['requires_approval'] is True
    assert result['reason'] == 'model_pull_download_requires_user_approval'


def test_model_pull_uses_ollama_after_approval(monkeypatch):
    calls = []

    class Proc:
        returncode = 0
        stdout = 'pulled'
        stderr = ''

    monkeypatch.setattr(local_model_setup.shutil, 'which', lambda name: '/usr/local/bin/ollama')
    monkeypatch.setattr(local_model_setup.subprocess, 'run', lambda args, **kwargs: calls.append(args) or Proc())
    result = pull_model('gemma4:e4b-nvfp4', approved=True, select_after_pull=False)
    assert result['ok'] is True
    assert calls[0] == ['ollama', 'pull', 'gemma4:e4b-nvfp4']


def test_local_model_status_api_contract(monkeypatch):
    monkeypatch.setattr(local_model_setup.shutil, 'which', lambda name: None)
    status = client.get('/local-model/status')
    assert status.status_code == 200
    assert status.json()['recommendation']['recommended_pull'].startswith('gemma4:')

    pull = client.post('/local-model/pull', json={'model': 'gemma4:e4b-nvfp4', 'approved': False})
    assert pull.status_code == 403


def test_selected_ollama_model_is_used_by_assist_path(monkeypatch):
    from llm import assist_client

    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return {
            'ok': True,
            'provider': 'ollama',
            'model': kwargs['model'],
            'response': '{"task_kind":"reply","source_text_present":true,"intent_confidence":0.91,"needs_research":false,"style_hints":{},"approval_required":true,"pasteback_mode":"reactivate_validate_paste","reasoning_summary":"selected"}',
        }

    select_model('ollama:gemma4:latest')
    monkeypatch.setattr(assist_client, 'ollama_available', lambda: True)
    monkeypatch.setattr(assist_client, 'ollama_generate', fake_generate)
    result = assist_client.classify_assist_request('Reply to this email')
    assert result.provider == 'ollama'
    assert result.model == 'gemma4:latest'
    assert calls[0]['model'] == 'gemma4:latest'

    select_model('simple')
