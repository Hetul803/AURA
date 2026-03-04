import os, httpx

def ollama_available() -> bool:
    host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
    try:
        r = httpx.get(f'{host}/api/tags', timeout=0.5)
        return r.status_code == 200
    except Exception:
        return False
