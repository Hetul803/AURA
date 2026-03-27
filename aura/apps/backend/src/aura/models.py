from __future__ import annotations

from llm.assist_client import assist_model_metadata
from llm.ollama_client import default_ollama_model, ollama_model_present, ollama_status, ollama_tags
from llm.simple_llm import respond
from aura.state import db_conn


ASSIST_SETUP_DOC = 'Mac private alpha: install/start Ollama, then pull the selected local model before using real assist drafting.'


def _default_selected_model() -> str:
    return f'ollama:{default_ollama_model()}'


def available_models():
    status = ollama_status(timeout=1.0)
    base = [{
        'id': 'simple',
        'label': 'SimpleLLM (deterministic demo fallback)',
        'assist_ready': False,
        'recommended_for_assist': False,
    }]
    if status.get('ok'):
        for name in status.get('models', []):
            base.append({
                'id': f'ollama:{name}',
                'label': f'Ollama Local ({name})',
                'assist_ready': True,
                'recommended_for_assist': True,
            })
    else:
        fallback = default_ollama_model()
        base.append({
            'id': f'ollama:{fallback}',
            'label': f'Ollama Local ({fallback})',
            'available': False,
            'assist_ready': False,
            'recommended_for_assist': True,
        })
    return base



def selected_model() -> str:
    row = db_conn().execute("SELECT value FROM profile_meta WHERE key='selected_model'").fetchone()
    return row['value'] if row else _default_selected_model()



def selected_model_metadata() -> dict:
    selected = selected_model()
    if selected.startswith('ollama:'):
        model_name = selected.split(':', 1)[1]
        return {'provider': 'ollama', 'model': model_name, 'available': ollama_model_present(model_name)}
    if selected == 'ollama':
        model_name = default_ollama_model()
        return {'provider': 'ollama', 'model': model_name, 'available': ollama_model_present(model_name)}
    return {'provider': 'simple', 'model': 'simple', 'available': True}



def assist_model_info() -> dict:
    info = assist_model_metadata()
    selected = selected_model_metadata()
    if selected['provider'] == 'ollama':
        return {**info, 'model': selected['model'], 'selected': selected['provider']}
    return {**info, 'selected': selected['provider']}



def model_runtime_status() -> dict:
    selected = selected_model_metadata()
    ollama = ollama_status(timeout=1.0)
    assist = assist_model_info()
    selected_model_id = selected_model()
    using_local_model = selected['provider'] == 'ollama'
    selected_model_present = selected['provider'] == 'ollama' and selected['model'] in ollama.get('models', []) if ollama.get('ok') else False
    readiness_code = 'ready'
    setup_steps: list[str] = []
    limitations: list[str] = []
    summary = 'Local model ready for real assist drafting.'

    if not using_local_model:
        readiness_code = 'demo_only_model_selected'
        summary = 'SimpleLLM is only suitable for deterministic demos; real assist drafting requires a local Ollama model.'
        setup_steps = [
            f"Select an Ollama model such as {default_ollama_model()}.",
            'Install and start Ollama if it is not already running.',
            f"Run `ollama pull {default_ollama_model()}` before using real assist drafting.",
        ]
        limitations = [
            'Assist classification can still fall back to parser logic.',
            'Real draft generation is disabled until an Ollama model is selected and ready.',
        ]
    elif not ollama.get('ok'):
        readiness_code = ollama.get('error') or 'ollama_unavailable'
        summary = f"AURA could not reach Ollama at {ollama.get('host')}."
        setup_steps = [
            'Install Ollama on this Mac if it is not present.',
            'Start the Ollama app or run `ollama serve`.',
            f"Ensure the selected model `{selected['model']}` is available with `ollama pull {selected['model']}`.",
        ]
        limitations = [
            'Real assist drafting is unavailable until Ollama is reachable.',
            ASSIST_SETUP_DOC,
        ]
    elif not selected_model_present:
        readiness_code = 'selected_model_missing'
        summary = f"Ollama is reachable, but the selected model `{selected['model']}` is not installed yet."
        setup_steps = [
            f"Run `ollama pull {selected['model']}`.",
            'Refresh model status after the pull completes.',
        ]
        limitations = [
            'Real assist drafting is blocked until the selected model is installed locally.',
        ]
    else:
        setup_steps = ['Real drafting is ready on this Mac. Use the overlay or dashboard to start a task.']

    return {
        'selected_model_id': selected_model_id,
        'selected_model': selected,
        'assist_model': assist,
        'available_models': available_models(),
        'ollama': {
            'host': ollama.get('host'),
            'reachable': bool(ollama.get('ok')),
            'error': ollama.get('error'),
            'detail': ollama.get('detail'),
            'models': ollama.get('models', []),
        },
        'using_local_model': using_local_model,
        'selected_model_present': selected_model_present,
        'runtime_ready': bool(ollama.get('ok') and selected_model_present),
        'assist_drafting_ready': bool(ollama.get('ok') and using_local_model and selected_model_present),
        'readiness_code': readiness_code,
        'summary': summary,
        'limitations': limitations,
        'setup_steps': setup_steps,
        'alpha_notes': [ASSIST_SETUP_DOC],
    }



def generate(prompt: str) -> str:
    return respond(prompt)
