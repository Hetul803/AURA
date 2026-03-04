from llm.ollama_client import ollama_available
from llm.simple_llm import respond
from aura.state import db_conn


def available_models():
    base = [{"id": "simple", "label": "SimpleLLM (deterministic)"}]
    if ollama_available():
        base.append({"id": "ollama", "label": "Ollama Local"})
    return base


def selected_model() -> str:
    row = db_conn().execute("SELECT value FROM profile_meta WHERE key='selected_model'").fetchone()
    return row['value'] if row else 'simple'


def generate(prompt: str) -> str:
    model = selected_model()
    if model == 'ollama' and ollama_available():
        return f"[ollama] {respond(prompt)}"
    return respond(prompt)
