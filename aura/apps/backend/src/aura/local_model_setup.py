from __future__ import annotations

import platform
import os
import shutil
import subprocess
import time
from typing import Any

from llm.ollama_client import ollama_available, ollama_tags
from .state import db_conn

GEMMA4_MODELS = [
    {
        'model': 'gemma4:e4b-nvfp4',
        'label': 'Gemma 4 compact',
        'min_ram_gb': 8,
        'role': 'lightweight planning, classification, summaries, memory cleanup, private drafts',
    },
    {
        'model': 'gemma4:latest',
        'label': 'Gemma 4 balanced',
        'min_ram_gb': 16,
        'role': 'better local drafting and daily reasoning on capable Macs',
    },
    {
        'model': 'gemma4:26b',
        'label': 'Gemma 4 26B',
        'min_ram_gb': 32,
        'role': 'stronger local reasoning when memory is available',
    },
    {
        'model': 'gemma4:31b',
        'label': 'Gemma 4 31B',
        'min_ram_gb': 64,
        'role': 'largest local Gemma route for high-memory machines',
    },
]


def detect_hardware() -> dict[str, Any]:
    system = platform.system() or 'Unknown'
    machine = platform.machine() or 'unknown'
    processor = platform.processor() or ''
    ram_gb = None
    if system == 'Darwin':
        macos_version = ''
        try:
            mem = subprocess.run(['sysctl', '-n', 'hw.memsize'], capture_output=True, text=True, timeout=1.5, check=True)
            ram_gb = round(int(mem.stdout.strip()) / (1024 ** 3))
        except Exception:
            ram_gb = None
        try:
            version = subprocess.run(['sw_vers', '-productVersion'], capture_output=True, text=True, timeout=1.5, check=True)
            macos_version = version.stdout.strip()
        except Exception:
            macos_version = ''
        if not processor:
            try:
                brand = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], capture_output=True, text=True, timeout=1.5, check=True)
                processor = brand.stdout.strip()
            except Exception:
                processor = ''
    else:
        macos_version = ''
    if ram_gb is None:
        try:
            pages = int(os.sysconf('SC_PHYS_PAGES'))
            page_size = int(os.sysconf('SC_PAGE_SIZE'))
            ram_gb = round((pages * page_size) / (1024 ** 3))
        except Exception:
            ram_gb = None
    return {
        'os': system,
        'arch': machine,
        'cpu': processor or machine,
        'ram_gb': ram_gb,
        'macos_version': macos_version,
        'apple_silicon': system == 'Darwin' and machine in {'arm64', 'aarch64'},
        'intel_mac': system == 'Darwin' and machine in {'x86_64', 'i386'},
    }


def _installed_model_names(tags: list[dict[str, Any]]) -> list[str]:
    return [str(item.get('name') or item.get('model') or '') for item in tags if item.get('name') or item.get('model')]


def recommend_local_model(hardware: dict[str, Any] | None = None, installed_models: list[str] | None = None) -> dict[str, Any]:
    hardware = hardware or detect_hardware()
    installed_models = installed_models or []
    ram = hardware.get('ram_gb') or 8
    eligible = [item for item in GEMMA4_MODELS if ram >= item['min_ram_gb']]
    recommended = eligible[-1] if eligible else GEMMA4_MODELS[0]
    installed_match = next((name for name in installed_models if name.startswith(recommended['model'])), None)
    if not installed_match:
        installed_match = next((name for name in installed_models if name.startswith('gemma4')), None)
    fallback = next((name for name in installed_models if name), None)
    selected = installed_match or recommended['model']
    return {
        **recommended,
        'model': selected,
        'recommended_pull': recommended['model'],
        'choices': _model_choices(ram, installed_models, recommended['model']),
        'installed': bool(installed_match),
        'fallback_installed_model': fallback,
        'reason': _recommendation_reason(hardware, recommended),
        'cloud_guidance': 'Use Codex for repo implementation and heavy coding. Use ChatGPT or Claude browser handoff for heavier reasoning when you choose it.',
        'local_roles': [
            'lightweight planning',
            'routing and classification',
            'memory cleanup and compaction',
            'email draft fallback',
            'summarization',
            'privacy-sensitive simple tasks',
        ],
    }


def _model_choices(ram: int, installed_models: list[str], recommended_model: str) -> list[dict[str, Any]]:
    choices = []
    for item in GEMMA4_MODELS:
        available_for_hardware = ram >= item['min_ram_gb']
        installed = any(name == item['model'] or name.startswith(item['model'] + ':') for name in installed_models)
        choices.append({
            **item,
            'id': item['model'],
            'installed': installed,
            'available_for_hardware': available_for_hardware,
            'recommended': item['model'] == recommended_model,
            'status': 'installed' if installed else ('recommended' if item['model'] == recommended_model else ('available' if available_for_hardware else 'too_large_for_detected_ram')),
        })
    choices.append({
        'id': 'simple',
        'model': 'simple',
        'label': 'Skip local model for now',
        'min_ram_gb': 0,
        'role': 'deterministic fallback until Ollama is configured',
        'installed': True,
        'available_for_hardware': True,
        'recommended': False,
        'status': 'fallback',
    })
    return choices


def _recommendation_reason(hardware: dict[str, Any], model: dict[str, Any]) -> str:
    ram = hardware.get('ram_gb')
    chip = 'Apple Silicon' if hardware.get('apple_silicon') else 'Intel/other'
    if ram is None:
        return f'{model["label"]} is the conservative default because AURA could not read total RAM on this {chip} machine.'
    return f'{model["label"]} fits the detected {ram} GB RAM {chip} profile.'


def local_model_status() -> dict[str, Any]:
    installed = shutil.which('ollama') is not None
    running = False
    tags: list[dict[str, Any]] = []
    error = ''
    if installed:
        try:
            running = ollama_available()
            tags = ollama_tags(timeout=1.2) if running else []
        except Exception as exc:
            error = str(exc)
    names = _installed_model_names(tags)
    hardware = detect_hardware()
    recommendation = recommend_local_model(hardware, names)
    selected = _selected_model()
    selected_model = selected.split(':', 1)[1] if selected.startswith('ollama:') else selected
    selected_available = selected == 'simple' or any(name == selected_model or name.startswith(selected_model + ':') for name in names)
    return {
        'hardware': hardware,
        'ollama': {
            'installed': installed,
            'running': running,
            'host': 'http://localhost:11434',
            'error': error,
            'install_url': 'https://ollama.com/download',
            'install_command': 'brew install --cask ollama',
        },
        'available_models': names,
        'recommendation': recommendation,
        'selected_model': {'id': selected, 'model': selected_model, 'available': selected_available},
        'setup_steps': _setup_steps(installed, running, recommendation),
        'summary': _summary(installed, running, names, recommendation),
    }


def _selected_model() -> str:
    row = db_conn().execute("SELECT value FROM profile_meta WHERE key='selected_model'").fetchone()
    return row['value'] if row else 'simple'


def _setup_steps(installed: bool, running: bool, recommendation: dict[str, Any]) -> list[str]:
    steps = []
    if not installed:
        steps.append('Install Ollama from https://ollama.com/download or with `brew install --cask ollama`.')
    if installed and not running:
        steps.append('Start Ollama, then refresh AURA local model status.')
    if not recommendation.get('installed'):
        steps.append(f"Approve pulling `{recommendation['recommended_pull']}` from onboarding, or skip and use SimpleLLM until later.")
    steps.append('Keep Codex, ChatGPT, and Claude optional for heavy coding or reasoning; local Gemma is the private/cheap first route.')
    return steps


def _summary(installed: bool, running: bool, names: list[str], recommendation: dict[str, Any]) -> str:
    if not installed:
        return 'Ollama is not installed. AURA can start with SimpleLLM, but real local drafting needs Ollama.'
    if not running:
        return 'Ollama is installed but not running.'
    if recommendation.get('installed'):
        return f"AURA found local models and recommends {recommendation['model']} for this Mac."
    return f"Ollama is running with {len(names)} model(s). AURA recommends pulling {recommendation['recommended_pull']}."


def select_model(model_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        conn.execute("INSERT INTO profile_meta(key,value) VALUES('selected_model',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (model_id,))
    return {'ok': True, 'model_id': model_id}

def start_ollama_server(wait_seconds: float = 2.0) -> dict[str, Any]:
    if shutil.which('ollama') is None:
        return {
            'ok': False,
            'status': 'missing_ollama',
            'install_url': 'https://ollama.com/download',
            'install_command': 'brew install --cask ollama',
            'message': 'Ollama is not installed, so AURA cannot start the local model runtime.',
        }
    if ollama_available():
        return {'ok': True, 'status': 'already_running', 'command': 'ollama serve'}
    try:
        subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as exc:
        return {'ok': False, 'status': 'start_failed', 'command': 'ollama serve', 'message': str(exc)}
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if ollama_available():
            return {'ok': True, 'status': 'started', 'command': 'ollama serve'}
        time.sleep(0.2)
    return {
        'ok': False,
        'status': 'starting_or_blocked',
        'command': 'ollama serve',
        'message': 'AURA tried to start Ollama, but it was not reachable yet. Start the Ollama app or run `ollama serve`, then retry.',
    }


def pull_model(model: str, *, approved: bool = False, select_after_pull: bool = True, timeout: int = 1800) -> dict[str, Any]:
    if not approved:
        return {'ok': False, 'requires_approval': True, 'status': 'approval_required', 'model': model, 'reason': 'model_pull_download_requires_user_approval'}
    if shutil.which('ollama') is None:
        return {
            'ok': False,
            'status': 'missing_ollama',
            'model': model,
            'install_url': 'https://ollama.com/download',
            'install_command': 'brew install --cask ollama',
            'repair': 'Install Ollama, open it once, then retry the download in AURA.',
        }
    if not ollama_available():
        started = start_ollama_server(wait_seconds=3.5)
        if not started.get('ok'):
            return {
                'ok': False,
                'status': 'ollama_not_running',
                'model': model,
                'command': 'ollama serve',
                'start_result': started,
                'repair': 'Start the Ollama app or run `ollama serve`, then retry the download in AURA.',
            }
    proc = subprocess.run(['ollama', 'pull', model], capture_output=True, text=True, timeout=timeout)
    ok = proc.returncode == 0
    if ok and select_after_pull:
        select_model(f'ollama:{model}')
    return {
        'ok': ok,
        'status': 'pulled' if ok else 'pull_failed',
        'model': model,
        'stdout': proc.stdout[-4000:],
        'stderr': proc.stderr[-4000:],
        'selected': f'ollama:{model}' if ok and select_after_pull else None,
    }
