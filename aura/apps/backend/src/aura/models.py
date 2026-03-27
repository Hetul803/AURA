from __future__ import annotations

from llm.assist_client import assist_model_metadata
from llm.ollama_client import default_ollama_model, ollama_available, ollama_tags
from llm.simple_llm import respond
from aura.state import db_conn


def available_models():
    base = [{"id": "simple", "label": "SimpleLLM (deterministic demo)"}]
    if ollama_available():
        for model in ollama_tags():
            name = model.get('name')
            if name:
                base.append({"id": f"ollama:{name}", "label": f"Ollama Local ({name})"})
    else:
        base.append({"id": f"ollama:{default_ollama_model()}", "label": f"Ollama Local ({default_ollama_model()})", "available": False})
    return base


def selected_model() -> str:
    row = db_conn().execute("SELECT value FROM profile_meta WHERE key='selected_model'").fetchone()
    return row['value'] if row else 'simple'


def selected_model_metadata() -> dict:
    selected = selected_model()
    if selected.startswith('ollama:'):
        model_name = selected.split(':', 1)[1]
        return {'provider': 'ollama', 'model': model_name, 'available': ollama_available()}
    if selected == 'ollama':
        return {'provider': 'ollama', 'model': default_ollama_model(), 'available': ollama_available()}
    return {'provider': 'simple', 'model': 'simple', 'available': True}


def assist_model_info() -> dict:
    info = assist_model_metadata()
    selected = selected_model_metadata()
    if selected['provider'] == 'ollama':
        return {**info, 'model': selected['model'], 'selected': selected['provider']}
    return {**info, 'selected': selected['provider']}


def generate(prompt: str) -> str:
    # Non-assist/demo path only.
    return respond(prompt)
